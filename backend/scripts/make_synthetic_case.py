"""Generate a complete synthetic MMM case that shares nothing with the Danone data.

The seeded reference case is the only end-to-end case the product has, and it is
also the case every default, keyword list and benchmark in the codebase was written
against. That makes it useless as a test of whether the product works on *someone
else's* data: a hardcoded 本品销量 keyword, a Danone ROI band or an
``l1 == 'MARKETING FACTOR'`` literal all pass silently there and fail on a real
client. This builds the opposite: a case chosen to share no vocabulary with it.

* **Industry**: skincare, not beverage.
* **Taxonomy**: L1 labels are ``Business Outcome / Media / Trade / Market`` — none
  of the three literals ``pivot`` defaults to. Roles are carried **only** by the
  documented ``metric_type ∈ {Y, spending, X}`` contract, which is what the Data
  Engine actually emits, so anything that resolves roles by keyword instead of by
  tag is exposed rather than accommodated.
* **Names**: English throughout. No 本品 / 花费 / 箱数 / 销量.
* **Shape**: 2 products × 4 channels = 8 model objects, 36 months, 3 regions.
* **National rows**: the paid-media factors carry **no channel_type** — they are
  bought nationally and drive every channel. A per-channel model that cannot see
  them is missing most of its media, which is exactly the failure this case exists
  to catch.
* **Market rows**: a ``Competitor Set`` brand with spend but no response, so it can
  never be a model object and its rows must be shared into every product's model.

The response is generated from a known linear model over the drivers, so a fit that
recovers positive spend coefficients is evidence the pipeline works — not just that
it ran.

    PYTHONPATH=. .venv/bin/python scripts/make_synthetic_case.py [--project-id ID]
"""
from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

PROJECT_ID = "aurelia-skincare"
PROJECT_NAME = "Aurelia Skincare · MMM 2026"
BRAND = "Aurelia"
INDUSTRY = ("beauty", "skincare", "facial-care")

PRODUCTS = ["Aurelia Daily", "Aurelia Pro"]
MARKET_BRAND = "Competitor Set"
CHANNELS = ["Ecommerce", "Pharmacy", "Department", "Salon"]
REGIONS = ["North", "East", "South"]
MONTHS = [y * 100 + m for y in (2022, 2023, 2024) for m in range(1, 13)]  # 36

# (l1, l2, l3, l4) → [(metric, metric_type, scope)]
#   scope "national"  — no channel_type, no brand: bought once, drives everything
#   scope "channel"   — per channel × product × region
#   scope "market"    — no channel_type, brand = Competitor Set
FACTORS: list[tuple[tuple[str, str, str, str], list[tuple[str, str, str]]]] = [
    (("Business Outcome", "Sales", "Sell-out", "Net Sales"),
     [("Net Sales Units", "Y", "channel"), ("Net Sales Value", "Y", "channel")]),

    (("Media", "Paid", "Video", "Connected TV"),
     [("CTV Spend", "spending", "national"), ("CTV Reach", "X", "national")]),
    (("Media", "Paid", "Video", "Online Video"),
     [("OLV Spend", "spending", "national"), ("OLV Impressions", "X", "national")]),
    (("Media", "Paid", "Social", "Influencer"),
     [("Influencer Spend", "spending", "national"), ("Influencer Posts", "X", "national")]),
    (("Media", "Paid", "Search", "Paid Search"),
     [("Search Spend", "spending", "national"), ("Search Clicks", "X", "national")]),
    (("Media", "Owned", "CRM", "Loyalty Program"),
     [("Loyalty Members", "X", "national")]),

    (("Trade", "Retail", "Distribution", "Store Coverage"),
     [("Active Doors", "X", "channel")]),
    (("Trade", "Retail", "Promotion", "Price Promotion"),
     [("Promo Spend", "spending", "channel"), ("Promo Depth", "X", "channel")]),
    (("Trade", "Retail", "Visibility", "Shelf Display"),
     [("Display Spend", "spending", "channel"), ("Shelf Share", "X", "channel")]),
    (("Trade", "Service", "Sampling", "In-store Sampling"),
     [("Sampling Events", "X", "channel")]),

    (("Market", "Competition", "Rival Activity", "Competitor Media"),
     [("Competitor Spend", "spending", "market")]),
    (("Market", "Competition", "Rival Activity", "Competitor Price"),
     [("Competitor Price Index", "X", "market")]),
    (("Market", "Environment", "Seasonality", "Category Demand"),
     [("Category Index", "X", "national")]),
]

# Ground truth, expressed the way the engine decomposes: each driver's **share of
# sales**. `_decomposition` reports `coef · mean(transformed_x) / mean(Y)`, so
# generating the response as `baseline + Σ share·Y̅·(transformed/mean(transformed))`
# means a correct fit recovers these numbers directly — the case can be checked, not
# just run. Shares are chosen to look like a real skincare mix: a little over half
# organic, a quarter paid media, the rest trade.
BASELINE_SHARE = 0.40
CONTRIBUTION_SHARE: dict[str, float] = {
    "CTV Spend": 0.09, "OLV Spend": 0.12, "Influencer Spend": 0.07, "Search Spend": 0.09,
    "Promo Spend": 0.09, "Display Spend": 0.05,
    "Active Doors": 0.06, "Shelf Share": 0.03, "Sampling Events": 0.02,
    "Loyalty Members": 0.02,
    "Competitor Spend": -0.03,   # a rival outspending us costs sales
    "Competitor Price Index": 0.02,  # a rival pricing up wins us some
    # Deliberately zero: a plausible-looking factor that does nothing. The model
    # should report it insignificant rather than manufacture an effect for it.
    "Category Index": 0.0,
}

# Exposure metrics are generated FROM their spend sibling, so they are genuinely
# collinear with it and carry no independent effect — the shape that makes VIF and
# the significance tests earn their keep instead of always passing.
EXPOSURE_OF: dict[str, str] = {
    "CTV Reach": "CTV Spend",
    "OLV Impressions": "OLV Spend",
    "Influencer Posts": "Influencer Spend",
    "Search Clicks": "Search Spend",
    "Promo Depth": "Promo Spend",
}

# Which source each factor arrived from — one published asset per source, the way a
# real project's data lands (media agency file, retailer feed, panel subscription…).
SOURCE_OF = {
    "Media": "Media agency export",
    "Trade": "Retail partner feed",
    "Market": "Syndicated panel",
    "Business Outcome": "Sell-out report",
}


def _season(i: int, phase: float = 0.0) -> float:
    return 1.0 + 0.28 * math.sin(2 * math.pi * ((i % 12) / 12.0) + phase)


def _scale(metric: str) -> float:
    m = metric.lower()
    if "spend" in m:
        return 800_000.0
    if "impression" in m or "reach" in m or "clicks" in m or "members" in m:
        return 12_000_000.0
    if "doors" in m:
        return 4_200.0
    if "index" in m or "share" in m or "depth" in m:
        return 45.0
    if "posts" in m or "events" in m:
        return 130.0
    return 1_000.0


def _driver_series(rng: np.random.Generator, metric: str, n: int) -> np.ndarray:
    """A plausible driver: its own flighting, its own bursts, never negative.

    Each driver gets its **own seasonal phase**, derived from its name so the case is
    reproducible. Real media plans are not flighted identically — TV runs to one
    calendar, search to another — and generating them co-seasonal made every national
    driver a near-copy of every other, so VIF condemned the whole media block at once
    for a collinearity the generator had invented rather than the data having it.
    """
    base = _scale(metric)
    phase = (sum(ord(c) for c in metric) % 12) / 12.0 * 2 * math.pi
    season = np.array([_season(i, phase) for i in range(n)])
    bursts = rng.random(n) < 0.3
    level = base * season * rng.uniform(0.55, 1.45, n)
    level[bursts] *= rng.uniform(1.5, 2.6, int(bursts.sum()))
    return np.maximum(level, base * 0.05)


# How tightly an exposure tracks the spend that bought it. Real delivery efficiency
# drifts — CPMs move, inventory mix changes — so impressions are correlated with
# spend, not a copy of it. `Search Clicks` is the deliberate exception: clicks track
# search spend almost exactly, which is the genuine redundancy VIF exists to catch,
# and it should be the pair the screening flags rather than every pair at once.
_EXPOSURE_DRIFT: dict[str, float] = {"Search Clicks": 0.03}
_DEFAULT_DRIFT = 0.30


def _exposure_from(rng: np.random.Generator, spend: np.ndarray, metric: str) -> np.ndarray:
    """An exposure series bought by that spend: proportional, with drifting efficiency."""
    n = spend.size
    scale = _scale(metric) / max(float(np.mean(spend)), 1e-9)
    drift = _EXPOSURE_DRIFT.get(metric, _DEFAULT_DRIFT)
    # A slow random walk in efficiency, plus per-period delivery noise.
    walk = np.cumsum(rng.normal(0.0, drift / 3.0, n))
    efficiency = np.exp(walk - walk.mean()) * rng.normal(1.0, drift / 2.0, n)
    return np.maximum(spend * scale * efficiency, 0.0)


def _mmm_response(drivers: dict[str, np.ndarray], mean_y: float,
                  rng: np.random.Generator) -> np.ndarray:
    """The response, generated the way the engine decomposes it.

    Each driver is put through the engine's own adstock → Hill transform with the
    defaults ``run_mmm`` uses (decay 0.5, half = mean of the adstocked series), then
    scaled so its mean contribution is exactly its declared share of ``mean_y``.
    Using the real transform rather than an approximation is the point: it makes the
    fitted coefficients, contributions and ROIs comparable to the numbers declared in
    ``CONTRIBUTION_SHARE`` instead of merely plausible.
    """
    from app.mmm.transforms import adstock_geometric, hill_saturation

    n = len(next(iter(drivers.values())))
    season = np.array([_season(i) for i in range(n)])
    trend = np.linspace(1.0, 1.18, n)  # a real trend, so the trend control earns its column
    y = BASELINE_SHARE * mean_y * season * trend

    for metric, raw in drivers.items():
        share = CONTRIBUTION_SHARE.get(metric)
        if not share:
            continue
        stocked = adstock_geometric(np.asarray(raw, dtype=float), 0.5)
        half = float(np.mean(stocked))
        t = hill_saturation(stocked, half=half, slope=1.0) if half > 0 else stocked
        m = float(np.mean(t)) or 1.0
        y = y + share * mean_y * (t / m)

    return np.maximum(y * rng.normal(1.0, 0.02, n), mean_y * 0.1)


def build_long_table(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = len(MONTHS)
    rows: list[dict] = []

    def emit(path, metric, mtype, brand, channel, region, values, source):
        l1, l2, l3, l4 = path
        for i, ym in enumerate(MONTHS):
            rows.append({
                "task_name": source, "brand": brand, "province_group": region,
                "channel_type": channel, "channel": channel,
                "year": ym // 100, "month": ym, "source": source,
                "l1": l1, "l2": l2, "l3": l3, "l4": l4,
                "l5": "", "l6": "", "l7": "", "l8": "",
                "metric_type": mtype, "metric": metric, "value": float(values[i]),
            })

    def _series_for(metric: str, siblings: dict[str, np.ndarray]) -> np.ndarray:
        parent = EXPOSURE_OF.get(metric)
        if parent and parent in siblings:
            return _exposure_from(rng, siblings[parent], metric)
        return _driver_series(rng, metric, n)

    # ── national drivers: one series each, no channel, no brand ──────────────
    national: dict[str, np.ndarray] = {}
    for path, metrics in FACTORS:
        for metric, mtype, scope in metrics:
            if scope != "national":
                continue
            national[metric] = _series_for(metric, national)
    for path, metrics in FACTORS:
        for metric, mtype, scope in metrics:
            if scope == "national":
                emit(path, metric, mtype, "", "", "", national[metric], SOURCE_OF[path[0]])

    # ── market drivers: competitor brand, no channel ─────────────────────────
    market: dict[str, np.ndarray] = {}
    for path, metrics in FACTORS:
        for metric, mtype, scope in metrics:
            if scope != "market":
                continue
            s = _driver_series(rng, metric, n)
            market[metric] = s
            emit(path, metric, mtype, MARKET_BRAND, "", "", s, SOURCE_OF[path[0]])

    # ── per channel × product: drivers, then the response they generate ──────
    for product in PRODUCTS:
        for ci, channel in enumerate(CHANNELS):
            local: dict[str, np.ndarray] = {}
            for path, metrics in FACTORS:
                for metric, mtype, scope in metrics:
                    if scope != "channel" or mtype == "Y":
                        continue
                    local[metric] = _series_for(metric, local)
            for path, metrics in FACTORS:
                for metric, mtype, scope in metrics:
                    if scope != "channel" or mtype == "Y":
                        continue
                    # Split the channel total across regions so the table carries a
                    # real region dimension that rolls up to this series.
                    w = rng.dirichlet(np.ones(len(REGIONS)) * 6)
                    for ri, region in enumerate(REGIONS):
                        emit(path, metric, mtype, product, channel, region,
                             local[metric] * w[ri], SOURCE_OF[path[0]])

            mean_y = 40_000.0 * (1.6 if product == PRODUCTS[0] else 1.0) * (1.0 + 0.35 * ci)
            units = _mmm_response({**national, **market, **local}, mean_y, rng)
            # A real, explainable business event: the Salon distributor was lost in
            # April 2023 and not replaced until October, so the channel ran at a
            # trickle for half a year. Big enough to clear the anomaly threshold on
            # the annual channel total, which is what gives 2.3 something to localize
            # and 2.3a a genuine event to handle — otherwise the media coefficients
            # absorb a shock marketing did not cause.
            if channel == "Salon":
                lo = MONTHS.index(202304)
                units[lo:lo + 6] *= 0.12
            price = 189.0 + 24.0 * ci + (18.0 if product == PRODUCTS[1] else 0.0)

            kpi_path = FACTORS[0][0]
            w = rng.dirichlet(np.ones(len(REGIONS)) * 6)
            for ri, region in enumerate(REGIONS):
                emit(kpi_path, "Net Sales Units", "Y", product, channel, region,
                     units * w[ri], SOURCE_OF["Business Outcome"])
                emit(kpi_path, "Net Sales Value", "Y", product, channel, region,
                     units * w[ri] * price, SOURCE_OF["Business Outcome"])

    df = pd.DataFrame(rows)
    from app.ingest.dataset import COLUMN_NAMES
    return df[[c for c in COLUMN_NAMES if c in df.columns]]


def build_factor_tree():
    """One factor row per (L1–L4) path — what `claim_published_metrics` matches on."""
    from app.domain.models import FactorRow, FactorTree
    rows = []
    for i, (path, metrics) in enumerate(FACTORS):
        l1, l2, l3, l4 = path
        rows.append(FactorRow(
            id=f"fs-{i}", l1=l1, l2=l2, l3=l3, l4=l4,
            indicator=metrics[0][0], dimension="", source="template",
            status="baseline",
            rationale="Synthetic case factor — see scripts/make_synthetic_case.py.",
        ))
    return FactorTree(rows=rows)


def seed(project_id: str = PROJECT_ID) -> dict:
    from app.dataeng import assets as asset_svc
    from app.dataeng.dbt.service import claim_published_metrics
    from app.domain.models import DataAsset, DataAssetVersion, IndustryRef, ProjectMeta
    from app.store.state import get_store, initial_state

    store = get_store()
    df = build_long_table()

    meta = ProjectMeta(
        id=project_id, name=PROJECT_NAME, brand=BRAND,
        industry=IndustryRef(l1=INDUSTRY[0], l2=INDUSTRY[1], l3=INDUSTRY[2]),
        kpi="Net Sales Units",
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    st = initial_state(meta)
    st.factor_tree = build_factor_tree()
    st.indicator_coverage = []
    st.data_assets = []
    store._states[project_id] = st  # noqa: SLF001 — seeding path, same as the reference seeder

    summary = []
    for source, grp in sorted(df.groupby("source"), key=lambda kv: -len(kv[1])):
        asset = asset_svc.create_asset(st, name=str(source),
                                       description=f"Synthetic case source · {source}")
        slice_df = grp.reset_index(drop=True)
        version = asset.latest_version + 1
        rel = f"projects/{project_id}/assets/{asset.id}/v{version}.parquet"
        abs_path = asset_svc.get_settings().data_path / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        slice_df.to_parquet(abs_path, index=False)
        asset.versions.append(DataAssetVersion(
            version=version, parquetPath=rel, rowCount=int(len(slice_df)),
            columns=[str(c) for c in slice_df.columns], sql="synthetic source slice",
            producedAt=datetime.now(timezone.utc).isoformat(timespec="seconds")))
        asset.latest_version = version
        asset.status = "published"
        claim_published_metrics(st, asset, slice_df)
        summary.append({"source": str(source), "rows": int(len(slice_df))})

    asset_svc._invalidate(project_id)  # noqa: SLF001
    from app.agents.dataset_cache import invalidate_project
    invalidate_project(project_id)
    store._upsert_index(meta)  # noqa: SLF001
    store.save(project_id)

    mapped = sum(1 for c in st.indicator_coverage if c.tree_row_id)
    return {"projectId": project_id, "rows": int(len(df)), "assets": len(st.data_assets),
            "coverage": len(st.indicator_coverage), "mappedCoverage": mapped,
            "factorRows": len(st.factor_tree.rows), "perSource": summary}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", default=PROJECT_ID)
    args = ap.parse_args()
    out = seed(args.project_id)
    for k, v in out.items():
        print(f"{k}: {v}")
