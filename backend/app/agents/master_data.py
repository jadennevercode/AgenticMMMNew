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

    ``model_selection``'s ``exclude``/``include`` are keyed per model object
    (channel type) so 2.5r/2.6/3.2's per-object fits never let one channel's
    drop or tick leak into another's. This mask resolves the keep/drop
    decision **per channel_type present in df** — a master-table call is
    already sliced to (at most) a handful of channels via ``_apply_dims``, so
    it walks each one's own rows against its own ``exclude_for``/
    ``include_for`` rather than flattening every object's verdicts into one
    union. That is the whole point of per-channel screening: a wide table
    sliced to one Channel Type shows exactly that channel's surviving
    indicators, and the same indicator can appear as a column in one channel
    and be absent in another.

    A row whose ``channel_type`` is missing/blank cannot be screened against
    "its" object — there isn't one. ``.astype("string")`` turns NaN into the
    literal string ``"<NA>"``, which — left unnormalized — the per-object loop
    would treat as a real object; ``exclude_for("<NA>")`` then resolves only
    the OBJECT_ANY-level drops, never a real object's own per-object drops, so
    a channel-specific rejection could leak in through any unmapped row. So
    missing/blank/``"<NA>"`` is normalized to ``""`` up front, and the
    unmapped remainder is screened against the **union** of every model
    object's excludes instead (the strict, pre-per-channel-screening
    behaviour) — the safe fallback when a row cannot be pinned to one object.
    """
    sel = model_selection(st)
    l4 = df["l4"].astype("string").map(_lower) if "l4" in df.columns else pd.Series("", index=df.index)
    metric = df["metric"].astype("string").map(_lower)
    if "channel_type" in df.columns:
        raw_ct = df["channel_type"].astype("string")
        ct = raw_ct.map(lambda s: "" if pd.isna(s) or str(s).strip() in ("", "<NA>") else str(s).strip())
    else:
        ct = pd.Series("", index=df.index)
    keep = pd.Series(True, index=df.index)
    for obj in sorted(set(ct) - {""}):
        excl = sel.exclude_for(obj)
        metric_only = {m for excl_l4, m in excl if not excl_l4}
        inc = sel.include_for(obj)
        rowsel = ct == obj
        rej = pd.Series([(a, b) in excl or b in metric_only
                         for a, b in zip(l4[rowsel], metric[rowsel])], index=l4[rowsel].index)
        block = rej if inc is None else (rej | ~metric[rowsel].isin(inc))
        keep.loc[rowsel] = ~block

    unmapped = ct == ""
    if unmapped.any():
        from app.agents.dataset_cache import model_objects
        objects = model_objects(st)
        rejected_union: frozenset[tuple[str, str]] = frozenset().union(
            *(sel.exclude_for(o) for o in objects)) if objects else sel.exclude_for("")
        metric_only_union = {m for excl_l4, m in rejected_union if not excl_l4}
        rej = pd.Series([(a, b) in rejected_union or b in metric_only_union
                         for a, b in zip(l4[unmapped], metric[unmapped])], index=l4[unmapped].index)
        keep.loc[unmapped] = keep.loc[unmapped] & ~rej

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

    # The primary KPI (the response the wide table explains) — prefer the Volume KPI
    # so it matches the OLS default Y (DATA-011/012), else the most frequent KPI.
    kpi_rows = df[_kpi_mask(df)]
    kpi_metric = ""
    if not kpi_rows.empty:
        from app.agents.indicator_metadata import classify_indicator
        kpi_names = _distinct(kpi_rows, "metric")
        volume = [m for m in kpi_names if classify_indicator(m).metric_type == "kpi_volume"]
        kpi_metric = volume[0] if volume else (
            str(kpi_rows["metric"].mode().iloc[0]) if not kpi_rows["metric"].mode().empty else "")

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

    # DATA-011/007: roll each indicator up to its period value with ITS OWN aggregation
    # — a rate/coverage metric (NDWD) averaged across the sliced dimensions, spend and
    # volume summed. A single pivot aggfunc would wrongly sum a rate over regions.
    from app.dataeng.validation_query import _metric_agg, _pandas_agg
    cols_data: dict[str, pd.Series] = {}
    for m, g in frame.groupby("_m"):
        cols_data[str(m)] = g.groupby("_k")["_v"].agg(_pandas_agg(_metric_agg(st, str(m))))
    wide = pd.DataFrame(cols_data).sort_index()

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
