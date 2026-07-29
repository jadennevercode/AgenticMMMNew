"""2.5's range verdicts: the AI's proposal, the human's override, and the merge.

The merge is where this can quietly go wrong in two opposite directions, and both
would be invisible on screen:

* refreshing a re-fit over a row the human already ruled on **reverts their call**;
* dropping rows the new fit no longer mentions **deletes the rejection** that
  removed them, and the indicator walks back into the model.

Runnable with pytest or plain python (asserts run under __main__).
"""
from __future__ import annotations

from app.agents import ols_scorecard as sc
from app.domain.models import OlsRangeScorecard
from app.store.state import ProjectState


def _tree_row(indicator: str, status: str = "inRange", *, object: str = "MT::A",
              ai: str = "consistent", l4: str = "TV", reason: str = "") -> dict:
    return {"object": object, "treeRowId": f"ft-{indicator}", "l1": "MARKETING FACTOR",
            "l2": "品牌传播", "l3": "品牌传播", "l4": l4, "indicator": indicator,
            "metric": indicator, "coef": 1.0, "tValue": 3.0, "pValue": 0.01,
            "significant": True, "roi": 2.0, "contribution": 10.0,
            "roiRange": "1.0–4.0", "contributionRange": "5–20%",
            "roiStatus": "in", "contributionStatus": "in", "rangeSource": "knowledge",
            "status": status, "flagReason": reason, "aiVerdict": ai, "aiRationale": "because"}


def _st(rows: list[dict]) -> tuple[ProjectState, dict]:
    return ProjectState(), {"tree": rows}


# ── the recommendation ──────────────────────────────────────────────────────

def test_out_of_range_is_recommended_reject() -> None:
    verdict, why = sc.recommend(_tree_row("TV", "review", reason="ROI 9 outside 1.0–4.0"))
    assert verdict == "reject"
    assert "outside" in why


def test_implausible_rejects_even_without_a_band() -> None:
    """`noBenchmark` is unfalsifiable on arithmetic alone — if the AI says the
    coefficient cannot be believed, that is the only signal there is."""
    verdict, _ = sc.recommend(_tree_row("TV", "noBenchmark", ai="implausible"))
    assert verdict == "reject"


def test_questionable_does_not_reject() -> None:
    """The arithmetic passed. Turning a hedge into a rejection drops variables
    nobody decided to drop."""
    verdict, why = sc.recommend(_tree_row("TV", "inRange", ai="questionable"))
    assert verdict == "accept"
    assert "questionable" in why.lower()


def test_in_range_accepts() -> None:
    assert sc.recommend(_tree_row("TV"))[0] == "accept"


# ── the merge ───────────────────────────────────────────────────────────────

def test_rows_an_earlier_layer_already_ruled_are_not_offered() -> None:
    st, body = _st([_tree_row("A"), _tree_row("B", "dropped"),
                    _tree_row("C", "notMapped"), _tree_row("D", "notInModel")])
    card = sc.build_scorecard(st, body)
    assert [r.indicator for r in card.rows] == ["A"], (
        "2.5 must not re-offer a verdict an earlier layer already made")


def test_a_human_verdict_survives_a_refit() -> None:
    st, body = _st([_tree_row("TV", "review", reason="ROI out")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    tv = next(r for r in st.ols_scorecard.rows if r.indicator == "TV")
    assert tv.disposition == "reject"

    # The human disagrees: keep it despite the band.
    tv.disposition = "accept"
    tv.decided_by = "human"
    tv.note = "New creative, band is stale."

    # A re-fit still finds it out of range and still recommends rejecting it.
    card = sc.build_scorecard(st, {"tree": [_tree_row("TV", "review", reason="ROI out")]})
    row = next(r for r in card.rows if r.indicator == "TV")
    assert row.auto_verdict == "reject", "the recommendation must keep being computed"
    assert row.disposition == "accept", "the human's call must not be reverted by a re-fit"
    assert row.decided_by == "human"
    assert row.note == "New creative, band is stale."


def test_the_ai_recommendation_still_moves_on_untouched_rows() -> None:
    st, body = _st([_tree_row("TV", "inRange")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    assert st.ols_scorecard.rows[0].disposition == "accept"

    card = sc.build_scorecard(st, {"tree": [_tree_row("TV", "review", reason="ROI out")]})
    assert next(r for r in card.rows if r.indicator == "TV").disposition == "reject", (
        "a row the human never touched must follow the fresh recommendation")


def test_a_rejection_survives_the_refit_that_erases_its_evidence() -> None:
    """The reason this is stored state rather than a re-derivation. Rejecting
    excludes the indicator, so the next fit has no record of it and the tree stops
    mentioning it — reading that silence as "nothing was out of range" is exactly
    how a dropped variable used to walk back in."""
    st, body = _st([_tree_row("TV", "review", reason="ROI out"), _tree_row("OOH")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    assert sc.reject_pairs_by_object(st) == {"MT::A": {("tv", "tv")}}

    # Re-fit without TV — it was excluded, so it cannot appear.
    card = sc.build_scorecard(st, {"tree": [_tree_row("OOH")]})
    st.ols_scorecard = card
    assert ("tv", "tv") in sc.reject_pairs_by_object(st).get("MT::A", set()), (
        "the rejection must persist once its own evidence is gone")


def test_an_accepted_row_absent_from_the_refit_is_dropped() -> None:
    """The mirror of the rule above: only rejections are carried forward. An
    accepted row that stops being fitted for some other reason (its channel lost
    its data) must not linger as a stale accept."""
    st, body = _st([_tree_row("TV"), _tree_row("OOH")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    card = sc.build_scorecard(st, {"tree": [_tree_row("OOH")]})
    assert [r.indicator for r in card.rows] == ["OOH"]


def test_rejections_are_keyed_per_model_object() -> None:
    """A factor can be out of range in one channel and fine in another; rejecting
    it in one must not remove it from the other's fit."""
    st, body = _st([_tree_row("TV", "review", object="MT::A", reason="out"),
                    _tree_row("TV", "inRange", object="EC::A")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    rejects = sc.reject_pairs_by_object(st)
    assert rejects == {"MT::A": {("tv", "tv")}}
    assert "EC::A" not in rejects


def test_no_verdict_is_structurally_impossible() -> None:
    st, body = _st([_tree_row("TV")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    assert sc.pending_rows(st) == []


def test_summary_counts_the_overrides() -> None:
    st, body = _st([_tree_row("TV", "review", reason="out"), _tree_row("OOH")])
    st.ols_scorecard = sc.build_scorecard(st, body)
    # `rows` is sorted by factor path, not insertion order — pick the row, don't index.
    tv = next(r for r in st.ols_scorecard.rows if r.indicator == "TV")
    tv.disposition = "accept"
    tv.decided_by = "human"
    s = sc.summary(st)
    assert s == {"total": 2, "accepted": 2, "rejected": 0, "byHuman": 1, "overridden": 1}


def test_no_scorecard_means_no_rejections() -> None:
    assert sc.reject_pairs_by_object(ProjectState()) == {}
    assert sc.build_scorecard(ProjectState(), {}).rows == []
    assert OlsRangeScorecard().rows == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all 2.5 range-scorecard tests passed")
