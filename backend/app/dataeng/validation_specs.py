"""Generate the default explorer tab per FactorTree L3 for Business Validation.

Each non-KPI L3 gets one preset tab that mirrors today's fixed chart: the sell-out
KPI metric as the backdrop (``yKpi``) and that factor's default indicators as the
overlay (``yOverlay``), drawn as bars for spend-type factors and lines otherwise.
The shape is app-owned and compact; the frontend compiles it into a Graphic Walker
chart, so this module never depends on GW's internal spec version.
"""
from __future__ import annotations

import pandas as pd

from app.agents import dataset_cache
from app.dataeng import validation_query as vq


def _kpi_metric(df: pd.DataFrame) -> str:
    kpi = df[vq._kpi_mask(df)]
    if kpi.empty:
        return ""
    return str(kpi["metric"].mode().iloc[0])


def default_specs(st: object) -> list[dict]:
    df = dataset_cache.model_df(st)
    if df.empty:
        return []
    kpi_metric = _kpi_metric(df)
    overlay = df[~vq._kpi_mask(df)]
    combo = (overlay[["l1", "l2", "l3"]].astype("string").apply(lambda s: s.str.strip())
             .dropna(subset=["l3"]).drop_duplicates())
    combo = combo[combo["l3"].str.len() > 0].sort_values(["l1", "l2", "l3"])

    specs: list[dict] = []
    for _, row in combo.iterrows():
        l3 = row["l3"] or ""
        sub = df[vq._casefold_eq(df["l3"], l3)]
        indicators = vq._default_indicators(sub)
        sub_overlay = overlay[vq._casefold_eq(overlay["l3"], l3)]
        is_spend = bool(
            sub_overlay["metric_type"].astype("string").str.strip().str.casefold()
            .isin(vq._SPEND_TYPES).any()
        )
        specs.append({
            "specId": f"factor::{l3}",
            "l3": l3,
            "title": f"{row['l2'] or ''} › {l3}".strip(" ›"),
            "encoding": {
                "x": "period",
                "yKpi": kpi_metric,
                "yOverlay": indicators,
                "overlayKind": "bar" if is_spend else "line",
            },
            "filter": {"l3": l3},
        })
    return specs
