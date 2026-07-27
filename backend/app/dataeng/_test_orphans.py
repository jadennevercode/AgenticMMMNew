"""An orphan metric can be adopted into the factor tree.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_orphans``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", status="baseline"),
    ])
    st.indicator_coverage.append(IndicatorCoverage(
        id="c-orph", tree_row_id="", asset_id="a1", asset_name="Logistics",
        metric="仓库库存", metric_type="X", l1="COMMERCIAL FACTOR", l2="SUPPLY",
        l3="WAREHOUSE", l4="库存", coverage_start="202201", coverage_end="202212",
        rows=12))
    return st


def test_adopt_creates_an_accepted_row_and_claims_it() -> None:
    from app.dataeng import orphans
    from app.dataeng.indicators import declared_indicators, orphan_indicators
    st = _st()

    row_id = orphans.adopt(st, "c-orph")

    row = next(r for r in st.factor_tree.rows if r.id == row_id)
    assert row.source == "data_upload"
    assert row.status == "accepted", \
        "the S1 gates have already closed — adoption accepts on the spot"
    assert (row.l1, row.l3, row.l4) == ("COMMERCIAL FACTOR", "WAREHOUSE", "库存")
    assert row.indicator == "仓库库存"

    assert orphan_indicators(st) == [], "the orphan is now a supplied factor"
    adopted = next(i for i in declared_indicators(st) if i.tree_row_id == row_id)
    assert adopted.asset_name == "Logistics" and adopted.rows == 12


def test_adopt_is_idempotent() -> None:
    from app.dataeng import orphans
    st = _st()
    first = orphans.adopt(st, "c-orph")
    assert orphans.adopt(st, "c-orph") == first
    assert len(st.factor_tree.rows) == 2


def test_dismiss_removes_the_orphan() -> None:
    from app.dataeng import orphans
    from app.dataeng.indicators import orphan_indicators
    st = _st()
    assert orphans.dismiss(st, "c-orph") is True
    assert orphan_indicators(st) == []
    assert len(st.factor_tree.rows) == 1
    assert orphans.dismiss(st, "c-orph") is False


def test_dismiss_refuses_a_claimed_coverage() -> None:
    from app.dataeng import orphans
    st = _st()
    orphans.adopt(st, "c-orph")
    assert orphans.dismiss(st, "c-orph") is False, \
        "dismissing a supplying coverage would silently unmap its factor"


def main() -> int:
    for fn in (test_adopt_creates_an_accepted_row_and_claims_it,
               test_adopt_is_idempotent,
               test_dismiss_removes_the_orphan,
               test_dismiss_refuses_a_claimed_coverage):
        fn()
        print(f"ok  {fn.__name__}")
    print("all orphan adoption tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
