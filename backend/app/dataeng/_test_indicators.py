"""Derivation tests: the factor tree is the indicator catalog.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_indicators``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", source="template", status="baseline"),
        FactorRow(id="ft-2", l1="KPI", l2="", l3="", l4="",
                  indicator="本品销量", source="ai", status="accepted"),
        FactorRow(id="ft-3", l1="MARKETING FACTOR", l2="DIGITAL", l3="EC", l4="天猫",
                  indicator="电商投放金额", source="interview", status="rejected"),
    ])
    return st


def test_coverage_model_defaults() -> None:
    c = IndicatorCoverage(id="cov-1", asset_id="a1", asset_name="Sales", metric="TV投放金额")
    assert c.tree_row_id == "", "an unclaimed coverage is an orphan"
    assert c.bound_by == ""
    assert c.rows == 0


def test_state_carries_coverage() -> None:
    st = _st()
    assert st.indicator_coverage == []
    st.indicator_coverage.append(
        IndicatorCoverage(id="cov-1", tree_row_id="ft-1", asset_id="a1",
                          asset_name="Sales", metric="TV投放金额", bound_by="auto"))
    # ProjectState must round-trip without aliasing its own fields.
    dumped = st.model_dump()
    assert "indicator_coverage" in dumped, "ProjectState fields are snake_case, unaliased"
    assert dumped["indicator_coverage"][0]["tree_row_id"] == "ft-1"


def main() -> int:
    for fn in (test_coverage_model_defaults, test_state_carries_coverage):
        fn()
        print(f"ok  {fn.__name__}")
    print("all indicator derivation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
