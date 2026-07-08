"""Model-dataset resolver.

`model_df(st)` returns the project's **own** parsed long table when the client's
data has been uploaded and bound (the 2.21 schema, via ``data_binding``), and
otherwise falls back to the Danone **reference** dataset — so the seeded demo and
any project without uploads keep working. Per-project tables are cached and
invalidated when a data file is uploaded.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import pandas as pd

from app import ingest

# Per-project parsed long tables (None = parsed-but-empty / no bindable data).
_PROJECT_CACHE: dict[str, Optional[pd.DataFrame]] = {}


@lru_cache(maxsize=1)
def _reference_df() -> pd.DataFrame:
    """The single Danone reference dataset (23.8k rows), cached for the process."""
    return ingest.load_model_dataset()


def model_df(st: object | None = None) -> pd.DataFrame:
    """Resolve the modeling dataset for a project, else the reference.

    `st` is a ProjectState (or None). When the project has bindable uploaded data
    it is parsed once and cached; otherwise the reference dataset is returned.
    """
    pid = getattr(st, "project_id", None) if st is not None else None
    if pid:
        if pid not in _PROJECT_CACHE:
            _PROJECT_CACHE[pid] = _resolve_project_df(pid, st)
        df = _PROJECT_CACHE[pid]
        if df is not None and not df.empty:
            return df
    return _reference_df()


def _resolve_project_df(pid: str, st: object) -> Optional[pd.DataFrame]:
    """Resolve a project's long table: published data assets first (the data engine),
    then the legacy per-L3 slot binding, else None (→ reference fallback)."""
    try:
        from app.dataeng.binding import build_published_long_table
        published = build_published_long_table(pid, st)
        if published is not None and not published.empty:
            return published
    except Exception:  # noqa: BLE001 — never let a bad asset break compute
        pass
    try:
        from app.agents.data_binding import build_project_long_table
        return build_project_long_table(st)
    except Exception:  # noqa: BLE001
        return None


def model_objects(st: object | None = None) -> list[str]:
    """The MMM model objects present in the resolved data (channel_type groups)."""
    df = model_df(st)
    types = [t for t in df["channel_type"].dropna().unique().tolist() if str(t).strip()]
    preferred = ["MT", "TT", "AFH", "EC", "O2O", "WS", "社区团购"]
    present = [p for p in preferred if p in types]
    return present or types


def uses_project_data(st: object | None = None) -> bool:
    """True when `model_df` is serving the project's own uploaded data."""
    pid = getattr(st, "project_id", None) if st is not None else None
    if not pid:
        return False
    df = _PROJECT_CACHE.get(pid)
    return df is not None and not df.empty


def invalidate_project(project_id: str) -> None:
    """Drop a project's cached long table (call after a data upload/delete)."""
    _PROJECT_CACHE.pop(project_id, None)
