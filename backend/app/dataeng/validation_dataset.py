"""Serialize the modeling long table (2.24) for the Business Validation explorer.

Graphic Walker computes charts client-side, so this hands it the whole per-project
long table (``model_df``) plus three derived columns it can't cheaply derive itself:
``year`` (int), ``period`` (a sortable month/year label), and ``value_yoy`` (the
row's year-over-year % against the same period one year earlier, within the same
factor/metric/dimension cell). A row cap keeps a pathologically wide upload from
shipping millions of rows to the browser.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

import app.agents.dataset_cache as dataset_cache
from app.agents.indicator_metadata import classify_indicator  # noqa: F401  (kept for future column typing)

# fid → semantic/analytic classification for the fixed dimension columns.
_DIMENSIONS = ["l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
               "metric", "metric_type", "source", "brand", "channel_type", "province_group"]
_CELL_KEYS = ["l3", "l4", "metric", "brand", "channel_type", "province_group"]


def _period(year: Any, month: Any) -> str:
    m = pd.to_numeric(pd.Series([month]), errors="coerce").iloc[0]
    if pd.notna(m) and int(m) >= 190001:
        s = str(int(m))
        return f"{s[:4]}-{s[4:6]}"
    y = pd.to_numeric(pd.Series([year]), errors="coerce").iloc[0]
    return "" if pd.isna(y) else str(int(y))


def _with_yoy(df: pd.DataFrame) -> pd.Series:
    """YoY % per (cell, period-within-year): value vs the same month/year-1."""
    val = pd.to_numeric(df["value"], errors="coerce")
    ym = pd.to_numeric(df["month"], errors="coerce")
    has_month = ym.notna()
    # bucket = month-of-year (mm) when monthly, else 0; prior-year key = year-1 + bucket.
    yr = pd.to_numeric(df["year"], errors="coerce")
    mm = (ym % 100).where(has_month, 0)
    keys = df[[c for c in _CELL_KEYS if c in df.columns]].astype("string").fillna("")
    cur = pd.Series(list(zip(*[keys[c] for c in keys.columns], yr, mm)), index=df.index)
    prev = pd.Series(list(zip(*[keys[c] for c in keys.columns], yr - 1, mm)), index=df.index)
    prior_val = pd.Series(val.values, index=cur.values)
    prior_val = prior_val[~prior_val.index.duplicated(keep="first")]
    mapped = prev.map(prior_val)
    yoy = (val - mapped) / mapped.abs() * 100.0
    return yoy.where(mapped.notna() & (mapped != 0))


def _columns(df: pd.DataFrame) -> list[dict]:
    cols: list[dict] = []
    for fid in _DIMENSIONS:
        if fid in df.columns:
            cols.append({"fid": fid, "name": fid, "semanticType": "nominal", "analyticType": "dimension"})
    cols.append({"fid": "year", "name": "year", "semanticType": "ordinal", "analyticType": "dimension"})
    cols.append({"fid": "month", "name": "month", "semanticType": "ordinal", "analyticType": "dimension"})
    cols.append({"fid": "period", "name": "period", "semanticType": "temporal", "analyticType": "dimension"})
    cols.append({"fid": "value", "name": "value", "semanticType": "quantitative", "analyticType": "measure"})
    cols.append({"fid": "value_yoy", "name": "value_yoy", "semanticType": "quantitative", "analyticType": "measure"})
    return cols


def _clean(v: Any) -> Any:
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if v is pd.NA or v is None:
        return None
    return v


def build_validation_dataset(st: object, row_cap: int = 200_000) -> dict:
    df = dataset_cache.model_df(st).copy()
    if df.empty:
        return {"columns": _columns(df), "rows": [], "rowCount": 0, "capped": False, "note": ""}
    df["year"] = pd.to_numeric(df.get("year"), errors="coerce").astype("Int64")
    df["period"] = [_period(y, m) for y, m in zip(df.get("year"), df.get("month"))]
    df["value_yoy"] = _with_yoy(df).round(1)

    capped = len(df) > row_cap
    note = ("" if not capped else
            f"Showing the first {row_cap:,} of {len(df):,} rows — pre-aggregate in the "
            "Data Engine to explore the full set.")
    if capped:
        df = df.iloc[:row_cap]

    cols = _columns(df)
    keep = [c["fid"] for c in cols]
    records = df[[c for c in keep if c in df.columns]].to_dict("records")
    rows = [{k: _clean(v) for k, v in rec.items()} for rec in records]
    return {"columns": cols, "rows": rows, "rowCount": len(rows), "capped": capped, "note": note}
