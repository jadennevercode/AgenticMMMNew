"""Per-file interview digests merge without dropping or duplicating.

BREAK 2 replaced the concatenate-then-truncate minutes path (which used only the
first ~5 of 12 transcripts) with one call per transcript + a pure merge. A later
break replaced the original combined answers+factor-side merge helper with two
successor functions that this file now drives:

- `_merge_factor_side(results)` — merges factor_changes (deduped by identity)
  and insights (capped) only, no answers.
- `_rebuild_targets_from_real_minutes(biz, files, results)` — rebuilds the
  interview targets keyed by each file's REAL department, backfilling outline
  answers fill-first by question number and attaching newly raised questions.

These tests pin both: factor changes dedup by their identity key, insights cap,
non-dict results are ignored, outline answers fill-first per question number
across files, and a blank/whitespace answer never claims a question's slot.
The live per-file LLM call is covered by the E2E run, not here.

Run: PYTHONPATH=. .venv/bin/python tests/test_minutes_merge.py
"""
from __future__ import annotations

from app.agents.business import (
    _MAX_INSIGHTS,
    _merge_factor_side,
    _rebuild_targets_from_real_minutes,
)


def _change(op, l4, indicator):
    return {"op": op, "l1": "A", "l2": "B", "l3": "C", "l4": l4,
            "indicator": indicator, "rationale": "r", "quote": "q"}


def test_factor_changes_dedup_by_identity() -> None:
    results = [
        {"factor_changes": [_change("add", "D1", "ind1"), _change("add", "D2", "ind2")]},
        {"factor_changes": [_change("add", "D1", "ind1"),   # dup of the first
                            _change("modify", "D1", "ind1")]},  # same path, diff op → kept
    ]
    merged = _merge_factor_side(results)
    keys = {(c["op"], c["l4"], c["indicator"]) for c in merged["factor_changes"]}
    assert keys == {("add", "D1", "ind1"), ("add", "D2", "ind2"),
                    ("modify", "D1", "ind1")}, keys
    assert len(merged["factor_changes"]) == 3


def test_insights_capped() -> None:
    results = [{"insights": [{"kind": "connection", "title": f"t{i}",
                             "finding": "f", "confidence": 0.7}]} for i in range(6)]
    merged = _merge_factor_side(results)
    assert len(merged["insights"]) == _MAX_INSIGHTS, len(merged["insights"])


def test_non_dict_results_ignored() -> None:
    merged = _merge_factor_side([{}, None, "oops", {"factor_changes": [_change("add", "D1", "ind1")]}])
    assert len(merged["factor_changes"]) == 1
    assert merged["insights"] == []


def test_answers_fill_first_across_files() -> None:
    # Outline has 8 business questions (only 1, 3, 5, 8 are ever answered).
    # File A answers 1 and 3; B answers 3 (must be ignored, already filled) and
    # 5; C answers 5 (ignored) and 8. Each file is its own department, so the
    # fill-first behavior is visible per-target rather than merged into one bag.
    def q(n):
        return {"qType": "business", "question": f"q{n}?", "relatedFactorPath": "", "origin": "提纲"}

    biz = [(q(n), "Dept") for n in range(1, 9)]
    files = [("A.docx", "..."), ("B.docx", "..."), ("C.docx", "...")]
    results = [
        {"department": "GM", "answers": [{"n": 1, "answer": "a1", "source": "GM"},
                                         {"n": 3, "answer": "a3-A", "source": "GM"}]},
        {"department": "Media", "answers": [{"n": 3, "answer": "a3-B", "source": "Media"},
                                            {"n": 5, "answer": "a5", "source": "Media"}]},
        {"department": "EC", "answers": [{"n": 5, "answer": "a5-C", "source": "EC"},
                                         {"n": 8, "answer": "a8", "source": "EC"}]},
    ]
    targets = _rebuild_targets_from_real_minutes(biz, files, results)
    # department now lives on "team" (layerZh is the filename layer marker, blank here)
    assert [t["team"] for t in targets] == ["GM", "Media", "EC"], targets

    def answer_of(target, question_text):
        return next((row["finalAnswer"] for row in target["questions"]
                     if row["question"] == question_text), None)

    gm, media, ec = targets
    assert answer_of(gm, "q1?") == "a1"
    assert answer_of(gm, "q3?") == "a3-A", "first non-empty answer wins"
    # q3 was already claimed by GM's file, so Media's duplicate attempt at n=3
    # must not appear in Media's rebuilt target at all.
    assert answer_of(media, "q3?") is None, "fill-first: later file's dup is dropped"
    assert answer_of(media, "q5?") == "a5", "first non-empty answer wins"
    # q5 was already claimed by Media's file, so EC's duplicate attempt is dropped.
    assert answer_of(ec, "q5?") is None, "fill-first: later file's dup is dropped"
    assert answer_of(ec, "q8?") == "a8"


def test_empty_answers_are_skipped() -> None:
    # File 1 "answers" q2 with whitespace only — must not claim the slot, so
    # file 2's real answer for the same question number still lands (on file 2's
    # own target, since fill-first tracks CLAIMED question numbers, not text).
    q1 = {"qType": "business", "question": "q1?", "relatedFactorPath": "", "origin": "提纲"}
    q2 = {"qType": "business", "question": "q2?", "relatedFactorPath": "", "origin": "提纲"}
    biz = [(q1, "Dept"), (q2, "Dept")]
    files = [("A.docx", "..."), ("B.docx", "...")]
    results = [
        {"department": "A", "answers": [{"n": 2, "answer": "  ", "source": "x"}]},
        {"department": "B", "answers": [{"n": 2, "answer": "real", "source": "y"}]},
    ]
    targets = _rebuild_targets_from_real_minutes(biz, files, results)
    a_target, b_target = targets
    assert a_target["questions"] == [], "blank answer must not claim the slot"
    assert b_target["questions"][0]["finalAnswer"] == "real"


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("\nAll minutes-merge tests passed.")
