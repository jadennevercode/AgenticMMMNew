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

import numpy as np
import pandas as pd

import app.agents.dataset_cache as dataset_cache

# fid → semantic/analytic classification for the fixed dimension columns.
_DIMENSIONS = ["l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8",
               "metric", "metric_type", "source", "brand", "channel_type", "province_group"]
_CELL_KEYS = ["l3", "l4", "metric", "brand", "channel_type", "province_group"]


def _period(df: pd.DataFrame) -> pd.Series:
    """Vectorized period label over the whole frame: "YYYY-MM" for monthly rows
    (month as yyyymm >= 190001), else the year as a string, else ""."""
    m = pd.to_numeric(df.get("month"), errors="coerce")
    y = pd.to_numeric(df.get("year"), errors="coerce")
    has_month = m.notna() & (m >= 190001)
    m_str = m.astype("Int64").astype("string")
    monthly = m_str.str.slice(0, 4) + "-" + m_str.str.slice(4, 6)
    yearly = y.astype("Int64").astype("string")
    return monthly.where(has_month, yearly).fillna("")


def _with_yoy(df: pd.DataFrame) -> pd.Series:
    """YoY % per (cell, period-within-year): value vs the same month/year-1.

    When a cell/period has multiple source rows (e.g. multiple published Data
    Engine assets contribute the same cell), the prior-year value is taken from
    the first row after a stable sort by cell keys + year + month, so the result
    is deterministic regardless of the incoming row order.
    """
    val = pd.to_numeric(df["value"], errors="coerce")
    ym = pd.to_numeric(df["month"], errors="coerce")
    has_month = ym.notna()
    # bucket = month-of-year (mm) when monthly, else 0; prior-year key = year-1 + bucket.
    yr = pd.to_numeric(df["year"], errors="coerce")
    mm = (ym % 100).where(has_month, 0)
    keys = df[[c for c in _CELL_KEYS if c in df.columns]].astype("string").fillna("")
    cur = pd.Series(list(zip(*[keys[c] for c in keys.columns], yr, mm)), index=df.index)
    prev = pd.Series(list(zip(*[keys[c] for c in keys.columns], yr - 1, mm)), index=df.index)

    sort_cols = list(keys.columns)
    sort_key = keys.copy()
    sort_key["__yr"] = yr
    sort_key["__mm"] = mm
    order = sort_key.sort_values(sort_cols + ["__yr", "__mm"], kind="mergesort").index

    prior_val = pd.Series(val.loc[order].values, index=cur.loc[order].values)
    prior_val = prior_val[~prior_val.index.duplicated(keep="first")]
    mapped = prev.map(prior_val)
    with np.errstate(divide="ignore", invalid="ignore"):
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
    df["period"] = _period(df)
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
