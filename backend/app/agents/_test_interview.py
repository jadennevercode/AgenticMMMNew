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

def main():
    test_columns_and_rows()
    test_department_from_filename()

if __name__ == "__main__":
    main()
