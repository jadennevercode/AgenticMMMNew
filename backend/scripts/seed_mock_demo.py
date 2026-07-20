"""Seed a MOCK project with synthetic modeling data — no reference/ needed.

Builds a 19-column long table (the 2.24 schema) with L4–L8 depth, multiple
channels/geos and 24 monthly periods, publishes it through the real Data-Engine
path, and sets a Brand×Channel×Geo profile. Lets us actually exercise BIZ-001 /
FND-001 / DATA-004 / DATA-005 on real data in an environment with no reference set.

Run:  PYTHONPATH=. .venv/bin/python scripts/seed_mock_demo.py
Then restart the backend so the running server picks up the new project.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.indicator_metadata import (  # noqa: E402
    INDICATOR_META_RULE_VERSION, classify_indicator,
)
from app.config import get_settings  # noqa: E402
from app.dataeng import assets as asset_svc  # noqa: E402
from app.domain.models import (  # noqa: E402
    DataAssetVersion, Indicator, IndustryRef, ModelScope, ModelScopeDimension,
    ProjectProfile,
)
from app.ingest.dataset import COLUMN_NAMES  # noqa: E402
from app.store.state import get_store  # noqa: E402
from scripts.seed_dataprocess_demo import build_factor_tree  # noqa: E402


def publish_direct(pid: str, st, df: pd.DataFrame) -> None:
    """Publish a long table WITHOUT dbt (the Fusion binary isn't available here):
    write the parquet, register a published asset version, and register indicators
    with FND-001 semantic metadata — the same shape the real publish path produces."""
    asset = asset_svc.create_asset(st, name="mock", description="Synthetic mock dataset.")
    rel = Path("projects") / pid / "assets" / asset.id / "v1.parquet"
    abs_path = get_settings().data_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(abs_path, index=False)
    asset.versions = [DataAssetVersion(version=1, parquetPath=str(rel),
                                       rowCount=len(df), columns=list(df.columns))]
    asset.status = "published"
    asset.latest_version = 1

    # Register one indicator per (l1..l4, metric), classified for FND-001 metadata.
    st.indicators = []
    paths = df[["l1", "l2", "l3", "l4", "metric", "metric_type"]].drop_duplicates()
    for i, r in enumerate(paths.itertuples(index=False)):
        meta = classify_indicator(r.metric)
        st.indicators.append(Indicator(
            id=f"ind-{asset.id}-{i}", metric=r.metric, metricType=r.metric_type,
            l1=r.l1, l2=r.l2, l3=r.l3, l4=r.l4,
            semanticType=meta.metric_type, unit=meta.unit, currency=meta.currency,
            aggregation=meta.aggregation, numberFormat=meta.fmt, source="data_upload",
            ruleVersion=INDICATOR_META_RULE_VERSION, assetId=asset.id, assetName=asset.name,
            rows=0, treeGrounded=True,
        ))

PROJECT_NAME = "Mock MMM · Brand×Channel×Geo"
BRAND = "脉动 Mizone"
CHANNELS = ["MT", "TT", "EC"]
GEOS = ["East", "West"]
MONTHS = [(y, m) for y in (2024, 2025) for m in range(1, 13)]  # 24 monthly periods

# Factor paths with genuine L4–L8 depth so the drilldown cascade has something to
# drill. (l1, l2, l3, l4, l5, l6, l7, l8, metric, role)
PATHS = [
    ("KPI", "销量", "Volume", "", "", "", "", "", "本品销量", "Y"),
    ("KPI", "销额", "Value", "", "", "", "", "", "本品销售额", "Y"),   # DATA-009: a Value KPI
    ("MARKETING FACTOR", "数字营销", "线上投放", "信息流", "抖音", "品牌广告", "开屏", "竖版", "投放花费", "spending"),
    ("MARKETING FACTOR", "数字营销", "线上投放", "信息流", "抖音", "效果广告", "", "", "投放花费", "spending"),
    ("MARKETING FACTOR", "数字营销", "线上投放", "信息流", "腾讯", "品牌广告", "", "", "投放花费", "spending"),
    ("MARKETING FACTOR", "数字营销", "线上投放", "电商站内", "天猫", "直通车", "", "", "投放花费", "spending"),
    ("MARKETING FACTOR", "传统媒体", "电视", "TVC", "", "", "", "", "GRP", "X"),
    ("COMMERCIAL FACTOR", "渠道", "分销", "商超", "", "", "", "", "NDWD覆盖率", "X"),
]


def build_mock_df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows = []
    for ci, channel in enumerate(CHANNELS):
        for gi, geo in enumerate(GEOS):
            for (y, m) in MONTHS:
                ym = y * 100 + m
                season = 1.0 + 0.25 * np.sin((m - 1) / 12 * 2 * np.pi)
                # total spend this cell drives the KPI (so charts show real signal)
                spend_paths = [p for p in PATHS if p[9] == "spending"]
                spend_vals = {}
                for p in spend_paths:
                    base = 8000 * (1 + 0.3 * ci) * (1 + 0.2 * gi)
                    spend_vals[p] = round(base * season * (1 + rng.normal(0, 0.1)), 1)
                total_spend = sum(spend_vals.values())
                for p in PATHS:
                    l1, l2, l3, l4, l5, l6, l7, l8, metric, role = p
                    if role == "Y":
                        vol = 50000 * (1 + 0.4 * ci) * season + 0.9 * total_spend + rng.normal(0, 1500)
                        # Value KPI ≈ volume × unit price; Volume KPI is the raw count.
                        val = round(vol * 3.5, 1) if metric == "本品销售额" else round(vol, 1)
                    elif role == "spending":
                        val = spend_vals[p]
                    elif metric == "NDWD覆盖率":
                        val = round(min(99.0, 60 + 5 * ci + rng.normal(0, 3)), 1)  # a % rate
                    else:  # GRP index
                        val = round(200 * season * (1 + rng.normal(0, 0.15)), 1)
                    rows.append({
                        "task_name": "mock", "brand": BRAND, "province_group": geo,
                        "channel_type": channel, "channel": channel,
                        "year": y, "month": ym, "source": "mock_upload",
                        "l1": l1, "l2": l2, "l3": l3, "l4": l4, "l5": l5, "l6": l6,
                        "l7": l7, "l8": l8, "metric_type": role, "metric": metric,
                        "value": val,
                    })
    return pd.DataFrame(rows)[COLUMN_NAMES]


def main() -> None:
    df = build_mock_df()
    print(f"mock long table: {len(df):,} rows · {df['month'].nunique()} months · "
          f"{df['channel_type'].nunique()} channels · {df['province_group'].nunique()} geos")

    store = get_store()
    existing = next((m for m in store.list_meta() if m.name == PROJECT_NAME), None)
    if existing is not None:
        store.reset(existing.id)
        pid = existing.id
    else:
        meta = store.create(PROJECT_NAME, BRAND,
                            IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
                            kpi="Sell-out Volume")
        pid = meta.id
    st = store.get(pid)
    print(f"project: {pid}")

    # BIZ-001 profile: Brand × Channel × Geo
    st.profile = ProjectProfile(
        projectIntro="Synthetic Mizone MMM to exercise Brand×Channel×Geo scope, "
                     "indicator metadata, L4–L8 drilldown and custom time windows.",
        timeGranularity="Month",
        modelScope=ModelScope(dimensions=[
            ModelScopeDimension(name="Brand", values=[BRAND]),
            ModelScopeDimension(name="Channel", values=CHANNELS),
            ModelScopeDimension(name="Geo", values=GEOS),
        ], rows=[]),
        sourceOrigin="mock seed",
    )
    st.factor_tree = build_factor_tree(df)

    publish_direct(pid, st, df)

    # Produce the Business Validation artifact deterministically (no LLM) so the UI
    # can render the L4–L8 drilldown + time-window controls on this data.
    from app.agents.dataset_cache import invalidate_project, model_df
    from app.agents.data import _anomalies, _bv_groups
    from app.agents.registry import build_engine
    from app.dataeng import validation_query as vq
    from scripts.seed_dataprocess_demo import seed_s1

    invalidate_project(pid)
    seed_s1(st)                       # mark S1 done so the workflow is navigable
    mdf = model_df(st)
    kpi_df = mdf[vq._kpi_mask(mdf)]
    kpi_metric = str(kpi_df["metric"].mode().iloc[0]) if not kpi_df.empty else ""
    groups = _bv_groups(st, mdf)
    anomalies = _anomalies(mdf)
    eng = build_engine()
    # advance S2 up to 2.3 so the deliverable is reachable, then produce the artifact.
    for tid in ("2.1", "2.2", "2.2d", "2.3"):
        if tid in st.tasks:
            st.tasks[tid].status, st.tasks[tid].progress = "done", 100.0
    eng.produce(st, "a-business-validation", state="proposed", agent="data", body={
        "kpiMetric": kpi_metric, "groups": groups,
        "anomalies": [{"channel": a["channel"], "year": a["year"], "growthPct": a["growth_pct"]}
                      for a in anomalies],
        "note": "Mock data — filter by L4–L8 sub-factor, pick a time window, and read each "
                "factor against sell-out.",
    })
    store.save(pid)

    # verify model_df now serves the mock data
    from app.agents.dataset_cache import invalidate_project, model_df
    invalidate_project(pid)
    mdf = model_df(st)
    print(f"published OK · model_df rows: {len(mdf):,} · indicators: {len(st.indicators)}")
    print("sample semantic metadata (FND-001):")
    for ind in st.indicators[:6]:
        print(f"  {ind.metric:12s} role={ind.metric_type:9s} semantic={ind.semantic_type:11s} "
              f"agg={ind.aggregation:8s} unit={ind.unit!r}")
    print(f"\nDONE. Restart backend, then open project '{pid}'.")


if __name__ == "__main__":
    main()
