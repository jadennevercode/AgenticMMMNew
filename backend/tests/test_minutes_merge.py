"""Per-file interview digests merge without dropping or duplicating.

BREAK 2 replaced the concatenate-then-truncate minutes path (which used only the
first ~5 of 12 transcripts) with one call per transcript + a pure merge. These
tests pin the merge: answers fill-first per question number, factor changes
dedup by their identity key, insights cap. The live per-file LLM call is covered
by the E2E run, not here.

Run: PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
"""
from __future__ import annotations

from app.agents.business import _MAX_INSIGHTS, _merge_minutes_digests


def _change(op, l4, indicator):
    return {"op": op, "l1": "A", "l2": "B", "l3": "C", "l4": l4,
            "indicator": indicator, "rationale": "r", "quote": "q"}


def test_answers_fill_first_across_files() -> None:
    # File A answers 1 and 3; B answers 3 (ignored, already filled) and 5;
    # C answers 5 (ignored) and 8.
    results = [
        {"answers": [{"n": 1, "answer": "a1", "source": "GM"},
                     {"n": 3, "answer": "a3-A", "source": "GM"}]},
        {"answers": [{"n": 3, "answer": "a3-B", "source": "Media"},
                     {"n": 5, "answer": "a5", "source": "Media"}]},
        {"answers": [{"n": 5, "answer": "a5-C", "source": "EC"},
                     {"n": 8, "answer": "a8", "source": "EC"}]},
    ]
    merged = _merge_minutes_digests(results)
    ans = merged["answers"]
    assert set(ans.keys()) == {1, 3, 5, 8}, set(ans.keys())
    assert ans[3]["answer"] == "a3-A", "first non-empty answer wins"
    assert ans[5]["answer"] == "a5", "first non-empty answer wins"


def test_empty_answers_are_skipped() -> None:
    results = [
        {"answers": [{"n": 2, "answer": "  ", "source": "x"}]},
        {"answers": [{"n": 2, "answer": "real", "source": "y"}]},
    ]
    merged = _merge_minutes_digests(results)
    assert merged["answers"][2]["answer"] == "real", "blank answer must not claim the slot"


def test_factor_changes_dedup_by_identity() -> None:
    results = [
        {"factor_changes": [_change("add", "D1", "ind1"), _change("add", "D2", "ind2")]},
        {"factor_changes": [_change("add", "D1", "ind1"),   # dup of the first
                            _change("modify", "D1", "ind1")]},  # same path, diff op → kept
    ]
    merged = _merge_minutes_digests(results)
    keys = {(c["op"], c["l4"], c["indicator"]) for c in merged["factor_changes"]}
    assert keys == {("add", "D1", "ind1"), ("add", "D2", "ind2"),
                    ("modify", "D1", "ind1")}, keys
    assert len(merged["factor_changes"]) == 3


def test_insights_capped() -> None:
    results = [{"insights": [{"kind": "connection", "title": f"t{i}",
                             "finding": "f", "confidence": 0.7}]} for i in range(6)]
    merged = _merge_minutes_digests(results)
    assert len(merged["insights"]) == _MAX_INSIGHTS, len(merged["insights"])


def test_non_dict_results_ignored() -> None:
    merged = _merge_minutes_digests([{}, None, "oops", {"answers": [{"n": 1, "answer": "ok"}]}])
    assert merged["answers"][1]["answer"] == "ok"
    assert merged["factor_changes"] == []


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll minutes-merge tests passed.")
