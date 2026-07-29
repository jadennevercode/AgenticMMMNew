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


def test_unbound_coverage_matching_a_row_is_not_an_orphan() -> None:
    """Coverage can be written before the factor tree exists (reset seeds the
    reference assets first). Once the tree arrives it must claim them on read —
    the same record must not be both a supplied factor and an unclaimed metric."""
    from app.dataeng.indicators import orphan_indicators
    from app.dataeng.mapping import resolve_factor_map
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="c-early", tree_row_id="", asset_id="a1", asset_name="TV",
        metric="TV投放金额", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
        rows=12))
    tv = next(r for r in resolve_factor_map(st).rows if r.row_id == "ft-1")
    assert tv.status == "mapped" and tv.asset_name == "TV"
    assert orphan_indicators(st) == []


def test_suggestions_only_offer_orphans() -> None:
    """A row nothing matches gets fuzzy proposals; a matched row gets none."""
    from app.dataeng import mapping_suggest as ms
    st = _st()
    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-taken", tree_row_id="ft-1", asset_id="a1",
                          asset_name="A", metric="TV投放金额", unit="元"),
        # Same L3 as ft-2 but a different L4 and a differently-worded metric, so
        # neither exact tier claims it — only the scorer can propose it.
        IndicatorCoverage(id="c-free", tree_row_id="", asset_id="a2",
                          asset_name="B", metric="电商投放费用", unit="元",
                          l3="EC", l4="其他平台", coverage_start="202201",
                          coverage_end="202212"),
    ])
    sugg = ms.suggest_all(st)
    assert "ft-1" not in sugg, "a mapped row needs no suggestion"
    assert [s.indicator_id for s in sugg["ft-2"]] == ["c-free"]


def test_autopilot_does_not_resolve_the_map_before_any_data_exists() -> None:
    """Blanket-ignoring an unstarted Data Engine permanently guts S2.

    Autopilot reaches 2.1 as soon as S1 closes, which on a real project is well
    before anything is published. Writing "no published indicator matches this
    factor" onto every row there is not a judgement — and because an ignore
    outranks coverage, data published afterwards can never un-ignore them: the
    factor map stays mapped=0 and the ledger drops every indicator at the mapping
    layer.
    """
    from app.dataeng.mapping import resolve_factor_map
    from app.dataeng.mapping_auto import auto_resolve_factor_map

    st = _st()
    result = auto_resolve_factor_map(st)
    assert result.get("no_data") is True
    assert st.factor_map_ignores == {}, "nothing may be ignored before data exists"
    assert resolve_factor_map(st).complete is False, "2.1 must still block"

    # Once something is published, it resolves as before.
    st.indicator_coverage.append(IndicatorCoverage(
        id="c1", tree_row_id="ft-1", asset_id="a1", asset_name="TV",
        metric="TV投放金额", rows=12, bound_by="auto"))
    auto_resolve_factor_map(st)
    fmap = resolve_factor_map(st)
    assert fmap.mapped == 1 and fmap.complete is True


def main() -> int:
    for fn in (test_row_with_coverage_is_mapped,
               test_autopilot_does_not_resolve_the_map_before_any_data_exists,
               test_multi_source_coverage_maps_once,
               test_ignored_row_clears_without_data,
               test_bind_pins_an_orphan_and_demotes_the_incumbent,
               test_unbind_releases_every_coverage_on_the_row,
               test_unbound_coverage_matching_a_row_is_not_an_orphan,
               test_suggestions_only_offer_orphans):
        fn()
        print(f"ok  {fn.__name__}")
    print("all mapping/coverage tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
