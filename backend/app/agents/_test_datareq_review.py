"""Runnable checks for interview-driven data-request field edits (no LLM)."""
from app.agents import business as B

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

def main():
    test_apply_field_edits()

if __name__ == "__main__":
    main()
