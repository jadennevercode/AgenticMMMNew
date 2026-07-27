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


def test_declared_one_per_active_row() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    got = ind.declared_indicators(st)
    assert [i.id for i in got] == ["ind-ft-1", "ind-ft-2"], \
        f"rejected rows are not data targets; got {[i.id for i in got]}"
    tv = got[0]
    assert tv.metric == "TV投放金额"
    assert (tv.l1, tv.l2, tv.l3, tv.l4) == ("MARKETING FACTOR", "ATL", "TV", "卫视")
    assert tv.tree_row_id == "ft-1"
    assert tv.tree_grounded is True
    assert tv.source == "template", "declared source follows the factor row"
    assert tv.asset_id == "" and tv.coverage_start == "", "no data yet"
    assert got[1].source == "ai"


def test_source_map_covers_every_factor_source() -> None:
    import typing

    from app.domain.models import FactorSource
    from app.dataeng import indicators as ind

    for v in typing.get_args(FactorSource):
        assert v in ind.SOURCE_MAP, f"FactorSource {v!r} has no IndicatorSource"


def test_coverage_fills_the_declared_row() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    st.indicator_coverage.append(IndicatorCoverage(
        id="cov-1", tree_row_id="ft-1", asset_id="a1", asset_name="TV spend",
        metric="CCTV投放金额", metric_type="spending", unit="元",
        coverage_start="202201", coverage_end="202412", rows=36, bound_by="auto"))

    tv = next(i for i in ind.declared_indicators(st) if i.id == "ind-ft-1")
    assert tv.asset_id == "a1" and tv.asset_name == "TV spend"
    assert tv.coverage_start == "202201" and tv.coverage_end == "202412"
    assert tv.rows == 36
    assert tv.unit == "元"
    assert tv.metric == "TV投放金额", "the factor's own wording stays the label"
    assert tv.source == "data_upload", "a supplied factor reports as supplied"


def test_human_pin_is_the_primary_coverage() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    st.indicator_coverage.extend([
        IndicatorCoverage(id="c-auto", tree_row_id="ft-1", asset_id="a1",
                          asset_name="Auto", metric="m1", rows=99, bound_by="auto"),
        IndicatorCoverage(id="c-human", tree_row_id="ft-1", asset_id="a2",
                          asset_name="Human", metric="m2", rows=1, bound_by="human"),
    ])
    prim = ind.primary_coverage(st, "ft-1")
    assert prim is not None and prim.id == "c-human", \
        "a human pin outranks a bigger auto match"
    assert len(ind.coverages_for(st, "ft-1")) == 2, "multi-source coverage is kept"


def test_orphans_are_separate_and_not_declared() -> None:
    st = _st()
    from app.dataeng import indicators as ind

    st.indicator_coverage.append(IndicatorCoverage(
        id="c-orph", tree_row_id="", asset_id="a1", asset_name="Sales",
        metric="仓库库存", l3="LOGISTICS", rows=12))

    assert [i.id for i in ind.declared_indicators(st)] == ["ind-ft-1", "ind-ft-2"]
    orph = ind.orphan_indicators(st)
    assert [i.id for i in orph] == ["c-orph"]
    assert orph[0].tree_grounded is False
    assert orph[0].source == "data_upload"
    assert len(ind.derive_indicators(st)) == 3


def test_coverage_written_before_the_tree_still_matches() -> None:
    """Resetting the Danone case seeds 29 reference assets while `factor_tree` is
    still None — the tree is built later by task 1.21. Matching only at publish
    time left every one of them an orphan forever and the 2.1 map permanently
    pending, so unbound coverage is matched on read.
    """
    from app.dataeng import indicators as ind

    st = ProjectState(project_id="_t")            # no factor tree yet
    st.indicator_coverage.append(IndicatorCoverage(
        id="c-early", tree_row_id="", asset_id="a1", asset_name="TV spend",
        metric="TV投放金额", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
        coverage_start="202201", coverage_end="202412", rows=36))
    assert len(ind.orphan_indicators(st)) == 1, "no tree → nothing to match against"

    st.factor_tree = _st().factor_tree             # the tree arrives afterwards
    tv = next(i for i in ind.declared_indicators(st) if i.id == "ind-ft-1")
    assert tv.asset_id == "a1", "the late tree must pick up the early coverage"
    assert ind.orphan_indicators(st) == [], \
        "a matched coverage is not also an orphan"


def test_l3_and_metric_name_is_the_looser_anchor() -> None:
    """Second tier: the mart's path disagrees but L3 + the factor's own indicator
    name line up. This is what the old resolver's third tier did."""
    from app.dataeng import indicators as ind

    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="c-loose", tree_row_id="", asset_id="a2", asset_name="Weather",
        metric="TV投放金额", l1="不同", l2="不同", l3="TV", l4="不同", rows=9))
    tv = next(i for i in ind.declared_indicators(st) if i.id == "ind-ft-1")
    assert tv.asset_id == "a2"


def main() -> int:
    for fn in (test_coverage_model_defaults, test_state_carries_coverage,
               test_coverage_written_before_the_tree_still_matches,
               test_l3_and_metric_name_is_the_looser_anchor,
               test_declared_one_per_active_row,
               test_source_map_covers_every_factor_source,
               test_coverage_fills_the_declared_row,
               test_human_pin_is_the_primary_coverage,
               test_orphans_are_separate_and_not_declared):
        fn()
        print(f"ok  {fn.__name__}")
    print("all indicator derivation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
