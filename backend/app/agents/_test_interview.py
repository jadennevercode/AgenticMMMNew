"""Runnable checks for the interview sheet + real-minutes rebuild (no LLM)."""
from app.agents import business as B

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
    assert [t["layerZh"] for t in targets] == ["市场部", "管理层访谈".replace("访谈", "")], \
        [t["layerZh"] for t in targets]   # file-2 dept falls back to filename
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
    assert t1["layerZh"] != t2["layerZh"], (t1["layerZh"], t2["layerZh"])
    assert t1["team"] != t2["team"], (t1["team"], t2["team"])
    assert t1["layerZh"] == "市场部", t1["layerZh"]
    assert t2["layerZh"] == "市场部 (2)", t2["layerZh"]
    print("OK rebuild_targets_dedupes_duplicate_department")

def main():
    test_columns_and_rows()
    test_department_from_filename()
    test_rebuild_targets()
    test_merge_factor_side_keeps_changes()
    test_rebuild_targets_dedupes_duplicate_department()
    test_interview_sheet_names_excel_safe()

if __name__ == "__main__":
    main()
