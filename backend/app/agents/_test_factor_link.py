"""The factor-tree ↔ data bridge, and the one case it used to drop on the floor.

A coverage record carries the mart's own ``(l1..l4, metric)`` *and* the factor row
it supplies. Those two spellings differ by design — that difference is the entire
reason a human pins one to the other — so the bridge has to register **both**. It
used to register only the tree side, which meant a pin across differing L4 wording
produced no traversable key at all, and the indicator read as an orphan: data the
factor tree never asked for, sitting in the model with a human's binding on it.

Runnable with pytest or plain python (asserts run under __main__).
"""
from __future__ import annotations

from app.agents import factor_link
from app.domain.models import (
    FactorRow,
    FactorTree,
    IndicatorCoverage,
    IndustryRef,
    ProjectMeta,
)
from app.store.state import ProjectState


def _row(rid: str, l3: str, l4: str, indicator: str) -> FactorRow:
    return FactorRow(id=rid, l1="MARKETING FACTOR", l2=l3, l3=l3, l4=l4,
                     indicator=indicator, status="baseline", source="template")


def _cov(cid: str, row_id: str, l3: str, l4: str, metric: str,
         bound_by: str = "human") -> IndicatorCoverage:
    """A published metric supplying a row, under the DATA's own labels."""
    return IndicatorCoverage(id=cid, treeRowId=row_id, assetId="a1", assetName="Asset",
                             metric=metric, l1="MARKETING FACTOR", l2=l3, l3=l3, l4=l4,
                             boundBy=bound_by)


def _state(rows: list[FactorRow], covs: list[IndicatorCoverage]) -> ProjectState:
    st = ProjectState()
    st.meta = ProjectMeta(
        id="link-test", name="Link", brand="B",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
        createdAt="2026-01-01")
    st.factor_tree = FactorTree(rows=rows)
    st.indicator_coverage = covs
    return st


def test_a_pin_across_differing_l4_wording_resolves() -> None:
    """The regression. The tree says 电商站内投流; the data says 站内投流; a human
    pinned them together. The key every later layer filters on is the data's.

    The two decoy rows are what makes this a real test rather than a tautology:
    ``花费`` is declared tree-wide (50 rows of the reference tree declare it), so
    the metric-only fallback correctly declines to guess and cannot rescue the
    lookup. Only the coverage's own ``(l4, metric)`` can resolve it.
    """
    st = _state(
        [_row("r1", "电商平台媒体及促销", "电商站内投流", "花费"),
         _row("decoy1", "品牌传播", "TV", "花费"),
         _row("decoy2", "品牌传播", "OOH", "花费")],
        [_cov("c1", "r1", "电商平台媒体及促销", "站内投流", "花费")],
    )
    link = factor_link.build(st)
    assert len(link.rows_of_metric["花费"]) > 1, "fixture must keep the label ambiguous"

    res = link.resolve("站内投流", "花费")
    assert res.row_id == "r1", "the human's pin must be traversable from the data key"
    assert res.how == factor_link.HOW_BOUND
    assert not res.orphan
    # The tree's own spelling keeps working — both sides are registered.
    assert link.row_for("电商站内投流", "花费") == "r1"
    assert factor_link._pair("站内投流", "花费") in link.keys_for("r1")


def test_an_ambiguous_label_is_not_an_orphan() -> None:
    """50 rows of the real tree declare 花费. When no L4 matches, the metric-only
    fallback rightly declines to guess — but "I cannot tell which" is not "the tree
    never asked for this", and adopting on the second reading duplicates a factor
    that already exists."""
    st = _state(
        [_row("r1", "品牌传播", "TV", "花费"), _row("r2", "品牌传播", "OOH", "花费")],
        [],
    )
    link = factor_link.build(st)

    res = link.resolve("某个没人认领的L4", "花费")
    assert res.row_id == ""
    assert res.how == factor_link.HOW_AMBIGUOUS
    assert not res.orphan, "an ambiguous label is declared — it is not orphan data"


def test_data_no_row_declares_is_a_real_orphan() -> None:
    st = _state([_row("r1", "品牌传播", "TV", "花费")], [])
    link = factor_link.build(st)

    res = link.resolve("天气", "降水量")
    assert res.row_id == "" and res.how == factor_link.HOW_UNDECLARED
    assert res.orphan


def test_a_pin_outranks_a_coincidentally_equal_declared_name() -> None:
    """Two rows can spell the same (l4, metric); only one carries the pin. The
    pin is a statement about that exact data key and must win."""
    st = _state(
        [_row("declared", "店内促销", "旺点促销", "花费"),
         _row("pinned", "组合优惠", "买N赠N", "花费")],
        [_cov("c1", "pinned", "店内促销", "旺点促销", "花费")],
    )
    link = factor_link.build(st)

    res = link.resolve("旺点促销", "花费")
    assert res.how == factor_link.HOW_BOUND
    assert res.row_id == "pinned", "a human pin must outrank a same-spelling declaration"


def test_an_ignore_reaches_the_data_key_the_later_layers_filter_on() -> None:
    """`ignored_data_keys` is the whole point of the bridge: a factor rejected at
    2.1 must stop being scored, screened and fitted. Before the fix a pinned row
    yielded only the tree-side key, so the ignore filtered nothing."""
    st = _state(
        [_row("r1", "电商平台媒体及促销", "电商站内投流", "花费"),
         _row("decoy", "品牌传播", "TV", "花费")],
        [_cov("c1", "r1", "电商平台媒体及促销", "站内投流", "花费")],
    )
    st.factor_map_ignores = {"r1": "Not part of this year's plan."}

    keys = factor_link.ignored_data_keys(st)
    assert factor_link._pair("站内投流", "花费") in keys, (
        "the ignore must be expressed in the data's key space, not only the tree's")
    assert keys[factor_link._pair("站内投流", "花费")] == "Not part of this year's plan."


def test_no_coverage_at_all_still_builds() -> None:
    """A tree with nothing published yet is a normal early state, not an error."""
    link = factor_link.build(_state([_row("r1", "品牌传播", "TV", "花费")], []))
    assert link.row_for("TV", "花费") == "r1"
    assert factor_link.build(ProjectState()).meta_of_row == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all factor_link bridge tests passed")
