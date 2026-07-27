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


def main() -> int:
    for fn in (test_human_pin_migrates_auto_is_dropped,
               test_migration_is_idempotent,
               test_migrated_pin_still_maps_the_row):
        fn()
        print(f"ok  {fn.__name__}")
    print("all indicator migration tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
