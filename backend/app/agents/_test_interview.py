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
    print("OK department_from_filename")

def test_rebuild_targets():
    # outline: 2 business questions
    q1 = {"qType": "business", "question": "渠道占比?", "relatedFactorPath": "", "origin": "提纲"}
    q2 = {"qType": "business", "question": "新品节奏?", "relatedFactorPath": "", "origin": "提纲"}
    biz = [(q1, "Marketing"), (q2, "Management")]
    files = [("市场部访谈.docx", "..."), ("管理层访谈.docx", "...")]
    results = [
        {"department": "市场部", "participants": "张三",
         "answers": [{"n": 1, "answer": "约40%", "source": "市场部纪要"}],
         "new_questions": [{"question": "竞品促销力度?", "answer": "很强", "source": "市场部纪要"}]},
        {"department": "", "participants": "",
         "answers": [{"n": 2, "answer": "季度上新", "source": "管理层纪要"}],
         "new_questions": []},
    ]
    targets = B._rebuild_targets_from_real_minutes(biz, files, results)
    assert [t["layerZh"] for t in targets] == ["市场部", "管理层访谈".replace("访谈", "")], \
        [t["layerZh"] for t in targets]   # file-2 dept falls back to filename
    mkt = targets[0]
    origins = [(q["question"], q["origin"], q.get("finalAnswer", "")) for q in mkt["questions"]]
    assert ("渠道占比?", "提纲", "约40%") in origins, origins
    assert ("竞品促销力度?", "新问题", "很强") in origins, origins
    assert mkt["participants"] == "张三"
    print("OK rebuild_targets")

def test_merge_factor_side_keeps_changes():
    results = [{"factor_changes": [{"op": "add", "l1": "A", "l2": "", "l3": "", "l4": "",
                                    "indicator": "x", "quote": "q"}],
                "insights": [{"kind": "gap", "title": "t", "finding": "f", "confidence": 0.5}]}]
    merged = B._merge_factor_side(results)
    assert len(merged["factor_changes"]) == 1 and len(merged["insights"]) == 1
    print("OK merge_factor_side")

def main():
    test_columns_and_rows()
    test_department_from_filename()
    test_rebuild_targets()
    test_merge_factor_side_keeps_changes()

if __name__ == "__main__":
    main()
