"""Publish claims factor rows; it does not manufacture indicators.

Run: ``PYTHONPATH=. .venv/bin/python -m app.dataeng._test_claim``
"""
from __future__ import annotations

import pandas as pd

from app.domain.models import DataAsset, FactorRow, FactorTree, IndicatorCoverage
from app.store.state import ProjectState


def _st() -> ProjectState:
    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-1", l1="MARKETING FACTOR", l2="ATL", l3="TV", l4="卫视",
                  indicator="TV投放金额", source="template", status="baseline"),
    ])
    return st


def _asset() -> DataAsset:
    return DataAsset(id="a1", name="TV spend")


def _df(l3: str = "TV", l4: str = "卫视", metric: str = "TV投放金额") -> pd.DataFrame:
    return pd.DataFrame({
        "metric": [metric] * 3,
        "metric_type": ["spending"] * 3,
        "l1": ["MARKETING FACTOR"] * 3, "l2": ["ATL"] * 3,
        "l3": [l3] * 3, "l4": [l4] * 3,
        "month": [202201, 202202, 202203],
        "value": [1.0, 2.0, 3.0],
    })


# L3 alone is the resolver's looser anchor, so an unmatched mart has to miss on
# L3 too — changing only L4 still claims the row, by design.
_MISS = {"l3": "WAREHOUSE", "l4": "库存"}


def test_matching_mart_claims_the_row_and_makes_no_indicator() -> None:
    from app.dataeng.dbt import service
    st = _st()
    covs = service.claim_published_metrics(st, _asset(), _df())

    assert len(covs) == 1
    assert covs[0].tree_row_id == "ft-1", "full L1–L4 path claims the row"
    assert covs[0].bound_by == "auto"
    assert covs[0].coverage_start == "202201" and covs[0].coverage_end == "202203"
    assert covs[0].rows == 3
    assert st.indicators == [], "publish no longer writes the legacy catalog"


def test_unmatched_metric_becomes_an_orphan() -> None:
    from app.dataeng.dbt import service
    from app.dataeng import indicators as ind
    st = _st()
    service.claim_published_metrics(st, _asset(), _df(**_MISS, metric="仓库库存"))

    assert ind.declared_indicators(st)[0].asset_id == "", "the factor is still unsupplied"
    orph = ind.orphan_indicators(st)
    assert len(orph) == 1 and orph[0].metric == "仓库库存"


def test_human_pin_survives_republish() -> None:
    from app.dataeng.dbt import service
    st = _st()
    covs = service.claim_published_metrics(st, _asset(), _df(**_MISS))
    covs[0].tree_row_id = "ft-1"
    covs[0].bound_by = "human"

    service.claim_published_metrics(st, _asset(), _df(**_MISS))
    after = st.indicator_coverage
    assert len(after) == 1
    assert after[0].tree_row_id == "ft-1" and after[0].bound_by == "human", \
        "a human binding is a decision, not derived state"


def test_republish_replaces_only_this_asset() -> None:
    from app.dataeng.dbt import service
    st = _st()
    st.indicator_coverage.append(IndicatorCoverage(
        id="other", tree_row_id="", asset_id="a2", asset_name="Other", metric="m"))
    service.claim_published_metrics(st, _asset(), _df())
    assert {c.asset_id for c in st.indicator_coverage} == {"a1", "a2"}


def test_siblings_on_one_path_each_claim_their_own_indicator() -> None:
    """The tree carries several rows per L1–L4, one per indicator.

    A path-keyed lookup silently keeps one arbitrary sibling and hands it every
    metric under that path. On the reference tree that bound 温度 to the row
    declaring 降水量 — marked ``auto``, with the row that actually declares 温度
    left looking unsupplied, and nothing downstream re-examining it.
    """
    from app.dataeng.dbt import service

    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-rain", l1="BASE", l2="EXT", l3="品类趋势", l4="季节性趋势",
                  indicator="降水量", source="template", status="baseline"),
        FactorRow(id="ft-temp", l1="BASE", l2="EXT", l3="品类趋势", l4="季节性趋势",
                  indicator="温度", source="template", status="baseline"),
    ])
    df = pd.DataFrame({
        "metric": ["温度", "降水量"],
        "metric_type": ["X", "X"],
        "l1": ["BASE"] * 2, "l2": ["EXT"] * 2,
        "l3": ["品类趋势"] * 2, "l4": ["季节性趋势"] * 2,
        "month": [202201, 202201], "value": [21.0, 90.0],
    })
    covs = service.claim_published_metrics(st, _asset(), df)
    bound = {c.metric: c.tree_row_id for c in covs}
    assert bound["温度"] == "ft-temp", f"温度 claimed {bound['温度']!r}"
    assert bound["降水量"] == "ft-rain", f"降水量 claimed {bound['降水量']!r}"


def test_the_l3_fallback_will_not_hand_one_row_to_two_metrics() -> None:
    """The coarse tier knows nothing about which metric it is placing.

    On the drill's tree 促销优惠's 花费 and PPI both fell through to the row
    declaring 满减活动花费 — the row then read as supplied and both metrics read
    as accounted for, three claims deep. One of them may anchor there; the rest
    are orphans, which is exactly what 2.1 exists to resolve.
    """
    from app.dataeng.dbt import service

    st = ProjectState(project_id="_t")
    st.factor_tree = FactorTree(rows=[
        FactorRow(id="ft-mj", l1="促销优惠", l2="促销优惠", l3="促销优惠", l4="满减",
                  indicator="满减活动花费", source="template", status="baseline"),
    ])
    df = pd.DataFrame({
        "metric": ["花费", "PPI"],
        "metric_type": ["spending", "X"],
        "l1": ["促销优惠"] * 2, "l2": ["促销优惠"] * 2,
        "l3": ["促销优惠"] * 2, "l4": ["促销优惠"] * 2,
        "month": [202201, 202201], "value": [1.0, 2.0],
    })
    covs = service.claim_published_metrics(st, _asset(), df)
    claimed = [c for c in covs if c.tree_row_id == "ft-mj"]
    assert len(claimed) == 1, [(c.metric, c.tree_row_id) for c in covs]
    assert len([c for c in covs if not c.tree_row_id]) == 1, "the rest are orphans"


def test_metric_no_sibling_declares_still_claims_the_path() -> None:
    """Preferring the indicator must not turn a known factor into an orphan."""
    from app.dataeng.dbt import service

    st = _st()
    covs = service.claim_published_metrics(st, _asset(), _df(metric="TV曝光量"))
    assert covs[0].tree_row_id == "ft-1", "an undeclared metric still anchors on its path"


def main() -> int:
    for fn in (test_matching_mart_claims_the_row_and_makes_no_indicator,
               test_unmatched_metric_becomes_an_orphan,
               test_siblings_on_one_path_each_claim_their_own_indicator,
               test_the_l3_fallback_will_not_hand_one_row_to_two_metrics,
               test_metric_no_sibling_declares_still_claims_the_path,
               test_human_pin_survives_republish,
               test_republish_replaces_only_this_asset):
        fn()
        print(f"ok  {fn.__name__}")
    print("all publish-claim tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
