"""Model-dataset resolver.

`model_df(st)` returns the project's **own** parsed long table when the client's
data has been uploaded and bound (the 2.21 schema, via ``data_binding`` or the
Data Engine's published assets). Per-project tables are cached and invalidated
when a data file is uploaded.

**The reference dataset is not a silent fallback.** A project that cannot produce
its own table resolves to ``source="none"`` with a human-readable ``reason``, and
S2 blocks on it — a real project must never be scored on Danone's 23.8k rows
without anybody noticing. The seeded demo project (and an explicit config switch)
keep the reference path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import pandas as pd

from app import ingest
from app.config import get_settings

# Per-project resolutions (cached; None entry = not resolved yet).
_PROJECT_CACHE: dict[str, "DatasetResolution"] = {}

# The seeded Danone case is the one project the reference dataset legitimately
# *is* the project's own data. Everything else must bring its own.
REFERENCE_PROJECTS = frozenset({"danone-mizone"})


@dataclass(frozen=True)
class DatasetResolution:
    """Where a project's modeling table came from, and why."""
    df: Optional[pd.DataFrame]
    source: str          # "published" | "slot" | "reference" | "none"
    reason: str = ""     # populated for "none" (blocker text) and "reference"

    @property
    def usable(self) -> bool:
        return self.df is not None and not self.df.empty


@dataclass(frozen=True)
class TaxonomyDiagnosis:
    """Whether a long table carries the roles the MMM engine needs to model.

    A table can be perfectly well-formed and still model nothing: the OLS engine
    picks Y and X by taxonomy tags, so a compiler that emitted `media` instead of
    `MARKETING FACTOR` yields zero drivers — and every S2 task would report
    success over an empty universe. This makes that condition loud and early.
    """
    rows: int = 0
    objects: list[str] = field(default_factory=list)
    y_rows: int = 0
    x_rows: int = 0
    channel_type_coverage: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def modelable(self) -> bool:
        return not self.problems


@lru_cache(maxsize=1)
def _reference_df() -> pd.DataFrame:
    """The single Danone reference dataset (23.8k rows), cached for the process."""
    return ingest.load_model_dataset()


def _allow_reference(pid: str) -> bool:
    """The reference dataset stands in for a project's own data only for the
    seeded demo, or when an operator explicitly opts in."""
    return pid in REFERENCE_PROJECTS or get_settings().allow_reference_fallback


def resolve_dataset(st: object | None = None) -> DatasetResolution:
    """Resolve a project's modeling table, declaring where it came from."""
    pid = getattr(st, "project_id", None) if st is not None else None
    if not pid:
        # No project context (tests, reference tooling) — the reference table is
        # the only thing there is to serve.
        return DatasetResolution(_reference_df(), "reference", "No project context.")
    if pid not in _PROJECT_CACHE:
        _PROJECT_CACHE[pid] = _resolve(pid, st)
    return _PROJECT_CACHE[pid]


def _resolve(pid: str, st: object) -> DatasetResolution:
    """Published data assets first (the Data Engine), then the legacy per-L3 slot
    binding, then — only where allowed — the reference table."""
    reasons: list[str] = []
    try:
        from app.dataeng.binding import published_long_table
        published, why = published_long_table(pid, st)
        if published is not None and not published.empty:
            return DatasetResolution(published, "published")
        if why:
            reasons.append(why)
    except Exception as exc:  # noqa: BLE001 — a bad asset must not break compute…
        reasons.append(f"Published assets could not be read: {exc}")  # …but it must be visible.

    try:
        from app.agents.data_binding import build_project_long_table
        slot = build_project_long_table(st)
        if slot is not None and not slot.empty:
            return DatasetResolution(slot, "slot")
        reasons.append("No bindable per-L3 slot uploads.")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"Slot uploads could not be parsed: {exc}")

    if _allow_reference(pid):
        return DatasetResolution(_reference_df(), "reference",
                                 "Using the Danone reference dataset.")
    return DatasetResolution(None, "none", " ".join(reasons) or "No project data available.")


def model_df(st: object | None = None) -> pd.DataFrame:
    """The project's modeling table, or an **empty** frame when it has none.

    Callers that must not run on an empty universe should check
    `resolve_dataset(st).usable` (or go through `dataset_blocker`) first; the
    empty frame keeps read-only paths (previews, renderers) total.
    """
    res = resolve_dataset(st)
    if res.usable:
        return res.df
    return _empty_long_table()


@lru_cache(maxsize=1)
def _empty_long_table() -> pd.DataFrame:
    from app.ingest.dataset import COLUMN_NAMES
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMN_NAMES})


def dataset_blocker(st: object | None = None) -> str:
    """The blocker text when a project has no usable data of its own, else ""."""
    res = resolve_dataset(st)
    return "" if res.usable else (res.reason or "No project data available.")


def model_objects(st: object | None = None) -> list[str]:
    """The MMM model objects present in the resolved data (channel_type groups)."""
    df = model_df(st)
    if df.empty or "channel_type" not in df.columns:
        return []
    types = [t for t in df["channel_type"].dropna().unique().tolist() if str(t).strip()]
    preferred = ["MT", "TT", "AFH", "EC", "O2O", "WS", "社区团购"]
    present = [p for p in preferred if p in types]
    return present or types


def diagnose_taxonomy(st: object | None = None) -> TaxonomyDiagnosis:
    """Check the resolved table carries a Y, some X drivers, and model objects."""
    df = model_df(st)
    if df.empty:
        return TaxonomyDiagnosis(problems=["The modeling table is empty."])

    from app.mmm.pivot import _is_y_row, is_driver_row

    objects = model_objects(st)
    ct = df["channel_type"] if "channel_type" in df.columns else pd.Series(dtype="object")
    coverage = float(ct.astype(str).str.strip().ne("").mean()) if len(ct) else 0.0

    y_mask = _is_y_row(df)
    y_rows = int(y_mask.sum())
    x_rows = int((is_driver_row(df) & ~y_mask).sum())

    problems: list[str] = []
    if not objects:
        problems.append(
            "No model objects: every row's `channel_type` is blank. Map a channel "
            "column in the Data Engine, or set a constant channel for single-channel data."
        )
    if y_rows == 0:
        problems.append(
            "No row was recognised as the response (Y). Tag the KPI metric with "
            "`metric_type='Y'` (or `l1='KPI'`) in the Data Engine's published indicators."
        )
    if x_rows == 0:
        problems.append(
            "No row was recognised as a driver (X). Tag spend/activity metrics with "
            "`metric_type='spending'` or `'X'` (or `l1='MARKETING FACTOR'`)."
        )
    return TaxonomyDiagnosis(rows=len(df), objects=objects, y_rows=y_rows, x_rows=x_rows,
                             channel_type_coverage=round(coverage, 3), problems=problems)


def uses_project_data(st: object | None = None) -> bool:
    """True when `model_df` is serving the project's own uploaded data."""
    return resolve_dataset(st).source in ("published", "slot")


def set_project_dataset(project_id: str, df: pd.DataFrame, source: str = "published") -> None:
    """Seed a project's resolved table directly (tests / fixtures).

    The cache holds `DatasetResolution`, not bare frames — the source is part of
    the answer now — so callers must go through here rather than poking
    `_PROJECT_CACHE` with a DataFrame.
    """
    _PROJECT_CACHE[project_id] = DatasetResolution(df, source)


def invalidate_project(project_id: str) -> None:
    """Drop a project's cached long table (call after a data upload/delete)."""
    _PROJECT_CACHE.pop(project_id, None)
    # The indicator universe is derived from that table, so it goes too.
    from app.agents.ledger import invalidate_universe
    invalidate_universe(project_id)
