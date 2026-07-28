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

def main():
    test_columns_and_rows()

if __name__ == "__main__":
    main()
