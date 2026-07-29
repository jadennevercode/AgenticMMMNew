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
                                 "Using the shared reference dataset — this project has no data of its own.")
    return DatasetResolution(None, "none", " ".join(reasons) or "No project data available.")


def raw_long_df(st: object | None = None) -> pd.DataFrame:
    """The assembled long table with the 2.1 model-role overrides applied.

    A no-op over the raw frame when no overrides are set — the reference/legacy
    table is returned unchanged. Identical to :func:`model_df` since the national
    roll-up was removed (2026-07-27); both names are kept because both read
    naturally at their call sites.
    """
    res = resolve_dataset(st)
    if not res.usable:
        return _empty_long_table()
    from app.agents.overrides import apply_metric_type_overrides
    return apply_metric_type_overrides(res.df, st)


def model_df(st: object | None = None) -> pd.DataFrame:
    """The project's modeling table — the assembled long table, **unaggregated**.

    Decision 2026-07-27: S2 screens and fits on the data exactly as it was
    published. The 2026-07-23 roll-up to a single national ``TOTAL`` object is
    gone, and with it the last place S2 changed the numbers before scoring them.
    Channel, product, region and source all survive to the consumer, which is what
    lets 2.2 see real granularity, 2.4 build a real panel, and the OLS stage fit
    one model per (channel, product) — see :mod:`app.agents.model_objects`.

    Aggregation still happens, but only where it is the consumer's own declared
    step: ``build_model_frame`` rolls each indicator to one value per month with
    that indicator's 2.1 aggregation, and says so.
    """
    return raw_long_df(st)


@lru_cache(maxsize=1)
def _empty_long_table() -> pd.DataFrame:
    from app.ingest.dataset import COLUMN_NAMES
    return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMN_NAMES})


def dataset_blocker(st: object | None = None) -> str:
    """The blocker text when a project has no usable data of its own, else ""."""
    res = resolve_dataset(st)
    return "" if res.usable else (res.reason or "No project data available.")


def model_objects(st: object | None = None) -> list[str]:
    """The MMM model objects present in the resolved data — one per
    ``(channel_type, brand)`` cell that can carry a model, busiest first.

    N channels × M products = N×M models (2026-07-27). Nothing is hardcoded:
    the channel list, the product list and which combinations are modelable all
    come from the data. See :mod:`app.agents.model_objects` for the id format and
    for why a cell needs both a response and a driver to qualify.
    """
    from app.agents.model_objects import enumerate_objects
    return enumerate_objects(model_df(st), st)


def diagnose_taxonomy(st: object | None = None) -> TaxonomyDiagnosis:
    """Check the **uploaded** table carries a Y, some X drivers, and a channel_type.

    A data-adequacy check on what the project uploaded: it reports real channel
    coverage and requires every row to declare its channel_type, which is now also
    half of a model object's identity."""
    df = raw_long_df(st)
    if df.empty:
        return TaxonomyDiagnosis(problems=["The modeling table is empty."])

    from app.agents.vocabulary import vocab_for
    from app.mmm.pivot import _is_y_row, is_driver_row

    try:
        vocab = vocab_for(st)
    except Exception:  # noqa: BLE001
        from app.agents.vocabulary import DEFAULT_VOCAB as vocab

    ct = df["channel_type"] if "channel_type" in df.columns else pd.Series(dtype="object")
    ctn = ct.astype("string").str.strip()
    objects = sorted({v for v in ctn[ctn.ne("") & ctn.ne("nan")].tolist()})
    # `.ne("")` on a nullable dtype returns NA for a missing value, and `.mean()`
    # skips NA — so a table where a quarter of the rows had no channel_type at all
    # reported 100% coverage, and 2.1 certified "ready to model" for exactly the
    # rows the modeling stage would have to treat specially. Count them as uncovered.
    filled = ctn.notna() & ctn.ne("") & ctn.ne("nan")
    coverage = float(filled.mean()) if len(ctn) else 0.0

    y_mask = _is_y_row(df, vocab)
    y_rows = int(y_mask.sum())
    x_rows = int((is_driver_row(df, vocab) & ~y_mask).sum())

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


def is_reference_seeded(st: object | None = None) -> bool:
    """True when this project's "published" assets are the seeded reference case.

    `seed_reference_assets` publishes the reference table through the real asset
    path, which is deliberate — it exercises the same code a client upload does. The
    side effect is that `resolve_dataset` reports `source="published"` and every
    downstream check answers "yes, the project's own data", so the artifacts present
    one client's numbers as another's with nothing saying otherwise.
    """
    from app.dataeng.seed_reference_assets import REFERENCE_ASSET_MARK
    # The legacy description, so a project seeded before the marker existed is still
    # recognised rather than quietly passing as the client's own data.
    marks = (REFERENCE_ASSET_MARK, "Danone reference source")
    assets = getattr(st, "data_assets", None) or []
    published = [a for a in assets if getattr(a, "status", "") == "published"]
    return bool(published) and all(
        any(m in (getattr(a, "description", "") or "") for m in marks) for a in published)


def uses_project_data(st: object | None = None) -> bool:
    """True when `model_df` is serving the project's own uploaded data.

    A project running on the seeded reference case is **not** running on its own
    data, however it was packaged.
    """
    return resolve_dataset(st).source in ("published", "slot") and not is_reference_seeded(st)


def set_project_dataset(project_id: str, df: pd.DataFrame, source: str = "published") -> None:
    """Seed a project's resolved table directly (tests / fixtures).

    The cache holds `DatasetResolution`, not bare frames — the source is part of
    the answer now — so callers must go through here rather than poking
    `_PROJECT_CACHE` with a DataFrame.
    """
    _PROJECT_CACHE[project_id] = DatasetResolution(df, source)


def invalidate_project(project_id: str) -> None:
    """Drop a project's cached long table (call after a data upload/delete or a 2.1
    override change)."""
    _PROJECT_CACHE.pop(project_id, None)
    # The indicator universe is derived from that table, so it goes too.
    from app.agents.ledger import invalidate_universe
    invalidate_universe(project_id)
    # Every cached 2.3 chart analysis is a reading of numbers that just changed —
    # a stale reading is worse than no reading, so they go with the table.
    from app.store.state import get_store
    st = get_store().get(project_id)
    if st is not None and getattr(st, "validation_chart_analyses", None):
        st.validation_chart_analyses = {}
