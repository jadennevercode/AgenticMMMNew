"""Live series query for the Business Validation charts (task 2.3).

Business Validation renders one chart per FactorTree L3: a **constant KPI**
(sell-out) area background, overlaid with that L3's indicator series (bar for
spend-type metrics, line otherwise), plus a yearly + YoY table beneath it. The
series are computed live from the modeling long table (``model_df``) so the
page's filters resolve against real rows instead of a precomputed deck.

Filter semantics:
- **time grain / model dimensions** (brand · channel type · province group) scope
  the whole view — they apply to both the KPI area and the overlay series.
- **data source** filters the overlay only; the KPI area stays the full sell-out
  backdrop so a factor can be eyeballed against total sales regardless of which
  file the factor came from.
- **L4 / indicator** select which overlay series are drawn.

Per-row ``source`` provenance is stamped by the transform compiler (see
``app.dataeng.dbt.compiler``); this module treats the ``source`` column as the
selectable data-source axis.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from app.agents.dataset_cache import model_df

# metric_type tags (lower-cased). The OLS engine tags the response as "Y" and
# spend drivers as "spending"; older reference data uses metric-name patterns.
_KPI_TYPES = {"y"}
_SPEND_TYPES = {"spending", "spend"}
_SALES_PATTERN = r"销量|销售|销额|offtake|sales|volume|gmv|sell.?out|箱|出货"
_SPEND_PATTERN = r"花费|费用|spend|投放|金额|cost|budget"
_INDICATOR_CAP = 6

# filter key (camelCase from the API) → long-table column
_DIM_COLS = {"brand": "brand", "channelType": "channel_type", "provinceGroup": "province_group"}


def _norm(s: object) -> str:
    return "" if s is None else str(s).strip()


def _casefold_eq(series: pd.Series, value: str) -> pd.Series:
    return series.astype("string").str.strip().str.casefold() == value.strip().casefold()


def _kpi_mask(df: pd.DataFrame) -> pd.Series:
    """Rows for the sell-out KPI: explicit ``Y`` tag, else a sales-like metric."""
    mtype = df["metric_type"].astype("string").str.strip().str.casefold()
    by_tag = mtype.isin(_KPI_TYPES)
    if by_tag.any():
        return by_tag
    return df["metric"].astype("string").str.contains(_SALES_PATTERN, case=False, regex=True, na=False)


def _is_spend_metric(df: pd.DataFrame, metric: str) -> bool:
    sub = df[_casefold_eq(df["metric"], metric)]
    if sub.empty:
        return False
    mtype = sub["metric_type"].astype("string").str.strip().str.casefold()
    if mtype.isin(_SPEND_TYPES).any():
        return True
    return bool(sub["metric"].astype("string").str.contains(
        _SPEND_PATTERN, case=False, regex=True, na=False).any())


def _available_grains(df: pd.DataFrame) -> list[str]:
    grains = ["year"]
    if "month" in df.columns and pd.to_numeric(df["month"], errors="coerce").notna().any():
        grains.append("month")
    return grains


def _period_keys(df: pd.DataFrame, grain: str) -> pd.Series:
    col = "year" if grain == "year" else "month"
    return pd.to_numeric(df[col], errors="coerce").astype("Int64")


def _period_label(key: int, grain: str) -> str:
    if grain == "year":
        return str(int(key))
    k = int(key)
    return f"{k // 100:04d}-{k % 100:02d}"


def _sum_by_period(sub: pd.DataFrame, grain: str) -> dict[int, float]:
    if sub.empty:
        return {}
    keys = _period_keys(sub, grain)
    vals = pd.to_numeric(sub["value"], errors="coerce")
    grp = pd.DataFrame({"k": keys, "v": vals}).dropna(subset=["k"]).groupby("k")["v"].sum()
    return {int(k): round(float(v), 2) for k, v in grp.items()}


def _apply_dims(df: pd.DataFrame, dims: dict[str, Optional[list[str]]]) -> pd.DataFrame:
    out = df
    for key, col in _DIM_COLS.items():
        wanted = dims.get(key)
        if wanted and col in out.columns:
            out = out[out[col].astype("string").str.strip().isin([_norm(v) for v in wanted])]
    return out


def _distinct(df: pd.DataFrame, col: str) -> list[str]:
    if col not in df.columns:
        return []
    vals = df[col].astype("string").str.strip().dropna().unique().tolist()
    return sorted(v for v in vals if v and v.lower() not in ("nan", "none"))


def _default_indicators(l3_base: pd.DataFrame) -> list[str]:
    """The L3's own indicators (non-KPI), most-material first, capped."""
    overlay = l3_base[~_kpi_mask(l3_base)]
    if overlay.empty:
        overlay = l3_base
    if overlay.empty:
        return []
    totals = (overlay.assign(_v=pd.to_numeric(overlay["value"], errors="coerce").abs())
              .groupby(overlay["metric"].astype("string").str.strip())["_v"].sum()
              .sort_values(ascending=False))
    metrics = [m for m in totals.index.tolist() if m and str(m).lower() not in ("nan", "none")]
    return metrics[:_INDICATOR_CAP]


def _indicator_options(l3_base: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    overlay = l3_base[~_kpi_mask(l3_base)]
    for _, row in overlay.iterrows():
        metric = _norm(row.get("metric"))
        if not metric or metric in seen:
            continue
        seen.add(metric)
        out.append({
            "metric": metric,
            "metricType": _norm(row.get("metric_type")),
            "l4": _norm(row.get("l4")),
        })
    return out


def _yoy(values: list[Optional[float]]) -> list[Optional[float]]:
    out: list[Optional[float]] = [None]
    for i in range(1, len(values)):
        prev, curr = values[i - 1], values[i]
        if prev and curr is not None:
            out.append(round((curr - prev) / prev * 100, 1))
        else:
            out.append(None)
    return out


def _yearly_table(years: list[int], named_masks: list[tuple[str, pd.DataFrame]]) -> dict:
    rows = []
    for name, sub in named_masks:
        by_year = _sum_by_period(sub, "year")
        values = [by_year.get(y) for y in years]
        rows.append({"metric": name, "values": values, "yoy": _yoy(values)})
    return {"years": years, "rows": rows}


def validation_series(
    st,
    *,
    l3: str,
    l4: Optional[str] = None,
    indicators: Optional[list[str]] = None,
    grain: str = "month",
    sources: Optional[list[str]] = None,
    brand: Optional[list[str]] = None,
    channel_type: Optional[list[str]] = None,
    province_group: Optional[list[str]] = None,
) -> dict:
    """Compute the KPI area + overlay series + yearly/YoY table for one L3."""
    df = model_df(st)
    dims = {"brand": brand, "channelType": channel_type, "provinceGroup": province_group}
    scoped = _apply_dims(df, dims)

    grains = _available_grains(scoped)
    if grain not in grains:
        grain = grains[-1] if grains else "year"

    # The L3 slice (dims applied; source/L4/indicator NOT yet) drives filter options.
    l3_base = scoped[_casefold_eq(scoped["l3"], l3)] if l3 else scoped.iloc[0:0]

    l3_sel = l3_base
    if sources:
        l3_sel = l3_sel[l3_sel["source"].astype("string").str.strip().isin([_norm(s) for s in sources])]
    if l4:
        l3_sel = l3_sel[_casefold_eq(l3_sel["l4"], l4)]

    metrics = indicators or _default_indicators(l3_base)

    # KPI area — full sell-out backdrop (dims-scoped, never source-filtered).
    kpi_df = scoped[_kpi_mask(scoped)]
    kpi_metric = _norm(kpi_df["metric"].mode().iloc[0]) if not kpi_df.empty else ""

    # Assemble a shared period axis over KPI + every overlay series.
    per_metric = {m: _sum_by_period(l3_sel[_casefold_eq(l3_sel["metric"], m)], grain) for m in metrics}
    kpi_by_period = _sum_by_period(kpi_df, grain)
    keys: set[int] = set(kpi_by_period)
    for d in per_metric.values():
        keys |= set(d)
    axis = sorted(keys)
    x = [_period_label(k, grain) for k in axis]

    kpi = None
    if kpi_by_period:
        kpi = {"metric": kpi_metric or "KPI", "kind": "area",
               "data": [kpi_by_period.get(k, 0.0) for k in axis]}

    series = []
    for m in metrics:
        d = per_metric[m]
        series.append({
            "metric": m,
            "metricType": _norm(l3_base[_casefold_eq(l3_base["metric"], m)]["metric_type"].iloc[0])
            if not l3_base[_casefold_eq(l3_base["metric"], m)].empty else "",
            "kind": "bar" if _is_spend_metric(l3_base, m) else "line",
            "data": [d.get(k) for k in axis],  # None = gap
        })

    years = sorted({int(y) for y in pd.to_numeric(scoped["year"], errors="coerce").dropna().unique()})
    named = ([(kpi_metric or "KPI", kpi_df)] if not kpi_df.empty else []) + \
            [(m, l3_sel[_casefold_eq(l3_sel["metric"], m)]) for m in metrics]
    yearly = _yearly_table(years, named)

    return {
        "l3": l3,
        "grain": grain,
        "x": x,
        "kpi": kpi,
        "series": series,
        "yearly": yearly,
        "options": {
            "grains": grains,
            "l4": _distinct(l3_base, "l4"),
            "indicators": _indicator_options(l3_base),
            "sources": _distinct(l3_base, "source"),
            "brand": _distinct(df, "brand"),
            "channelType": _distinct(df, "channel_type"),
            "provinceGroup": _distinct(df, "province_group"),
        },
    }
