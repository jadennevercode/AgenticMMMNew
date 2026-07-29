"""A screening gate closes on verdicts, and what it closed over stays closed.

Run: ``PYTHONPATH=. .venv/bin/python tests/test_gate_verdicts.py``

Two rules, both learned from one run of the reference case:

* 2.4 left six indicators on ``review`` — the AI's "needs a look" bucket — and
  every one of them reached the OLS, because only ``drop`` is read downstream.
  One was 竞品ND, near-singular in the design matrix, and it took the whole
  decomposition with it. A gate may not close while any row is still provisional.
* 2.5 and 2.6 are built on the verdicts as they stood when the selection was
  signed off. Editing one afterwards leaves the model asserting a filtering chain
  that no longer describes it, silently.
"""
from __future__ import annotations

from app.agents.artifact_edit import ArtifactEditError, apply_stat_scorecard
from app.agents.ledger import downstream_locked, provisional_rows
from app.domain.models import (
    QualityRow, QualityScorecard, StatScorecard, StatScoreRow,
)
from app.orchestrator.engine import GateBlocked
from app.store.state import ProjectState, danone_meta, initial_state


def _st() -> ProjectState:
    # initial_state seeds the blueprint's decision runtimes; the gates under test
    # are blueprint gates, so a bare ProjectState has none of them.
    st = initial_state(danone_meta())
    st.stat_scorecard = StatScorecard(rows=[
        StatScoreRow(id="s1", l4="竞品渠道扩张", indicator="竞品ND", disposition="review"),
        StatScoreRow(id="s2", l4="季节性趋势", indicator="温度", disposition="include"),
        StatScoreRow(id="s3", l4="价格变动", indicator="本品标价", disposition="drop"),
    ])
    st.quality_scorecard = QualityScorecard(rows=[
        QualityRow(id="q1", l4="旺点促销", indicator="花费", disposition="flag"),
        QualityRow(id="q2", l4="自有冰柜", indicator="已投放冰柜个数", disposition="accept"),
    ])
    return st


def test_provisional_rows_are_visible_per_layer() -> None:
    st = _st()
    assert provisional_rows(st, "statistical") == [("竞品渠道扩张", "竞品ND")]
    assert [l4 for l4, _ in provisional_rows(st, "quality")] == ["旺点促销"]


def test_a_gate_refuses_to_close_on_a_provisional_row() -> None:
    from app.agents.registry import build_engine

    st = _st()
    eng = build_engine()
    st.decisions["d-2.4"].status = "open"
    try:
        eng.resolve_decision(st, "d-2.4", "approve")
    except GateBlocked as exc:
        assert "竞品ND" in str(exc), exc
    else:
        raise AssertionError("d-2.4 closed with an indicator still awaiting review")
    assert st.decisions["d-2.4"].status == "open"


def test_the_gate_closes_once_every_row_has_a_verdict() -> None:
    from app.agents.registry import build_engine

    st = _st()
    eng = build_engine()
    st.decisions["d-2.4"].status = "open"
    for row in st.stat_scorecard.rows:
        if row.disposition == "review":
            row.disposition = "include"
    eng.resolve_decision(st, "d-2.4", "approve")
    assert st.decisions["d-2.4"].status == "resolved"


def test_upstream_locks_once_the_ols_selection_is_signed_off() -> None:
    st = _st()
    assert downstream_locked(st) is False
    apply_stat_scorecard(st, st.stat_scorecard)   # editable before the lock

    st.decisions["d-2.5"].status = "resolved"
    assert downstream_locked(st) is True
    try:
        apply_stat_scorecard(st, st.stat_scorecard)
    except ArtifactEditError as exc:
        assert "d-2.5" in str(exc), exc
    else:
        raise AssertionError("2.4 was editable after the OLS selection was signed off")


def test_the_range_layer_reads_the_2_5_scorecard() -> None:
    """2.5's verdicts are stored, not frozen onto the gate's resolution.

    They used to be: with nothing recording the drops, `d-2.5` had to photograph
    them at the moment it was answered, because excluding an indicator stops the
    next fit from flagging it and a live re-derivation would read that silence as
    "nothing was out of range". A stored verdict needs no photograph.
    """
    from app.agents.ledger import range_drop_pairs_by_object
    from app.domain.models import OlsRangeRow, OlsRangeScorecard

    st = _st()
    assert range_drop_pairs_by_object(st) == {}, "no sheet, no rejections"

    st.ols_scorecard = OlsRangeScorecard(rows=[
        OlsRangeRow(id="MT::B|冰柜|费用", object="MT::B", l4="冰柜", indicator="费用",
                    autoVerdict="reject", disposition="reject", decidedBy="human"),
        OlsRangeRow(id="MT::B|广告投放|花费", object="MT::B", l4="广告投放", indicator="花费",
                    autoVerdict="accept", disposition="accept"),
    ])
    assert range_drop_pairs_by_object(st) == {"MT::B": {("冰柜", "费用")}}


def test_the_2_5_sheet_outranks_a_stale_frozen_gate_answer() -> None:
    """Once a sheet exists it rules, even when it rejects nothing — otherwise a
    gate answer from before the review surface existed would keep re-applying on
    top of verdicts the human has since revised."""
    from app.agents.ledger import range_drop_pairs_by_object
    from app.domain.models import OlsRangeRow, OlsRangeScorecard

    st = _st()
    st.decisions["d-2.5"].status = "resolved"
    st.decisions["d-2.5"].resolution = {
        "optionId": "drop", "droppedPairsByObject": {"MT::B": [["冰柜", "费用"]]}}
    # Legacy project, no sheet → the frozen answer still applies.
    assert range_drop_pairs_by_object(st) == {"MT::B": {("冰柜", "费用")}}

    st.ols_scorecard = OlsRangeScorecard(rows=[
        OlsRangeRow(id="MT::B|冰柜|费用", object="MT::B", l4="冰柜", indicator="费用",
                    autoVerdict="reject", disposition="accept", decidedBy="human")])
    assert range_drop_pairs_by_object(st) == {}, (
        "the human kept it on the sheet; the old frozen drop must not override that")


def main() -> int:
    for fn in (test_provisional_rows_are_visible_per_layer,
               test_a_gate_refuses_to_close_on_a_provisional_row,
               test_the_gate_closes_once_every_row_has_a_verdict,
               test_the_range_layer_reads_the_2_5_scorecard,
               test_the_2_5_sheet_outranks_a_stale_frozen_gate_answer,
               test_upstream_locks_once_the_ols_selection_is_signed_off):
        fn()
        print(f"ok  {fn.__name__}")
    print("all gate-verdict tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
