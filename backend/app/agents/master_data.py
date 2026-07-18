"""2.6 Master Data — the modeling feature table, sliced on the 2.24 dimensions.

The modeling long table (the reference ``Data Process_2.24.xlsx`` schema) carries
per row: brand / province_group / channel_type / channel · year / month · the
L1–L8 factor path · METRICS type + label · VALUE. The master table is that long
table

  * restricted to the indicators the **ledger** reports as adopted — an
    indicator any S2 layer rejected can never appear here, and
  * pivoted to one column per indicator over the chosen time grain.

It is computed **live** rather than baked into the artifact: the user slices by
product × channel × region, and materializing every combination up front would
be both enormous and stale the moment a verdict changes.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.agents.ledger import model_selection
from app.dataeng.validation_query import (
    _available_grains,
    _kpi_mask,
    _period_keys,
    _period_label,
)
from app.store.state import ProjectState

# filter key (camelCase, as the API takes it) → long-table column. `channel` is
# in here and not in the validation view's set: the master table is what a user
# slices per-channel before handing it to modeling.
DIM_COLS: dict[str, str] = {
    "brand": "brand",
    "provinceGroup": "province_group",
    "channelType": "channel_type",
    "channel": "channel",
}

# A wide table is for reading, not for scrolling forever.
MAX_ROWS = 400
MAX_COLS = 60


def _lower(s: object) -> str:
    return str(s).strip().lower() if s is not None else ""


def _distinct(df: pd.DataFrame, col: str) -> list[str]:
    if col not in df.columns:
        return []
    vals = df[col].astype("string").str.strip().dropna().unique().tolist()
    return sorted(v for v in vals if v and v.lower() not in ("nan", "none", "na"))


def _apply_dims(df: pd.DataFrame, dims: dict[str, Optional[list[str]]]) -> pd.DataFrame:
    out = df
    for key, col in DIM_COLS.items():
        wanted = dims.get(key)
        if wanted and col in out.columns:
            keep = {_lower(v) for v in wanted}
            out = out[out[col].astype("string").str.strip().str.lower().isin(keep)]
    return out


def adopted_mask(st: ProjectState, df: pd.DataFrame) -> pd.Series:
    """Rows whose indicator survived every S2 filter layer (plus the KPI rows).

    The KPI is the response, not a factor — no layer rules on it, so it is never
    in the ledger and must be admitted explicitly or the table loses its Y.
    """
    sel = model_selection(st)
    l4 = df["l4"].astype("string").map(_lower) if "l4" in df.columns else pd.Series("", index=df.index)
    metric = df["metric"].astype("string").map(_lower)

    metric_only = {m for excl_l4, m in sel.exclude if not excl_l4}
    rejected = pd.Series(
        [(a, b) in sel.exclude or b in metric_only for a, b in zip(l4, metric)],
        index=df.index,
    )
    keep = ~rejected
    if sel.include is not None:
        keep &= metric.isin(sel.include)
    return keep | _kpi_mask(df)


def _adopted_df(st: ProjectState) -> pd.DataFrame:
    from app.agents.dataset_cache import model_df
    df = model_df(st)
    return df[adopted_mask(st, df)]


def dimensions(st: ProjectState) -> dict:
    """The slicing options the master table offers, from the adopted rows only."""
    try:
        df = _adopted_df(st)
    except Exception:  # noqa: BLE001 — no bound data yet
        return {"brand": [], "provinceGroup": [], "channelType": [], "channel": [],
                "grains": ["month"], "indicators": []}
    return {
        "brand": _distinct(df, "brand"),
        "provinceGroup": _distinct(df, "province_group"),
        "channelType": _distinct(df, "channel_type"),
        "channel": _distinct(df, "channel"),
        "grains": _available_grains(df),
        "indicators": _distinct(df, "metric"),
    }


def master_table(
    st: ProjectState,
    *,
    brand: Optional[list[str]] = None,
    province_group: Optional[list[str]] = None,
    channel_type: Optional[list[str]] = None,
    channel: Optional[list[str]] = None,
    grain: str = "month",
    indicators: Optional[list[str]] = None,
) -> dict:
    """The adopted feature wide table for one product × channel × region slice.

    Returns ``{columns, rows, kpi, truncated, rowCount, colCount, note}`` where
    each row is one period and each column one adopted indicator.
    """
    try:
        df = _adopted_df(st)
    except Exception as e:  # noqa: BLE001
        return {"columns": [], "rows": [], "kpi": "", "truncated": False,
                "rowCount": 0, "colCount": 0, "note": f"No modeling data available: {e}"}

    df = _apply_dims(df, {"brand": brand, "provinceGroup": province_group,
                          "channelType": channel_type, "channel": channel})
    if df.empty:
        return {"columns": [], "rows": [], "kpi": "", "truncated": False,
                "rowCount": 0, "colCount": 0,
                "note": "No rows match this slice — widen the filters."}

    if grain not in _available_grains(df):
        grain = "month" if "month" in _available_grains(df) else "year"

    kpi_rows = df[_kpi_mask(df)]
    kpi_metric = (str(kpi_rows["metric"].mode().iloc[0])
                  if not kpi_rows.empty and not kpi_rows["metric"].mode().empty else "")

    if indicators:
        wanted = {_lower(i) for i in indicators} | {_lower(kpi_metric)}
        df = df[df["metric"].astype("string").str.strip().str.lower().isin(wanted)]

    keys = _period_keys(df, grain)
    frame = pd.DataFrame({
        "_k": keys,
        "_m": df["metric"].astype("string").str.strip(),
        "_v": pd.to_numeric(df["value"], errors="coerce"),
    }).dropna(subset=["_k", "_m"])
    if frame.empty:
        return {"columns": [], "rows": [], "kpi": kpi_metric, "truncated": False,
                "rowCount": 0, "colCount": 0, "note": "No usable values in this slice."}

    wide = frame.pivot_table(index="_k", columns="_m", values="_v", aggfunc="sum").sort_index()

    # KPI first — it is the response the rest of the table explains.
    cols = [c for c in wide.columns if _lower(c) == _lower(kpi_metric)]
    cols += sorted(c for c in wide.columns if _lower(c) != _lower(kpi_metric))
    truncated = len(cols) > MAX_COLS or len(wide.index) > MAX_ROWS
    cols = cols[:MAX_COLS]
    index = list(wide.index)[-MAX_ROWS:]

    rows = [[_period_label(int(k), grain)]
            + [None if pd.isna(v := wide.at[k, c]) else round(float(v), 2) for c in cols]
            for k in index]
    return {
        "columns": ["Period"] + [str(c) for c in cols],
        "rows": rows,
        "kpi": kpi_metric,
        "grain": grain,
        "truncated": truncated,
        "rowCount": len(index),
        "colCount": len(cols),
        "note": (f"Showing the last {MAX_ROWS} periods / first {MAX_COLS} indicators."
                 if truncated else ""),
    }
