"""2.1 mapping suggestions — AI proposes, the resolver still decides.

The scoring here is deterministic on purpose: a mapping is what every later S2
layer filters on, so it must never be invented. These tests pin the scorer's
ordering and the accept/remap round-trip through the existing resolver.
"""
from __future__ import annotations

from app.dataeng import mapping_suggest as ms
from app.dataeng.mapping import resolve_factor_map
from app.domain.models import FactorRow, FactorTree, Indicator
from app.store.state import danone_meta, initial_state


def _ind(iid: str, metric: str, *, l3: str = "", l4: str = "", unit: str = "",
         start: str = "202301", end: str = "202412") -> Indicator:
    return Indicator(id=iid, metric=metric, l3=l3, l4=l4, unit=unit,
                     assetId="a1", assetName="Asset One",
                     coverageStart=start, coverageEnd=end, rows=100)


def _state(rows: list[FactorRow], inds: list[Indicator]):
    st = initial_state(danone_meta())
    st.factor_tree = FactorTree(rows=rows)
    st.indicators = inds
    return st


def _row(rid: str, *, l3: str, l4: str, indicator: str) -> FactorRow:
    return FactorRow(id=rid, l1="Marketing Factor", l2="Media", l3=l3, l4=l4,
                     indicator=indicator, status="accepted")


def test_overlap_is_symmetric_and_bounded() -> None:
    assert ms._overlap("同店销量", "同店销量") == 1.0
    assert ms._overlap("", "anything") == 0.0
    assert 0.0 < ms._overlap("brand social spend", "social spend") < 1.0


def test_cjk_names_score_above_zero() -> None:
    """A whitespace tokenizer alone scores every Chinese pair at zero."""
    assert ms._overlap("线下路演曝光", "路演曝光量") > 0.0


def test_same_l3_outranks_a_stranger() -> None:
    row = _row("r1", l3="社交媒体", l4="微博", indicator="曝光量")
    near = _ind("i1", "曝光量", l3="社交媒体", l4="微博")
    far = _ind("i2", "货架陈列数", l3="陈列", l4="冰柜")
    assert ms.score(row, near) > ms.score(row, far)


def test_unit_agreement_lifts_the_score() -> None:
    row = _row("r1", l3="促销", l4="折扣", indicator="促销花费")
    money = _ind("i1", "促销花费", l3="促销", l4="折扣", unit="元")
    unitless = _ind("i2", "促销花费", l3="促销", l4="折扣", unit="")
    assert ms.score(row, money) > ms.score(row, unitless)


def test_suggest_ranks_best_first_and_drops_weak_matches() -> None:
    # The candidate must NOT exact-match by L3 + indicator name, or the resolver
    # already covers the row and there is nothing to suggest. A near-miss name is
    # exactly the case suggestions exist for.
    row = _row("r1", l3="社交媒体", l4="微博", indicator="曝光量")
    st = _state([row], [
        _ind("i-far", "完全无关的东西", l3="物流", l4="仓储"),
        _ind("i-best", "微博曝光量", l3="社交媒体", l4="微博", unit="次"),
    ])
    assert resolve_factor_map(st).rows[0].status == "pending"

    out = ms.suggest_all(st)
    assert "r1" in out, "a pending row with a real candidate must get a suggestion"
    assert out["r1"][0].indicator_id == "i-best"
    assert out["r1"][0].reason
    assert all(s.score >= ms.MIN_SCORE for s in out["r1"])
    assert "i-far" not in [s.indicator_id for s in out["r1"]], "weak matches are dropped"


def test_mapped_rows_get_no_suggestion() -> None:
    """A row the resolver already covers is not pending — nothing to propose."""
    row = _row("r1", l3="社交媒体", l4="微博", indicator="曝光量")
    ind = _ind("i1", "曝光量", l3="社交媒体", l4="微博")
    ind.tree_row_id = "r1"
    st = _state([row], [ind])
    assert resolve_factor_map(st).rows[0].status == "mapped"
    assert ms.suggest_all(st) == {}


def test_an_indicator_bound_elsewhere_is_not_re_proposed() -> None:
    """One indicator covering two factors is a mapping error, not a suggestion."""
    taken = _ind("i1", "曝光量", l3="社交媒体", l4="微博")
    taken.tree_row_id = "r1"
    st = _state([
        _row("r1", l3="社交媒体", l4="微博", indicator="曝光量"),
        _row("r2", l3="社交媒体", l4="微博", indicator="曝光量"),
    ], [taken])
    out = ms.suggest_all(st)
    assert "i1" not in [s.indicator_id for s in out.get("r2", [])]


def test_bind_makes_the_resolver_report_mapped() -> None:
    """Accepting a suggestion resolves the row through the ordinary exact path."""
    row = _row("r1", l3="社交媒体", l4="微博", indicator="曝光量")
    st = _state([row], [_ind("i1", "微博曝光", l3="社交媒体", l4="微博")])
    assert resolve_factor_map(st).rows[0].status == "pending"

    assert ms.bind(st, "r1", "i1") is True
    fm = resolve_factor_map(st)
    assert fm.rows[0].status == "mapped" and fm.rows[0].metric == "微博曝光"
    assert fm.complete


def test_bind_clears_an_ignore_and_unbind_reverts() -> None:
    row = _row("r1", l3="社交媒体", l4="微博", indicator="曝光量")
    st = _state([row], [_ind("i1", "微博曝光", l3="社交媒体", l4="微博")])
    st.factor_map_ignores["r1"] = "no source"
    assert resolve_factor_map(st).rows[0].status == "ignored"

    ms.bind(st, "r1", "i1")
    assert resolve_factor_map(st).rows[0].status == "mapped"
    assert "r1" not in st.factor_map_ignores

    assert ms.unbind(st, "r1") is True
    assert resolve_factor_map(st).rows[0].status == "pending"


def test_bind_on_an_unknown_indicator_reports_failure() -> None:
    st = _state([_row("r1", l3="a", l4="b", indicator="c")], [])
    assert ms.bind(st, "r1", "nope") is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all mapping-suggest tests passed")
