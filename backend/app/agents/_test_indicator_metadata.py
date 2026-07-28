"""FND-001 checks: classifier correctness + role back-compat.

Run: PYTHONPATH=. .venv/bin/python -m app.agents._test_indicator_metadata
"""
from app.agents.indicator_metadata import classify_indicator, model_role


def _semantic(name: str) -> str:
    return classify_indicator(name).metric_type


def test_semantic_types():
    assert _semantic("本品月度销量") == "kpi_volume"
    assert _semantic("本品销售额") == "kpi_value"          # KPI wins over the 金额→spend gate
    assert _semantic("电商投放花费") == "spending"
    assert _semantic("媒介费用金额") == "spending"
    assert _semantic("NDWD 加权铺货率") == "rate"
    assert _semantic("门店覆盖占比") == "rate"
    assert _semantic("价格指数") == "index"
    assert _semantic("品牌情感score") == "index"
    assert _semantic("门店家数") == "count"
    assert _semantic("某未知驱动") == "other"


def test_aggregation_and_format():
    ndwd = classify_indicator("NDWD 覆盖率")
    assert ndwd.aggregation == "average" and ndwd.fmt == "percent"   # DATA-007 tie-in
    spend = classify_indicator("投放花费")
    assert spend.aggregation == "sum" and spend.fmt == "money" and spend.currency == "CNY"
    vol = classify_indicator("本品销量")
    assert vol.aggregation == "sum" and vol.currency is None


def test_role_backcompat():
    """model_role(classify(...)) must reproduce the legacy Y/spending/X tagging."""
    import re
    kpi = re.compile(r"本品.*(销量|销售)|kpi|本品月度销量|offtake|本品.*volume", re.I)
    spend = re.compile(r"花费|费用|投放|金额|spend|promotion", re.I)

    def legacy(m: str) -> str:
        if kpi.search(m):
            return "Y"
        if spend.search(m):
            return "spending"
        return "X"

    for name in ["本品月度销量", "本品销售额", "kpi offtake", "电商投放花费",
                 "媒介费用", "促销金额", "NDWD 覆盖率", "价格指数", "门店家数",
                 "某驱动因子", "TV GRP", "线上曝光量"]:
        got = model_role(classify_indicator(name).metric_type)
        assert got == legacy(name), f"{name}: {got} != {legacy(name)}"


if __name__ == "__main__":
    test_semantic_types()
    test_aggregation_and_format()
    test_role_backcompat()
    print("FND-001 indicator_metadata: ALL PASS")
