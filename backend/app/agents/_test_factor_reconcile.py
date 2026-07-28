"""Runnable checks for the factor-tree template↔materials reconcile (no LLM)."""
from app.domain.models import FactorRow
from app.agents import business as B

def _row(i, ind):
    return FactorRow(id=f"ft-tpl-{i}", l1="生意", l2="外部", l3="品类", l4="规模",
                     indicator=ind, dimension="", source="template", status="baseline")

def test_apply_reconcile_verdicts():
    rows = [_row(0, "市场规模"), _row(1, "GDP增速"), _row(2, "竞品数")]
    verdicts = {
        1: {"decision": "keep"},
        2: {"decision": "rename", "indicator": "宏观GDP同比"},
        3: {"decision": "downgrade", "rationale": "材料未提及"},
    }
    out = B._apply_reconcile_verdicts(rows, verdicts)
    assert out[0].status == "baseline" and out[0].indicator == "市场规模"
    assert out[1].status == "baseline" and out[1].indicator == "宏观GDP同比"
    assert out[1].rationale == "命名对齐材料"
    assert out[2].status == "proposed" and out[2].indicator == "竞品数"
    assert "待确认" in out[2].rationale
    # rows keep their identity/source
    assert all(r.source == "template" for r in out)
    print("OK apply_reconcile_verdicts")

def test_missing_verdict_defaults_to_keep():
    rows = [_row(0, "市场规模")]
    out = B._apply_reconcile_verdicts(rows, {})   # no verdicts at all
    assert out[0].status == "baseline" and out[0].indicator == "市场规模"
    print("OK missing_verdict_defaults_to_keep")

def main():
    test_apply_reconcile_verdicts()
    test_missing_verdict_defaults_to_keep()

if __name__ == "__main__":
    main()
