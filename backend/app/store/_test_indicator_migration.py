"""Saved projects keep their manual factor bindings across the refactor.

Run: ``PYTHONPATH=. .venv/bin/python -m app.store._test_indicator_migration``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, Indicator
from app.store.state import ProjectState, _migrate_indicators_to_coverage


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", status="baseline"),
    ])
    st.indicators = [
        Indicator(id="ind-old-1", metric="央视花费", metricType="spending",
                  l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视", unit="元",
                  assetId="a1", assetName="TV spend", coverageStart="202201",
                  coverageEnd="202212", rows=12, treeGrounded=True,
                  treeRowId="ft-1", boundBy="human"),
        Indicator(id="ind-old-2", metric="猜的", assetId="a1", assetName="TV spend",
                  treeGrounded=True, treeRowId="ft-1", boundBy="auto"),
    ]
    return st


def test_human_pin_migrates_auto_is_dropped() -> None:
    st = _st()
    carried = _migrate_indicators_to_coverage(st)

    assert carried == 1
    assert st.indicators == [], "the legacy list is drained, not left to drift"
    assert len(st.indicator_coverage) == 1
    c = st.indicator_coverage[0]
    assert c.id == "ind-old-1" and c.tree_row_id == "ft-1" and c.bound_by == "human"
    assert c.metric == "央视花费" and c.asset_id == "a1"
    assert c.coverage_start == "202201" and c.rows == 12


def test_binding_older_than_the_bound_by_field_is_kept() -> None:
    """A binding written before `bound_by` existed carries `""`, and the real
    Danone project has ten of them holding its 2.1 gate open. Their indicator
    paths do not match their factor row's by ANY rule in the code — only the
    metric name lines up — so nothing re-derives them. Only an explicit "auto"
    is safe to drop.
    """
    st = _st()
    st.indicators = [Indicator(
        id="ind-legacy", metric="温度", l3="Macro", l4="环境调节因素-自然",
        assetId="a1", assetName="Weather", treeGrounded=True, treeRowId="ft-1")]
    assert st.indicators[0].bound_by == "", "precondition: the field defaults empty"

    assert _migrate_indicators_to_coverage(st) == 1
    c = st.indicator_coverage[0]
    assert c.tree_row_id == "ft-1"
    assert c.bound_by == "human", \
        "an unreproducible binding is pinned so a re-publish cannot drop it"


def test_migration_is_idempotent() -> None:
    st = _st()
    _migrate_indicators_to_coverage(st)
    assert _migrate_indicators_to_coverage(st) == 0
    assert len(st.indicator_coverage) == 1


def test_migrated_pin_still_maps_the_row() -> None:
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    _migrate_indicators_to_coverage(st)
    assert resolve_factor_map(st).rows[0].status == "mapped"


def test_already_published_assets_are_reclaimed() -> None:
    """A project whose assets published BEFORE the refactor must not lose its
    mapping. Auto bindings are dropped by the migration on purpose, but nobody is
    going to re-publish 29 assets by hand to get them back — the parquet is still
    on disk, so the claim is replayed from it.
    """
    import pandas as pd

    from app.config import get_settings
    from app.domain.models import DataAsset, DataAssetVersion
    from app.dataeng.mapping import resolve_factor_map
    from app.store.state import _reclaim_published_assets

    st = _st()
    st.indicators = []                     # nothing to migrate; only auto existed
    rel = "projects/_t/assets/a1/v1.parquet"
    abs_path = get_settings().data_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "metric": ["TV投放金额"] * 2, "metric_type": ["spending"] * 2,
        "l1": ["MARKETING FACTOR"] * 2, "l2": ["ATL"] * 2,
        "l3": ["TV"] * 2, "l4": ["卫视"] * 2,
        "month": [202201, 202202], "value": [1.0, 2.0],
    }).to_parquet(abs_path, index=False)
    st.data_assets = [DataAsset(
        id="a1", name="TV spend", status="published", latestVersion=1,
        versions=[DataAssetVersion(version=1, parquetPath=rel, rowCount=2)])]

    assert resolve_factor_map(st).mapped == 0, "precondition: nothing claimed yet"
    assert _reclaim_published_assets(st) == 1
    assert resolve_factor_map(st).mapped == 1, \
        "a published asset must still supply its factor after the migration"
    # Idempotent: a second pass sees coverage already present and does nothing.
    assert _reclaim_published_assets(st) == 0


def test_legacy_binding_overlays_a_reclaimed_coverage() -> None:
    """The Danone shape end to end: reclaim rebuilds a coverage from the parquet
    and finds no factor row for it, then the legacy binding pins that same record.
    Skipping it because its id already exists would drop the binding — which is
    exactly how the 2.1 gate silently re-blocked.
    """
    import pandas as pd

    from app.config import get_settings
    from app.domain.models import DataAsset, DataAssetVersion
    from app.dataeng.dbt.service import _indicator_id
    from app.dataeng.mapping import resolve_factor_map
    from app.store.state import _reclaim_published_assets

    st = _st()
    # The mart's own path matches no factor row — only the metric name lines up.
    vals = {"metric": "温度", "metric_type": "X", "l1": "Macro", "l2": "",
            "l3": "Macro", "l4": "环境调节因素-自然"}
    rel = "projects/_t2/assets/a2/v1.parquet"
    abs_path = get_settings().data_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({**{k: [v] * 2 for k, v in vals.items()},
                  "month": [202201, 202202], "value": [1.0, 2.0]}).to_parquet(abs_path, index=False)
    asset = DataAsset(id="a2", name="Weather", status="published", latestVersion=1,
                      versions=[DataAssetVersion(version=1, parquetPath=rel, rowCount=2)])
    st.data_assets = [asset]
    st.indicators = [Indicator(id=_indicator_id("a2", vals), metric="温度",
                               l1="Macro", l3="Macro", l4="环境调节因素-自然",
                               assetId="a2", assetName="Weather",
                               treeGrounded=True, treeRowId="ft-1")]

    _reclaim_published_assets(st)
    assert resolve_factor_map(st).mapped == 0, \
        "precondition: the reclaim alone cannot match this path to the row"
    assert _migrate_indicators_to_coverage(st) == 1
    assert resolve_factor_map(st).mapped == 1, "the legacy binding must survive"
    assert len(st.indicator_coverage) == 1, "overlaid, not duplicated"


def main() -> int:
    for fn in (test_human_pin_migrates_auto_is_dropped,
               test_binding_older_than_the_bound_by_field_is_kept,
               test_migration_is_idempotent,
               test_migrated_pin_still_maps_the_row,
               test_already_published_assets_are_reclaimed,
               test_legacy_binding_overlays_a_reclaimed_coverage):
        fn()
        print(f"ok  {fn.__name__}")
    print("all indicator migration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
