"""The 2.1 factor map resolves against coverage records.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_mapping_coverage``
"""
from __future__ import annotations

from app.domain.models import FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", status="baseline"),
        FactorRow(id="ft-2", l1="MARKETING FACTOR", l2="DIGITAL", l3="EC", l4="天猫",
                  indicator="电商投放金额", status="accepted"),
    ])
    return st


def test_row_with_coverage_is_mapped() -> None:
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="c1", tree_row_id="ft-1", asset_id="a1", asset_name="TV",
        metric="CCTV花费", coverage_start="202201", coverage_end="202212",
        rows=12, bound_by="auto"))

    fmap = resolve_factor_map(st)
    tv = next(r for r in fmap.rows if r.row_id == "ft-1")
    assert tv.status == "mapped"
    assert tv.asset_name == "TV" and tv.metric == "CCTV花费"
    assert fmap.mapped == 1 and fmap.pending == 1 and fmap.complete is False


def test_multi_source_coverage_maps_once() -> None:
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c1", tree_row_id="ft-1", asset_id="a1",
                          asset_name="TV central", metric="央视花费", rows=12),
        IndicatorCoverage(id="c2", tree_row_id="ft-1", asset_id="a2",
                          asset_name="TV satellite", metric="卫视花费", rows=99),
    ])
    tv = next(r for r in resolve_factor_map(st).rows if r.row_id == "ft-1")
    assert tv.status == "mapped"
    assert len(tv.coverages) == 2, "a factor may be supplied by several sources"
    assert tv.asset_name == "TV satellite", "the widest series represents the row"


def test_ignored_row_clears_without_data() -> None:
    from app.dataeng.mapping import mapping_complete
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="c1", tree_row_id="ft-1", asset_id="a1", asset_name="TV", metric="m"))
    st.factor_map_ignores["ft-2"] = "no data source"
    assert mapping_complete(st) is True


def test_bind_pins_an_orphan_and_demotes_the_incumbent() -> None:
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-auto", tree_row_id="ft-1", asset_id="a1",
                          asset_name="Guess", metric="m1", bound_by="auto"),
        IndicatorCoverage(id="c-orph", tree_row_id="", asset_id="a2",
                          asset_name="Real", metric="m2"),
    ])
    assert ms.bind(st, "ft-1", "c-orph") is True
    by_id = {c.id: c for c in st.indicator_coverage}
    assert by_id["c-orph"].tree_row_id == "ft-1" and by_id["c-orph"].bound_by == "human"
    assert by_id["c-auto"].tree_row_id == "", \
        "one published metric supplies at most one factor row"


def test_unbind_releases_every_coverage_on_the_row() -> None:
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c1", tree_row_id="ft-1", asset_id="a1",
                          asset_name="A", metric="m1", bound_by="auto"),
        IndicatorCoverage(id="c2", tree_row_id="ft-1", asset_id="a2",
                          asset_name="B", metric="m2", bound_by="human"),
    ])
    assert ms.unbind(st, "ft-1") is True
    assert all(c.tree_row_id == "" for c in st.indicator_coverage)


def test_suggestions_only_offer_orphans() -> None:
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-taken", tree_row_id="ft-1", asset_id="a1",
                          asset_name="A", metric="TV投放金额", unit="元"),
        IndicatorCoverage(id="c-free", tree_row_id="", asset_id="a2",
                          asset_name="B", metric="电商投放金额", unit="元",
                          l3="EC", l4="天猫", coverage_start="202201",
                          coverage_end="202212"),
    ])
    sugg = ms.suggest_all(st)
    assert "ft-1" not in sugg, "a mapped row needs no suggestion"
    assert [s.indicator_id for s in sugg["ft-2"]] == ["c-free"]


def main() -> int:
    for fn in (test_row_with_coverage_is_mapped,
               test_multi_source_coverage_maps_once,
               test_ignored_row_clears_without_data,
               test_bind_pins_an_orphan_and_demotes_the_incumbent,
               test_unbind_releases_every_coverage_on_the_row,
               test_suggestions_only_offer_orphans):
        fn()
        print(f"ok  {fn.__name__}")
    print("all mapping/coverage tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
