"""Published data assets → the 2.21 unified long table.

The data engine's cleaning SQL already targets the 19-column long-table schema, so
binding is mostly: union every published asset's parquet, align to the canonical
column order, coerce the time/value types, and sanity-check there's a usable
monthly axis. This replaces the per-L3 slot binding as the project data source.
"""
from __future__ import annotations

import pandas as pd

from app.dataeng.assets import published_frames
from app.ingest.dataset import COLUMN_NAMES

_MIN_ROWS = 12
_MIN_MONTHS = 6


def published_long_table(project_id: str, st) -> tuple[pd.DataFrame | None, str]:
    """Union published assets into the long table.

    Returns ``(frame, reason)``. ``frame`` is None when the published assets are
    not usable as a modeling table, and ``reason`` then says *why* in human terms
    — the dataset resolver surfaces it as a blocker instead of silently swapping
    in the reference data (which is how a project could score someone else's
    numbers with no error anywhere).
    """
    frames = published_frames(project_id, st)
    if not frames:
        return None, "No published data assets. Publish at least one asset in the Data Engine."
    aligned: list[pd.DataFrame] = []
    for df in frames:
        d = df.copy()
        for c in COLUMN_NAMES:
            if c not in d.columns:
                d[c] = pd.NA
        aligned.append(d[COLUMN_NAMES])
    out = pd.concat(aligned, ignore_index=True)
    if len(out) < _MIN_ROWS:
        return None, (f"The published assets total {len(out)} rows; "
                      f"at least {_MIN_ROWS} are required to model.")
    month = pd.to_numeric(out.get("month"), errors="coerce")
    if month.notna().mean() < 0.5:
        return None, ("More than half the published rows have no readable `month`. "
                      "Check the time column mapping in the Data Engine.")
    if month.dropna().nunique() < _MIN_MONTHS:
        return None, (f"The published assets cover {month.dropna().nunique()} distinct months; "
                      f"at least {_MIN_MONTHS} are required to model.")
    out["value"] = pd.to_numeric(out.get("value"), errors="coerce")
    return out.reset_index(drop=True), ""


def build_published_long_table(project_id: str, st) -> pd.DataFrame | None:
    """Union published assets into the long table, or None when none are usable."""
    return published_long_table(project_id, st)[0]
