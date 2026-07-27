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
        if inc is None:
            block = rej
        else:
            # `inc` is keyed (norm_l4, norm_metric); legacy configs may still
            # carry bare metric names, which keep that metric under any L4.
            inc_pairs = {i for i in inc if isinstance(i, tuple)}
            inc_metrics = {i for i in inc if isinstance(i, str)}
            picked = pd.Series([(a, b) in inc_pairs or b in inc_metrics
                                for a, b in zip(l4[rowsel], metric[rowsel])],
                               index=l4[rowsel].index)
            block = rej | ~picked
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

    # The primary KPI (the response the wide table explains) is the response the
    # user set at 2.1 and the model was fitted on — resolved through the one
    # authority so the master table cannot headline a different Y than the fit.
    # Falls back to the Volume-preferring auto-pick for un-configured projects.
    kpi_rows = df[_kpi_mask(df)]
    kpi_metric = ""
    if not kpi_rows.empty:
        from app.agents.indicator_metadata import classify_indicator
        from app.agents.overrides import resolved_y_metric
        kpi_names = _distinct(kpi_rows, "metric")
        resolved = resolved_y_metric(st, df) or ""
        if resolved and any(_lower(resolved) == _lower(m) for m in kpi_names):
            kpi_metric = next(m for m in kpi_names if _lower(m) == _lower(resolved))
        else:
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


# ── 2.32 reference shape: granularity reference + data station ──────────────
# The `model input_2.32.xlsx` deliverable is two sheets: a per-indicator model
# granularity reference (渠道 scope × 区域 granularity; blank = not selected) and
# the long-format Data Station (the model-input rows at those granularities).

_NA_TOKENS = {"", "nan", "none", "na", "<na>", "total"}


def _clean_set(series: pd.Series) -> list[str]:
    vals = series.astype("string").str.strip().dropna().tolist()
    return sorted({v for v in vals if v and v.lower() not in _NA_TOKENS})


def _channel_scope(channels: list[str]) -> str:
    """渠道 scope string: 全渠道 when the indicator is national/all-channel data
    (no specific channel_type in the raw rows), else the channel-type list."""
    return "全渠道" if not channels else ",".join(channels)


def _region_scope(regions: list[str]) -> str:
    """区域 granularity: National when the indicator is only national, else the
    province-group set (e.g. A,B,C,D)."""
    letters = [r for r in regions if r.lower() != "national"]
    if not letters:
        return "National"
    return ",".join(sorted(letters))


def granularity_reference(st: ProjectState) -> list[dict]:
    """The 模型颗粒度参考表 sheet: every active factor row with its 渠道 scope and
    区域 granularity (a data fact from the raw per-channel table), blank when the
    indicator was not adopted into the model."""
    from app.agents.dataset_cache import raw_long_df
    from app.agents.ledger import _norm_pair, indicator_ledger
    from app.dataeng.mapping import resolve_factor_map

    raw = raw_long_df(st)
    cov: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
    if not raw.empty and {"l4", "metric", "channel_type", "province_group"} <= set(raw.columns):
        for (l4, metric), sub in raw.groupby(
                [raw["l4"].astype("string"), raw["metric"].astype("string")], dropna=False):
            cov[_norm_pair(l4, metric)] = (_clean_set(sub["channel_type"]),
                                           _clean_set(sub["province_group"]))

    # The ledger keys its adopted rows by `(l4.strip().lower(), metric.strip().lower())`
    # — match that exactly (its `_norm_pair`), not `indicator_key`'s space-stripped form.
    adopted_keys = {r.key for r in indicator_ledger(st) if r.adopted}
    rows: list[dict] = []
    for fm in resolve_factor_map(st).rows:
        metric = fm.metric or fm.indicator
        key = _norm_pair(fm.l4, metric)
        adopted = key in adopted_keys
        channels, regions = cov.get(key, ([], []))
        rows.append({
            "l1": fm.l1, "l2": fm.l2, "l3": fm.l3, "l4": fm.l4,
            "indicator": fm.indicator or metric,
            "adopted": adopted,
            # Blank channel + region = not selected into the model (2.32 convention).
            "channelScope": _channel_scope(channels) if adopted else "",
            "regionScope": _region_scope(regions) if adopted else "",
        })
    return rows


# The Data Station columns, in the 2.32 reference order.
DATA_STATION_COLS = [
    ("task_name", "Task name"), ("brand", "品牌"), ("province_group", "省份组别"),
    ("channel_type", "渠道类型"), ("channel", "渠道"), ("year", "年"), ("month", "月"),
    ("source", "数据源"), ("l1", "数据类型Level1"), ("l2", "数据类型Level2"),
    ("l3", "数据类型Level3"), ("l4", "数据类型Level4"), ("l5", "数据类型Level5"),
    ("l6", "数据类型Level6"), ("l7", "数据类型Level7"), ("l8", "数据类型Level8"),
    ("metric_type", "METRICS类型"), ("metric", "METRICS"), ("value", "VALUE"),
]
DATA_STATION_CAP = 5000


def data_station(st: ProjectState, *, limit: int = DATA_STATION_CAP) -> dict:
    """The D.Data Station sheet: the raw per-channel long rows for the **adopted**
    indicators, at their native channel/region/time granularity."""
    from app.agents.dataset_cache import raw_long_df
    from app.agents.ledger import _norm_pair, indicator_ledger

    raw = raw_long_df(st)
    if raw.empty:
        return {"columns": [c for _, c in DATA_STATION_COLS], "rows": [],
                "rowCount": 0, "truncated": False}
    adopted_keys = {r.key for r in indicator_ledger(st) if r.adopted}
    keys = [_norm_pair(a, b) for a, b in zip(raw["l4"].astype("string"), raw["metric"].astype("string"))]
    mask = pd.Series([k in adopted_keys for k in keys], index=raw.index)
    sub = raw[mask]
    total = len(sub)
    truncated = total > limit
    sub = sub.head(limit)
    rows = [
        [None if pd.isna(r.get(col)) else (round(float(r[col]), 2) if col == "value"
         else str(r.get(col, ""))) for col, _ in DATA_STATION_COLS]
        for _, r in sub.iterrows()
    ]
    return {"columns": [c for _, c in DATA_STATION_COLS], "rows": rows,
            "rowCount": total, "truncated": truncated}


def _kpi_metric(df: pd.DataFrame) -> str:
    """The primary KPI in a slice — prefer the Volume KPI (matches the OLS default Y)."""
    kpi_rows = df[_kpi_mask(df)]
    if kpi_rows.empty:
        return ""
    from app.agents.indicator_metadata import classify_indicator
    names = _distinct(kpi_rows, "metric")
    volume = [m for m in names if classify_indicator(m).metric_type == "kpi_volume"]
    if volume:
        return volume[0]
    mode = kpi_rows["metric"].mode()
    return str(mode.iloc[0]) if not mode.empty else ""


def _wide_frame(st: ProjectState, df: pd.DataFrame, grain: str):
    """The full (uncapped) KPI-first wide frame for a slice → (cols, wide indexed by period)."""
    from app.dataeng.validation_query import _metric_agg, _pandas_agg
    kpi_metric = _kpi_metric(df)
    keys = _period_keys(df, grain)
    frame = pd.DataFrame({
        "_k": keys,
        "_m": df["metric"].astype("string").str.strip(),
        "_v": pd.to_numeric(df["value"], errors="coerce"),
    }).dropna(subset=["_k", "_m"])
    if frame.empty:
        return [], pd.DataFrame()
    cols_data: dict[str, pd.Series] = {}
    for m, g in frame.groupby("_m"):
        cols_data[str(m)] = g.groupby("_k")["_v"].agg(_pandas_agg(_metric_agg(st, str(m))))
    wide = pd.DataFrame(cols_data).sort_index()
    cols = [c for c in wide.columns if _lower(c) == _lower(kpi_metric)]
    cols += sorted(c for c in wide.columns if _lower(c) != _lower(kpi_metric))
    return cols, wide


def build_export(st: ProjectState, **_ignored) -> bytes:
    """The 2.32 ``model input`` deliverable as xlsx: two sheets —
    ``模型颗粒度参考表`` (per-indicator 渠道 scope × 区域 granularity) and
    ``D.Data Station`` (the adopted indicators' raw long rows). Uncapped."""
    from io import BytesIO
    import openpyxl

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # Sheet 1 — 模型颗粒度参考表
    ws1 = wb.create_sheet(title="模型颗粒度参考表")
    ws1.append(["生意因子-Level 1", "生意因子-Level 2", "生意因子-Level 3",
                "生意影响因子-Level 4", "指标选择", "渠道", "区域"])
    for r in granularity_reference(st):
        ws1.append([r["l1"], r["l2"], r["l3"], r["l4"], r["indicator"],
                    r["channelScope"], r["regionScope"]])

    # Sheet 2 — D.Data Station (uncapped)
    ws2 = wb.create_sheet(title="D.Data Station")
    ds = data_station(st, limit=10_000_000)
    ws2.append(ds["columns"])
    for row in ds["rows"]:
        ws2.append(row)

    if not wb.sheetnames:
        wb.create_sheet(title="empty")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
