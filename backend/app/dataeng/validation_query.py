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


# DATA-005: the period grains the view can bucket on. Year is always available;
# half-year / quarter / month need a monthly (yyyymm) axis. Half-year and quarter
# keys are yyyy*10 + bucket (unambiguous within a single grain: 20251 = 2025 H1 / Q1).
_SUB_YEAR_GRAINS = ["half_year", "quarter", "month"]


def _has_month_axis(df: pd.DataFrame) -> bool:
    return "month" in df.columns and pd.to_numeric(df["month"], errors="coerce").notna().any()


def _available_grains(df: pd.DataFrame) -> list[str]:
    grains = ["year"]
    if _has_month_axis(df):
        grains += _SUB_YEAR_GRAINS
    return grains


def _period_keys(df: pd.DataFrame, grain: str) -> pd.Series:
    if grain == "year":
        return pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    ym = pd.to_numeric(df["month"], errors="coerce")   # yyyymm
    if grain == "month":
        return ym.astype("Int64")
    y, m = ym // 100, ym % 100
    if grain == "half_year":
        return (y * 10 + ((m > 6).astype("Int64") + 1)).astype("Int64")
    if grain == "quarter":
        return (y * 10 + ((m - 1) // 3 + 1)).astype("Int64")
    return ym.astype("Int64")


def _period_label(key: int, grain: str) -> str:
    k = int(key)
    if grain == "year":
        return str(k)
    if grain == "month":
        return f"{k // 100:04d}-{k % 100:02d}"
    if grain == "half_year":
        return f"{k // 10} H{k % 10}"
    if grain == "quarter":
        return f"{k // 10} Q{k % 10}"
    return str(k)


# DATA-007: how an indicator rolls up across periods/dimensions. The pandas agg name
# for each configured aggregation (weighted_average has no weights here → mean).
_AGG_PANDAS = {
    "sum": "sum", "count": "count", "average": "mean", "min": "min", "max": "max",
    "distinct_count": "nunique", "weighted_average": "mean",
}


def _pandas_agg(aggregation: str) -> str:
    return _AGG_PANDAS.get(aggregation, "sum")


def _metric_meta(st, metric: str) -> dict:
    """DATA-008: an indicator's semantic metadata (unit/format/aggregation/type),
    from the registered Indicator if present, else classified from the name."""
    m = _norm(metric).casefold()
    for ind in getattr(st, "indicators", []) or []:
        if _norm(ind.metric).casefold() == m:
            return {"unit": ind.unit, "numberFormat": ind.number_format,
                    "aggregation": ind.aggregation, "semanticType": ind.semantic_type}
    from app.agents.indicator_metadata import classify_indicator
    meta = classify_indicator(metric)
    return {"unit": meta.unit, "numberFormat": meta.fmt,
            "aggregation": meta.aggregation, "semanticType": meta.metric_type}


def _metric_agg(st, metric: str) -> str:
    return _metric_meta(st, metric)["aggregation"]


def _sum_by_period(sub: pd.DataFrame, grain: str, aggregation: str = "sum") -> dict[int, float]:
    """Roll a single indicator's rows up to per-period values using its configured
    aggregation (DATA-007) — a rate/coverage metric averages, spend/volume sums."""
    if sub.empty:
        return {}
    keys = _period_keys(sub, grain)
    vals = pd.to_numeric(sub["value"], errors="coerce")
    grp = (pd.DataFrame({"k": keys, "v": vals}).dropna(subset=["k"])
           .groupby("k")["v"].agg(_pandas_agg(aggregation)))
    return {int(k): round(float(v), 2) for k, v in grp.items()}


def _apply_dims(df: pd.DataFrame, dims: dict[str, Optional[list[str]]]) -> pd.DataFrame:
    out = df
    for key, col in _DIM_COLS.items():
        wanted = dims.get(key)
        if wanted and col in out.columns:
            out = out[out[col].astype("string").str.strip().isin([_norm(v) for v in wanted])]
    return out


# ── DATA-005 · time-window scoping + comparison ───────────
def _in_span(df: pd.DataFrame, start_ym: int, end_ym: int) -> pd.Series:
    """Boolean mask of rows whose yyyymm month falls in [start_ym, end_ym]."""
    ym = pd.to_numeric(df["month"], errors="coerce")
    return (ym >= start_ym) & (ym <= end_ym)


def _sum_in_span(df: pd.DataFrame, start_ym: int, end_ym: int, aggregation: str = "sum") -> float:
    """Aggregate one indicator's values over a month span with its configured
    aggregation (DATA-007) — the window total a rate averages, a spend sums."""
    sub = df[_in_span(df, start_ym, end_ym)]
    if sub.empty:
        return 0.0
    vals = pd.to_numeric(sub["value"], errors="coerce").dropna()
    if vals.empty:
        return 0.0
    return round(float(getattr(vals, _pandas_agg(aggregation))()), 2)


def _window_comparison(st, scoped_full: pd.DataFrame, w, kpi_df: pd.DataFrame,
                       kpi_metric: str, metrics: list[str]) -> Optional[dict]:
    """Current-window vs comparison-window value (+ % change) per metric, each rolled
    up with its own aggregation (DATA-007) and carrying its display metadata (DATA-008).

    Compares equal-length, same-season spans (the comparison bounds are derived by
    FND-002 `normalize_window`). Returns None if the window has no usable current span.
    """
    from app.agents.time_windows import int_to_ym, is_equal_length, ym_to_int

    cs, ce = ym_to_int(w.current_start), ym_to_int(w.current_end)
    if cs is None or ce is None:
        return None
    ps, pe = ym_to_int(w.comparison_start), ym_to_int(w.comparison_end)
    has_comp = ps is not None and pe is not None

    def _delta(cur: float, prev: Optional[float]) -> Optional[float]:
        if prev is None or prev == 0:
            return None
        return round((cur - prev) / prev * 100, 1)

    rows = []
    named = ([(kpi_metric or "KPI", kpi_df)] if not kpi_df.empty else []) + \
            [(m, scoped_full[_casefold_eq(scoped_full["metric"], m)]) for m in metrics]
    for name, sub in named:
        meta = _metric_meta(st, name)
        agg = meta["aggregation"]
        cur = _sum_in_span(sub, cs, ce, agg)
        prev = _sum_in_span(sub, ps, pe, agg) if has_comp else None
        rows.append({"metric": name, "current": cur, "comparison": prev,
                     "deltaPct": _delta(cur, prev), "unit": meta["unit"],
                     "numberFormat": meta["numberFormat"], "aggregation": agg})
    return {
        "name": w.name,
        "current": {"start": int_to_ym(cs), "end": int_to_ym(ce),
                    "label": f"{int_to_ym(cs)} → {int_to_ym(ce)}"},
        "comparison": ({"start": int_to_ym(ps), "end": int_to_ym(pe),
                        "label": f"{int_to_ym(ps)} → {int_to_ym(pe)}"} if has_comp else None),
        "comparisonType": w.comparison_type,
        "equalLength": is_equal_length(w),
        "rows": rows,
    }


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


def _yearly_table(years: list[int], named_masks: list[tuple[str, pd.DataFrame, dict]]) -> dict:
    """Per-year values per indicator. Each entry is (name, rows, meta); the metric's
    aggregation rolls a rate up as a yearly average not a sum (DATA-007), and its
    unit/format ride along so the table formats each row correctly (DATA-008)."""
    rows = []
    for name, sub, meta in named_masks:
        by_year = _sum_by_period(sub, "year", meta["aggregation"])
        values = [by_year.get(y) for y in years]
        rows.append({"metric": name, "values": values, "yoy": _yoy(values),
                     "unit": meta["unit"], "numberFormat": meta["numberFormat"]})
    return {"years": years, "rows": rows}


# DATA-004: the drilldown levels below L3, in cascade order.
_DRILL_LEVELS = ["l4", "l5", "l6", "l7", "l8"]


def validation_series(
    st,
    *,
    l3: str,
    l4: Optional[str] = None,
    l5: Optional[str] = None,
    l6: Optional[str] = None,
    l7: Optional[str] = None,
    l8: Optional[str] = None,
    indicators: Optional[list[str]] = None,
    grain: str = "month",
    sources: Optional[list[str]] = None,
    brand: Optional[list[str]] = None,
    channel_type: Optional[list[str]] = None,
    province_group: Optional[list[str]] = None,
    window=None,
    kpi_metric_req: Optional[str] = None,
) -> dict:
    """Compute the KPI area + overlay series + yearly/YoY table for one L3, drilled
    to an L4–L8 path (DATA-004). Each level's options cascade from the levels above
    it, and the same level path scopes the chart, table, indicators and breadcrumb.

    DATA-005: when ``window`` (a TimeWindow) is given, the whole view is scoped to its
    current span and a current-vs-comparison block (equal-length, same-season) is
    returned alongside the standard yearly table."""
    df = model_df(st)
    dims = {"brand": brand, "channelType": channel_type, "provinceGroup": province_group}
    scoped_full = _apply_dims(df, dims)

    # DATA-005: scope every downstream frame to the window's current span (if any).
    scoped = scoped_full
    win_cur_span: Optional[tuple[int, int]] = None
    if window is not None and _has_month_axis(scoped_full):
        from app.agents.time_windows import ym_to_int
        cs, ce = ym_to_int(window.current_start), ym_to_int(window.current_end)
        if cs is not None and ce is not None:
            scoped = scoped_full[_in_span(scoped_full, cs, ce)]
            win_cur_span = (cs, ce)

    grains = _available_grains(scoped)
    if grain not in grains:
        grain = grains[-1] if grains else "year"

    # The L3 slice (dims applied; source/level/indicator NOT yet) drives filter options.
    l3_base = scoped[_casefold_eq(scoped["l3"], l3)] if l3 else scoped.iloc[0:0]

    # DATA-004 cascade. `opt_bases[lvl]` = l3_base filtered by every *higher* selected
    # level, so that level's option list reflects the current drill path; `filter_base`
    # is l3_base narrowed by the whole selected L4–L8 path (no source) and drives the
    # indicator set. A level whose value isn't set simply doesn't narrow the subset.
    level_vals = {"l4": l4, "l5": l5, "l6": l6, "l7": l7, "l8": l8}
    opt_bases: dict[str, pd.DataFrame] = {}
    cur = l3_base
    for lvl in _DRILL_LEVELS:
        opt_bases[lvl] = cur
        v = level_vals[lvl]
        if v and lvl in cur.columns:
            cur = cur[_casefold_eq(cur[lvl], v)]
    filter_base = cur

    # Selection for the drawn series: the same level path + the source filter (which
    # scopes the overlay only, never the KPI backdrop).
    l3_sel = l3_base
    if sources:
        l3_sel = l3_sel[l3_sel["source"].astype("string").str.strip().isin([_norm(s) for s in sources])]
    for lvl in _DRILL_LEVELS:
        v = level_vals[lvl]
        if v and lvl in l3_sel.columns:
            l3_sel = l3_sel[_casefold_eq(l3_sel[lvl], v)]

    metrics = indicators or _default_indicators(filter_base)

    # KPI area — full sell-out backdrop (dims-scoped, never source-filtered).
    # DATA-009: a project may publish both a Volume KPI and a Value KPI; expose both
    # as options and let the caller pick which is the backdrop (default: prefer Volume,
    # so switching the chart never changes the OLS default Y).
    kpi_all = scoped[_kpi_mask(scoped)]
    kpi_metric_options = _distinct(kpi_all, "metric")
    kpi_metric = ""
    if kpi_metric_req and any(_norm(kpi_metric_req).casefold() == m.casefold() for m in kpi_metric_options):
        kpi_metric = next(m for m in kpi_metric_options if m.casefold() == _norm(kpi_metric_req).casefold())
    if not kpi_metric and kpi_metric_options:
        volume = [m for m in kpi_metric_options if _metric_meta(st, m)["semanticType"] == "kpi_volume"]
        kpi_metric = volume[0] if volume else kpi_metric_options[0]
    kpi_df = kpi_all[_casefold_eq(kpi_all["metric"], kpi_metric)] if kpi_metric else kpi_all.iloc[0:0]

    # DATA-007/008: each metric's aggregation + display metadata, resolved once.
    metric_meta = {m: _metric_meta(st, m) for m in metrics}
    kpi_agg = _metric_agg(st, kpi_metric) if kpi_metric else "sum"

    # Assemble a shared period axis over KPI + every overlay series, each rolled up
    # with its own aggregation (a rate averages per period, spend/volume sums).
    per_metric = {m: _sum_by_period(l3_sel[_casefold_eq(l3_sel["metric"], m)], grain,
                                    metric_meta[m]["aggregation"]) for m in metrics}
    kpi_by_period = _sum_by_period(kpi_df, grain, kpi_agg)
    keys: set[int] = set(kpi_by_period)
    for d in per_metric.values():
        keys |= set(d)
    axis = sorted(keys)
    x = [_period_label(k, grain) for k in axis]

    kpi = None
    if kpi_by_period:
        km = _metric_meta(st, kpi_metric) if kpi_metric else {}
        kpi = {"metric": kpi_metric or "KPI", "kind": "area",
               "data": [kpi_by_period.get(k, 0.0) for k in axis],
               "unit": km.get("unit", ""), "numberFormat": km.get("numberFormat", "number"),
               "aggregation": kpi_agg, "semanticType": km.get("semanticType", "")}

    series = []
    for m in metrics:
        d = per_metric[m]
        mm = metric_meta[m]
        series.append({
            "metric": m,
            "metricType": _norm(filter_base[_casefold_eq(filter_base["metric"], m)]["metric_type"].iloc[0])
            if not filter_base[_casefold_eq(filter_base["metric"], m)].empty else "",
            "kind": "bar" if _is_spend_metric(filter_base, m) else "line",
            "data": [d.get(k) for k in axis],  # None = gap
            # DATA-008: display metadata so the UI formats the axis/tooltip correctly.
            "unit": mm["unit"], "numberFormat": mm["numberFormat"],
            "aggregation": mm["aggregation"], "semanticType": mm["semanticType"],
        })

    years = sorted({int(y) for y in pd.to_numeric(scoped["year"], errors="coerce").dropna().unique()})
    kpi_meta = _metric_meta(st, kpi_metric) if kpi_metric else {"aggregation": "sum", "unit": "", "numberFormat": "number"}
    named = ([(kpi_metric or "KPI", kpi_df, kpi_meta)] if not kpi_df.empty else []) + \
            [(m, l3_sel[_casefold_eq(l3_sel["metric"], m)], metric_meta[m]) for m in metrics]
    yearly = _yearly_table(years, named)

    # DATA-005 comparison: current-window vs comparison-window totals (equal-length,
    # same-season). Computed from the FULL (un-window-scoped) frame so the comparison
    # span's rows — which lie outside the current span — are available.
    comparison = None
    if window is not None and win_cur_span is not None:
        kpi_full = scoped_full[_kpi_mask(scoped_full)]
        # overlay drivers under the same L3 (+ drill path) but full time range.
        drivers = scoped_full[_casefold_eq(scoped_full["l3"], l3)] if l3 else scoped_full.iloc[0:0]
        for lvl in _DRILL_LEVELS:
            if level_vals[lvl] and lvl in drivers.columns:
                drivers = drivers[_casefold_eq(drivers[lvl], level_vals[lvl])]
        comparison = _window_comparison(st, drivers, window, kpi_full, kpi_metric, metrics)

    # DATA-004 breadcrumb: the resolved L3 → L4…L8 path, shared by chart/table/export.
    breadcrumb = ([{"level": "L3", "value": l3}] if l3 else []) + [
        {"level": lvl.upper(), "value": _norm(level_vals[lvl])}
        for lvl in _DRILL_LEVELS if level_vals[lvl]
    ]

    return {
        "l3": l3,
        "grain": grain,
        "x": x,
        "kpi": kpi,
        "kpiMetric": kpi_metric,
        "series": series,
        "yearly": yearly,
        "comparison": comparison,
        "breadcrumb": breadcrumb,
        "options": {
            "grains": grains,
            # DATA-009: the KPI backdrop choices (Volume / Value) the chart can switch.
            "kpiMetrics": [{"metric": m, "semanticType": _metric_meta(st, m)["semanticType"]}
                           for m in kpi_metric_options],
            # Each level's options cascade from the levels above it; an empty list
            # tells the UI to hide that level (Not Available) rather than draw it.
            "l4": _distinct(opt_bases["l4"], "l4"),
            "l5": _distinct(opt_bases["l5"], "l5"),
            "l6": _distinct(opt_bases["l6"], "l6"),
            "l7": _distinct(opt_bases["l7"], "l7"),
            "l8": _distinct(opt_bases["l8"], "l8"),
            "indicators": _indicator_options(filter_base),
            "sources": _distinct(l3_base, "source"),
            "brand": _distinct(df, "brand"),
            "channelType": _distinct(df, "channel_type"),
            "provinceGroup": _distinct(df, "province_group"),
        },
    }
