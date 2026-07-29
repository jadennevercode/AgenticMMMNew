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


def _with_response(st: ProjectState) -> ProjectState:
    st.indicator_coverage.append(IndicatorCoverage(
        id="c-y", tree_row_id="", asset_id="a2", asset_name="Sales",
        metric="本品销量箱数", metric_type="Y", l1="KPI", l2="KPI", l3="KPI",
        l4="本品销量", coverage_start="202201", coverage_end="202212", rows=12))
    return st


def test_the_response_is_not_an_orphan() -> None:
    """No industry factor tree declares sales — factors are what explain it.

    Before this, the response matched no row and was listed as "data nobody asked
    for", i.e. the one series the model is built on was offered for adoption.
    """
    from app.dataeng.indicators import orphan_indicators, response_coverages
    st = _with_response(_st())

    assert [c.metric for c in response_coverages(st)] == ["本品销量箱数"]
    orphans = {i.metric for i in orphan_indicators(st)}
    assert "本品销量箱数" not in orphans, orphans
    assert "仓库库存" in orphans, "a genuine orphan must still be offered"


def test_adopting_the_response_is_refused() -> None:
    """Adopting Y would make the dependent variable one of its own drivers."""
    from app.dataeng import orphans
    st = _with_response(_st())
    try:
        orphans.adopt(st, "c-y")
    except ValueError as exc:
        assert "response" in str(exc).lower(), exc
    else:
        raise AssertionError("adopting the response should be refused")


def main() -> int:
    for fn in (test_adopt_creates_an_accepted_row_and_claims_it,
               test_adopt_is_idempotent,
               test_the_response_is_not_an_orphan,
               test_adopting_the_response_is_refused,
               test_dismiss_removes_the_orphan,
               test_dismiss_refuses_a_claimed_coverage):
        fn()
        print(f"ok  {fn.__name__}")
    print("all orphan adoption tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
