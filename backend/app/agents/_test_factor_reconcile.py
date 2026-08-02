"""Runnable checks for the factor-tree template↔materials reconcile (no LLM)."""
import asyncio

from app.domain.models import FactorRow, IndustryRef, ProjectMeta
from app.store.state import ProjectState
from app.agents import business as B

def _row(i, ind):
    return FactorRow(id=f"ft-tpl-{i}", l1="生意", l2="外部", l3="品类", l4="规模",
                     indicator=ind, dimension="", source="template", status="baseline")

def _bare_state():
    meta = ProjectMeta(id="t-reconcile", name="t", brand="b",
                       industry=IndustryRef(l1="beverage", l2="functional", l3="sports"),
                       createdAt="2026-01-01T00:00:00+00:00")
    return ProjectState(project_id="t-reconcile", meta=meta)

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

def test_reconcile_falls_back_without_materials():
    st = _bare_state()   # no uploaded materials in this project
    rows = [_row(0, "市场规模"), _row(1, "GDP增速")]
    out = asyncio.run(B._reconcile_baseline_with_materials(st, rows))
    assert [r.indicator for r in out] == ["市场规模", "GDP增速"]
    assert all(r.status == "baseline" for r in out)   # untouched verbatim
    print("OK reconcile_falls_back_without_materials")

def test_downgrade_sets_remove_kind():
    rows = [_row(0, "天气温度指数")]
    out = B._apply_reconcile_verdicts(rows, {1: {"decision": "downgrade", "rationale": "材料未提及"}})
    assert out[0].status == "proposed" and out[0].proposal_kind == "remove", out[0]
    print("OK downgrade_sets_remove_kind")

def test_accept_factor_rows_direction():
    from app.store.state import ProjectState
    from app.domain.models import ProjectMeta, IndustryRef, FactorTree, FactorRow
    st = ProjectState(meta=ProjectMeta(id="t", name="t", brand="b", createdAt="2026-01-01T00:00:00+00:00",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional")))
    add = FactorRow(id="a", indicator="x", source="ai", status="proposed", proposalKind="add")
    rem = FactorRow(id="b", indicator="y", source="template", status="proposed", proposalKind="remove")
    st.factor_tree = FactorTree(rows=[add, rem])
    B.accept_factor_rows(st, {"ai", "template"})
    assert st.factor_tree.rows[0].status == "accepted", "add-kind → accepted"
    assert st.factor_tree.rows[1].status == "rejected", "remove-kind → rejected (confirm removal)"
    print("OK accept_factor_rows_direction")

def main():
    test_apply_reconcile_verdicts()
    test_missing_verdict_defaults_to_keep()
    test_reconcile_falls_back_without_materials()
    test_downgrade_sets_remove_kind()
    test_accept_factor_rows_direction()

if __name__ == "__main__":
    main()
