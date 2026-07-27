"""National aggregation — collapse the per-channel long table to one total model.

The product models a single **national total** (decision 2026-07-23): S2 screening,
OLS and master data all see one model object, ``TOTAL``. Channel-specific drivers
(e-commerce spend, TT new-SKU counts…) survive as their own ``(l4, metric)``
columns of the national frame, so their ROI / L4-contribution stays individually
attributable — only the channel *dimension* is removed, not the channel-specific
factors.

``build_national`` groups the override-applied long table by
``(period, l1..l8, metric, metric_type)`` and aggregates ``value`` across
channel_type / channel / province_group using each indicator's maintained
aggregation (2.1): ``sum`` for spend/volume/count, ``weighted_average`` (weighted
by co-located KPI volume, falling back to a simple mean) for rate/price/index.
Every output row carries ``channel_type = channel = "TOTAL"`` and
``province_group = "National"`` so ``build_model_frame(..., "TOTAL")`` selects them
and ``model_objects`` collapses to ``["TOTAL"]`` with no change to any per-object
loop body.
"""
from __future__ import annotations

import pandas as pd

from app.agents.overrides import resolve_aggregation

# Descriptive columns that identify a national indicator series (the group key).
_GROUP_COLS = ["year", "month", "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
               "metric", "metric_type"]
# Columns collapsed away by the national roll-up.
_COLLAPSED = {"channel_type", "channel", "province_group"}

TOTAL_OBJECT = "TOTAL"


def _kpi_weight_lookup(df: pd.DataFrame) -> dict[tuple, float]:
    """Weight table for weighted averages: total KPI (Y) volume per
    ``(channel_type, province_group, year, month)`` — a rate metric at that
    granularity is weighted by how much of the response sits there."""
    from app.dataeng.validation_query import _kpi_mask
    try:
        kpi = df[_kpi_mask(df)]
    except Exception:  # noqa: BLE001 — no usable KPI just means "no weights"
        return {}
    if kpi.empty:
        return {}
    val = pd.to_numeric(kpi["value"], errors="coerce")
    g = kpi.assign(_w=val).groupby(
        ["channel_type", "province_group", "year", "month"], dropna=False)["_w"].sum()
    return {tuple(k): float(v) for k, v in g.items()}


def _agg_group(sub: pd.DataFrame, method: str, weights: dict[tuple, float]) -> float:
    vals = pd.to_numeric(sub["value"], errors="coerce")
    vals = vals[vals.notna()]
    if vals.empty:
        return float("nan")
    if method == "sum":
        return float(vals.sum())
    if method in ("min", "max"):
        return float(vals.min() if method == "min" else vals.max())
    if method == "weighted_average":
        w = sub.apply(
            lambda r: weights.get((r["channel_type"], r["province_group"], r["year"], r["month"]), 0.0),
            axis=1)
        w = pd.to_numeric(w, errors="coerce").reindex(vals.index).fillna(0.0)
        if float(w.sum()) > 0:
            return float((vals * w).sum() / w.sum())
        return float(vals.mean())  # no weights available → simple mean
    # average / count / distinct_count fall back to a mean of the present values.
    return float(vals.mean())


def build_national(df: pd.DataFrame, st: object | None) -> pd.DataFrame:
    """Collapse ``df`` (per-channel long table) to the national total frame."""
    if df is None or df.empty:
        return df
    missing = [c for c in _GROUP_COLS if c not in df.columns]
    if missing or "value" not in df.columns:
        return df  # not a long table we recognise — leave it untouched

    weights = _kpi_weight_lookup(df)
    brand = ""
    if "brand" in df.columns:
        nonblank = df["brand"].astype("string").str.strip()
        nonblank = nonblank[nonblank.ne("") & nonblank.ne("nan")]
        brand = str(nonblank.iloc[0]) if len(nonblank) else ""

    rows: list[dict] = []
    for key, sub in df.groupby(_GROUP_COLS, dropna=False):
        rec = dict(zip(_GROUP_COLS, key))
        method = resolve_aggregation(st, rec.get("l4", ""), rec.get("metric", ""))
        value = _agg_group(sub, method, weights)
        if value != value:  # NaN → nothing to model here
            continue
        rows.append({
            "task_name": "TOTAL", "brand": brand,
            "province_group": "National", "channel_type": TOTAL_OBJECT, "channel": TOTAL_OBJECT,
            "source": "national", **rec, "value": value,
        })
    if not rows:
        return df.iloc[0:0]
    return pd.DataFrame(rows, columns=[
        "task_name", "brand", "province_group", "channel_type", "channel",
        "year", "month", "source",
        "l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
        "metric_type", "metric", "value",
    ])
