"""Runnable checks for interview-driven data-request field edits (no LLM)."""
from app.agents import business as B
from app.domain.models import IndustryRef, ProjectMeta
from app.store.state import ProjectState

def test_apply_field_edits():
    by_l3 = {"品类": {"规模": ["市场规模", "增速"]}, "媒介": {"TV": ["TV花费"]}}
    edits = {
        "品类||规模": {"added": ["季节指数"], "removed": ["增速"]},
        "媒介||TV": {"added": [], "removed": []},
    }
    out = B._apply_field_edits(by_l3, edits)
    assert out["品类"]["规模"] == ["市场规模", "季节指数"], out["品类"]["规模"]  # removed 增速, added 季节指数
    assert out["媒介"]["TV"] == ["TV花费"]                                    # untouched
    # idempotent: a duplicate add is not doubled
    out2 = B._apply_field_edits(out, {"品类||规模": {"added": ["季节指数"], "removed": []}})
    assert out2["品类"]["规模"].count("季节指数") == 1, out2["品类"]["规模"]
    print("OK apply_field_edits")

def test_datareq_review_sheet():
    props = [{"op": "add", "l3": "品类", "l4": "规模", "indicator": "季节指数",
              "rationale": "访谈提到", "quote": "我们看季节性"},
             {"op": "remove", "l3": "媒介", "l4": "TV", "indicator": "TV花费",
              "rationale": "不单独跟踪", "quote": "TV没细分"}]
    sheet = B._datareq_review_sheet(props)
    assert sheet is not None and sheet["name"] == "Interview-driven changes (proposed)"
    assert len(sheet["rows"]) == 2
    assert B._datareq_review_sheet([]) is None
    print("OK datareq_review_sheet")


def test_record_edit_then_rerender_applies():
    # Simulate the endpoint's core: record an accepted 'add' then re-derive columns.
    meta = ProjectMeta(id="t-datareq", name="t", brand="b",
                       industry=IndustryRef(l1="beverage", l2="functional", l3="sports"),
                       createdAt="2026-01-01T00:00:00+00:00")
    st = ProjectState(project_id="t-datareq", meta=meta)
    st.data_request_field_edits.setdefault("品类||规模", {"added": [], "removed": [], "rejected": []})
    st.data_request_field_edits["品类||规模"]["added"].append("季节指数")
    by_l3 = {"品类": {"规模": ["市场规模"]}}
    applied = B._apply_field_edits(by_l3, st.data_request_field_edits)
    assert applied["品类"]["规模"] == ["市场规模", "季节指数"]
    print("OK record_edit_then_rerender_applies")


def main():
    test_apply_field_edits()
    test_datareq_review_sheet()
    test_record_edit_then_rerender_applies()

if __name__ == "__main__":
    main()
