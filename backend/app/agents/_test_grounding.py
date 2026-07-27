"""Grounding material is budgeted once, and truncation is visible.

Run: ``PYTHONPATH=. .venv/bin/python -m app.agents._test_grounding``
"""
from __future__ import annotations

from app.agents.common import clip, grounding_budget, truncation_finding


def test_under_budget_is_untouched() -> None:
    r = clip("hello", label="SOW")
    assert r.text == "hello"
    assert r.truncated is False and r.dropped == 0 and r.kept_ratio == 1.0


def test_over_budget_reports_what_it_dropped() -> None:
    r = clip("x" * 100, budget=40, label="materials")
    assert len(r.text) == 40
    assert r.truncated is True and r.dropped == 60
    assert abs(r.kept_ratio - 0.4) < 1e-9
    assert r.label == "materials"


def test_default_budget_is_generous() -> None:
    assert grounding_budget() >= 100_000, \
        "the point of the change is that whole documents reach the model"


def test_finding_names_the_source_and_the_share() -> None:
    kept = clip("y" * 10, label="notes")
    cut = clip("x" * 1000, budget=100, label="materials")
    f = truncation_finding([kept, cut])
    assert f is not None
    assert "materials" in f.text and "10%" in f.text
    assert "notes" not in f.text, "only truncated sources are reported"
    assert f.tone == "flag"


def test_no_finding_when_nothing_was_cut() -> None:
    assert truncation_finding([clip("short", label="a")]) is None


def test_empty_text_is_safe() -> None:
    r = clip("", label="empty")
    assert r.text == "" and r.kept_ratio == 1.0 and r.truncated is False


def main() -> int:
    for fn in (test_under_budget_is_untouched,
               test_over_budget_reports_what_it_dropped,
               test_default_budget_is_generous,
               test_finding_names_the_source_and_the_share,
               test_no_finding_when_nothing_was_cut,
               test_empty_text_is_safe):
        fn()
        print(f"ok  {fn.__name__}")
    print("all grounding budget tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
