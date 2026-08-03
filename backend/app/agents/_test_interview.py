"""Runnable checks for the interview sheet + real-minutes rebuild (no LLM)."""
from app.agents import business as B
from app.store.state import ProjectState

def test_columns_and_rows():
    q = {"qType": "business", "question": "渠道占比?", "relatedFactorPath": "",
         "origin": "提纲", "finalAnswer": "约40%", "answerSource": "市场部纪要"}
    t = B._make_target("management", "Marketing", [q])
    sheets = B._interview_sheets([t])
    iv = next(s for s in sheets["sheets"] if s["name"] != "Overview")
    assert iv["columns"] == ["#", "Q Type", "Question", "Related Factor Path",
                             "Origin", "访谈回答", "回答来源"], iv["columns"]
    row = iv["rows"][0]
    assert row == ["1", "business", "渠道占比?", "", "提纲", "约40%", "市场部纪要"], row
    print("OK columns_and_rows")

def test_department_from_filename():
    f = B._department_from_filename
    assert f("市场部访谈.docx") == "市场部", f("市场部访谈.docx")
    assert f("Layer3_电商部_纪要.txt") == "电商部", f("Layer3_电商部_纪要.txt")
    assert f("Sales Dept interview.md") == "Sales Dept", f("Sales Dept interview.md")
    assert f("   .txt") == "", f("   .txt")
    # Only TRAILING markers are stripped — a department name that contains a
    # marker token mid-word must be preserved (not over-stripped).
    assert f("记录部访谈.docx") == "记录部", f("记录部访谈.docx")
    assert f("Interviewer_Training.docx") == "Interviewer Training", f("Interviewer_Training.docx")
    # Repeated trailing markers are all stripped.
    assert f("客户访谈纪要.docx") == "客户", f("客户访谈纪要.docx")
    assert f("销售部会议纪要.docx") == "销售部", f("销售部会议纪要.docx")
    print("OK department_from_filename")

def test_interview_sheet_names_excel_safe():
    # Excel sheet tabs must be ≤31 chars, free of []:*?/\, and unique within
    # the workbook — even when long department names truncate to a collision.
    long_a = "超长部门名称" * 6 + "A"          # >31 chars, unique tail A
    long_b = "超长部门名称" * 6 + "B"          # >31 chars, same 31-char prefix as A
    illegal = "市场[部]:x*?/\\y"               # contains every Excel-illegal char
    targets = [B._make_real_target(d, "", []) for d in (long_a, long_b, illegal)]
    sheets = B._interview_sheets(targets)
    names = [s["name"] for s in sheets["sheets"]]
    assert names[0] == "Overview", names
    tab_names = names[1:]
    assert all(len(n) <= 31 for n in tab_names), [(n, len(n)) for n in tab_names]
    assert not any(ch in n for n in tab_names for ch in "[]:*?/\\"), tab_names
    assert len(set(names)) == len(names), names   # all unique, incl. Overview
    print("OK interview_sheet_names_excel_safe")

def test_rebuild_targets():
    # outline: 3 business questions — q1 will be double-claimed (fill-first),
    # q2 answered once, q3 answered by no one (must be dropped).
    q1 = {"qType": "business", "question": "渠道占比?", "relatedFactorPath": "", "origin": "提纲"}
    q2 = {"qType": "business", "question": "新品节奏?", "relatedFactorPath": "", "origin": "提纲"}
    q3 = {"qType": "business", "question": "全年预算?", "relatedFactorPath": "", "origin": "提纲"}
    biz = [(q1, "Marketing"), (q2, "Management"), (q3, "Ops")]
    files = [("市场部访谈.docx", "..."), ("管理层访谈.docx", "...")]
    results = [
        {"department": "市场部", "participants": "张三",
         "answers": [{"n": 1, "answer": "约40%", "source": "市场部纪要"}],
         "new_questions": [{"question": "竞品促销力度?", "answer": "很强", "source": "市场部纪要"}]},
        {"department": "", "participants": "",
         # file-2 also tries to answer q1 (already claimed by file-1) — must be
         # ignored (fill-first), only its q2 answer should land.
         "answers": [{"n": 2, "answer": "季度上新", "source": "管理层纪要"},
                     {"n": 1, "answer": "50%(重复)", "source": "管理层纪要"}],
         "new_questions": []},
    ]
    targets = B._rebuild_targets_from_real_minutes(biz, files, results)
    # department lives on "team" now (layerZh is the literal filename layer marker,
    # blank here since neither file name carries one after dept extraction below —
    # note file-2's fallback department IS itself the layer word "管理层", so its
    # layerZh is "管理层" while file-1 (no layer marker) is blank).
    assert [t["team"] for t in targets] == ["市场部", "管理层访谈".replace("访谈", "")], \
        [t["team"] for t in targets]   # file-2 dept falls back to filename
    assert [t["layerZh"] for t in targets] == ["", "管理层"], [t["layerZh"] for t in targets]
    mkt, mgmt = targets[0], targets[1]
    mkt_origins = [(q["question"], q["origin"], q.get("finalAnswer", "")) for q in mkt["questions"]]
    mgmt_origins = [(q["question"], q["origin"], q.get("finalAnswer", "")) for q in mgmt["questions"]]
    assert ("渠道占比?", "提纲", "约40%") in mkt_origins, mkt_origins
    assert ("竞品促销力度?", "新问题", "很强") in mkt_origins, mkt_origins
    assert mkt["participants"] == "张三"
    # fill-first: q1 was claimed by file-1, so file-2's duplicate attempt at n=1
    # must NOT appear anywhere in file-2's rebuilt target.
    assert not any(q["question"] == "渠道占比?" for q in mgmt["questions"]), mgmt_origins
    assert ("新品节奏?", "提纲", "季度上新") in mgmt_origins, mgmt_origins
    # unanswered outline question (q3, 全年预算?) is dropped entirely — not in any target.
    all_questions = [q["question"] for t in targets for q in t["questions"]]
    assert "全年预算?" not in all_questions, all_questions
    print("OK rebuild_targets")

def test_merge_factor_side_keeps_changes():
    results = [{"factor_changes": [{"op": "add", "l1": "A", "l2": "", "l3": "", "l4": "",
                                    "indicator": "x", "quote": "q"}],
                "insights": [{"kind": "gap", "title": "t", "finding": "f", "confidence": 0.5}]}]
    merged = B._merge_factor_side(results)
    assert len(merged["factor_changes"]) == 1 and len(merged["insights"]) == 1
    print("OK merge_factor_side")

def test_rebuild_targets_dedupes_duplicate_department():
    # Two uploaded files both resolve to the SAME department label (e.g. both
    # declare "市场部", or both fall back to the same filename-derived label).
    # Without disambiguation this produces two targets with the same
    # _target_id("field", dept) and the same _interview_sheets tab name — an
    # illegal duplicate sheet name on xlsx export.
    q1 = {"qType": "business", "question": "渠道占比?", "relatedFactorPath": "", "origin": "提纲"}
    biz = [(q1, "Marketing")]
    files = [("市场部访谈1.docx", "..."), ("市场部访谈2.docx", "...")]
    results = [
        {"department": "市场部", "participants": "张三",
         "answers": [{"n": 1, "answer": "40%", "source": "市场部纪要1"}], "new_questions": []},
        {"department": "市场部", "participants": "李四",
         "answers": [], "new_questions": [{"question": "新品铺货率?", "answer": "60%",
                                          "source": "市场部纪要2"}]},
    ]
    targets = B._rebuild_targets_from_real_minutes(biz, files, results)
    assert len(targets) == 2, targets
    t1, t2 = targets
    assert t1["id"] != t2["id"], (t1["id"], t2["id"])
    # department (disambiguated) lives on "team"; neither filename carries a layer
    # marker, so layerZh is blank for both.
    assert t1["team"] != t2["team"], (t1["team"], t2["team"])
    assert t1["team"] == "市场部", t1["team"]
    assert t2["team"] == "市场部 (2)", t2["team"]
    assert t1["layerZh"] == "" and t2["layerZh"] == "", (t1["layerZh"], t2["layerZh"])
    print("OK rebuild_targets_dedupes_duplicate_department")

def test_layer_from_filename():
    f = B._layer_from_filename
    assert f("Layer3_电商部_纪要.txt") == "Layer3", f("Layer3_电商部_纪要.txt")
    assert f("第2层_管理层访谈.docx") == "第2层", f("第2层_管理层访谈.docx")
    assert f("管理层_商务部访谈.docx") == "管理层", f("管理层_商务部访谈.docx")
    assert f("商务部访谈.docx") == "", f("商务部访谈.docx")   # no layer marker → blank
    print("OK layer_from_filename")

def test_real_target_layer_and_dept():
    # filename with a layer marker: layer literal + clean department
    biz = []
    files = [("Layer3_电商部_纪要.txt", "..."), ("商务部访谈.docx", "...")]
    results = [{"department": "", "answers": [], "new_questions": []},
               {"department": "", "answers": [], "new_questions": []}]
    t = B._rebuild_targets_from_real_minutes(biz, files, results)
    assert t[0]["layerZh"] == "Layer3" and t[0]["team"] == "电商部", t[0]
    assert t[1]["layerZh"] == "" and t[1]["team"] == "商务部", t[1]   # no layer → blank
    print("OK real_target_layer_and_dept")

def test_interview_sheets_blank_layer_tab():
    # No layer marker (real-filename case) → tab/title fall back to team alone,
    # no leading "·" artifact; meta line drops the "Layer: ... | " segment.
    blank = B._make_real_target("电商部", "", [])
    sheets = B._interview_sheets([blank])
    tab = next(s for s in sheets["sheets"] if s["name"] != "Overview")
    assert tab["name"] == "电商部", tab["name"]
    assert tab["preRows"][0] == ["电商部"], tab["preRows"][0]
    assert "Layer:" not in tab["preRows"][1][0], tab["preRows"][1]
    assert tab["preRows"][1][0].startswith("Duration:"), tab["preRows"][1]

    # A literal layer marker present → tab/title keep the "layer·team" form and
    # the meta line keeps its "Layer: ... | " segment.
    layered = B._make_real_target("电商部", "", [], layer="Layer3")
    sheets2 = B._interview_sheets([layered])
    tab2 = next(s for s in sheets2["sheets"] if s["name"] != "Overview")
    assert tab2["name"] == "Layer3·电商部", tab2["name"]
    assert tab2["preRows"][0] == ["Layer3 · 电商部"], tab2["preRows"][0]
    assert tab2["preRows"][1][0].startswith("Layer: Layer3  |  Duration:"), tab2["preRows"][1]
    print("OK interview_sheets_blank_layer_tab")

def test_bu_stats_coverage_by_department():
    # Real departments live on "team"; layerZh is blank for real filenames with
    # no explicit layer marker, so the coverage buckets must key off team (not
    # collapse into one blank "—" bucket).
    st = ProjectState()
    st.analysis["interview_targets"] = [
        {"layerZh": "", "layer": "", "team": "电商部", "questions": [{}, {}]},
        {"layerZh": "", "layer": "", "team": "市场部", "questions": [{}]},
        {"layerZh": "Layer3", "layer": "Layer3", "team": "客服部", "questions": [{}, {}, {}]},
    ]
    stats = B._bu_stats(st)
    assert stats["cats"] == {"电商部": 2, "市场部": 1, "客服部": 3}, stats["cats"]
    print("OK bu_stats_coverage_by_department")

def test_apply_interview_removals():
    from app.store.state import ProjectState
    from app.domain.models import ProjectMeta, IndustryRef, FactorTree, FactorRow
    st = ProjectState(meta=ProjectMeta(id="t", name="t", brand="b", createdAt="2026-01-01T00:00:00+00:00",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional")))
    keep = FactorRow(id="k", l3="电商", l4="平台", indicator="电商GMV", source="template", status="baseline")
    drop = FactorRow(id="d", l3="批发", l4="经销", indicator="经销商出货", source="template", status="accepted")
    st.factor_tree = FactorTree(rows=[keep, drop])
    n = B._apply_interview_removals(st, [{"op": "remove", "indicator": "经销商出货",
                                          "rationale": "没有月度台账", "quote": "经销出货没系统数据"}])
    assert n == 1, n
    d = next(r for r in st.factor_tree.rows if r.id == "d")
    assert d.status == "proposed" and d.proposal_kind == "remove" and d.source == "interview", d
    k = next(r for r in st.factor_tree.rows if r.id == "k")
    assert k.status == "baseline", "non-matching row untouched"
    # a remove with no matching row demotes nothing
    assert B._apply_interview_removals(st, [{"op": "remove", "indicator": "不存在指标"}]) == 0

    # Narrowing: a recurring indicator name under two different l3/l4 branches —
    # a change that supplies BOTH the indicator AND a specific l3/l4 must demote
    # only the row matching that branch, not every row sharing the indicator.
    spend_a = FactorRow(id="sa", l3="电商", l4="平台A", indicator="花费", source="template", status="accepted")
    spend_b = FactorRow(id="sb", l3="批发", l4="经销B", indicator="花费", source="template", status="accepted")
    st.factor_tree = FactorTree(rows=[spend_a, spend_b])
    n2 = B._apply_interview_removals(st, [{"op": "remove", "indicator": "花费", "l3": "电商", "l4": "平台A",
                                           "rationale": "重复统计", "quote": "这个花费口径重复了"}])
    assert n2 == 1, n2
    sa = next(r for r in st.factor_tree.rows if r.id == "sa")
    sb = next(r for r in st.factor_tree.rows if r.id == "sb")
    assert sa.status == "proposed" and sa.proposal_kind == "remove" and sa.source == "interview", sa
    assert sb.status == "accepted", "other branch sharing the indicator must stay untouched"

    # Back-compat: indicator given with NO l3/l4 on the change still demotes
    # every row matching that indicator tree-wide.
    spend_c = FactorRow(id="sc", l3="电商", l4="平台A", indicator="花费", source="template", status="accepted")
    spend_d = FactorRow(id="sd", l3="批发", l4="经销B", indicator="花费", source="template", status="accepted")
    st.factor_tree = FactorTree(rows=[spend_c, spend_d])
    n3 = B._apply_interview_removals(st, [{"op": "remove", "indicator": "花费",
                                           "rationale": "全部删减", "quote": "花费口径都不要了"}])
    assert n3 == 2, n3
    assert all(r.status == "proposed" and r.proposal_kind == "remove" for r in st.factor_tree.rows), \
        st.factor_tree.rows
    print("OK apply_interview_removals")

def test_writeback_no_changes_guard_includes_removed_n():
    # Fix-review finding: when a transcript's ONLY factor changes are removals,
    # removed_n>0 but adds (=changes after the split) is empty — the "No
    # interview-driven factor changes were extracted ... re-run if the model
    # timed out" finding must NOT also fire (misleading after a real removal
    # succeeded). writeback_minutes is LLM-coupled (each call goes through
    # _digest_transcript -> get_llm().json over the network), so rather than
    # fabricate an LLM call we characterize the actual guard in source: it must
    # require BOTH "no adds" and "no removes", not bare "not changes". The
    # removal mechanics themselves (row demoted to proposed/remove/interview)
    # are already exercised end-to-end by test_apply_interview_removals above.
    import inspect
    src = inspect.getsource(B.writeback_minutes)
    assert "if not changes and not removed_n:" in src, src
    print("OK writeback_no_changes_guard_includes_removed_n")

def main():
    test_columns_and_rows()
    test_department_from_filename()
    test_rebuild_targets()
    test_merge_factor_side_keeps_changes()
    test_rebuild_targets_dedupes_duplicate_department()
    test_interview_sheet_names_excel_safe()
    test_layer_from_filename()
    test_real_target_layer_and_dept()
    test_interview_sheets_blank_layer_tab()
    test_bu_stats_coverage_by_department()
    test_apply_interview_removals()
    test_writeback_no_changes_guard_includes_removed_n()

if __name__ == "__main__":
    main()
