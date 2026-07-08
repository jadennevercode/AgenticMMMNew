"""Integration test for the S2 Data Intake & Quality module.

Runs the deterministic (M-class) S2 handlers on the real reference dataset and
asserts the editable structured objects, blackboard, gate questions and metric
selection all behave. No LLM calls. Runnable with pytest or plain python.
"""
from __future__ import annotations

import asyncio

from app.agents import data as data_agent
from app.agents.data import accepted_metric_labels, quality_sheet
from app.agents.registry import build_engine
from app.domain import blueprint as bp
from app.domain.models import QualityScorecard
from app.store.state import danone_meta, initial_state


def _task(tid: str) -> dict:
    return next(t for t in bp.TASKS if t["id"] == tid)


def test_2_11_scorecard_roundtrip() -> None:
    st = initial_state(danone_meta())
    eng = build_engine()
    asyncio.run(data_agent.score_data(eng, st, _task("2.11")))

    card = st.quality_scorecard
    assert card is not None and len(card.rows) > 0
    # Every row carries the four dimensions + a disposition.
    r0 = card.rows[0]
    assert r0.disposition in ("accept", "flag", "drop")
    assert 0.0 <= r0.total <= 4.0

    # Artifact re-rendered with the disposition columns.
    art = st.artifact("a-quality-scorecard")
    assert art is not None
    score_sheet = art.body["sheets"][1]
    assert score_sheet["columns"][-2:] == ["处置", "备注"]

    # Blackboard accepted-metric list excludes drops.
    kept = accepted_metric_labels(card)
    dropped = [r for r in card.rows if r.disposition == "drop"]
    assert len(kept) == len(card.rows) - len(dropped)
    assert st.analysis["quality"]["accepted_metrics"] == kept

    # Client Q&A tracker seeded.
    assert st.client_qa is not None and len(st.client_qa.rows) > 0


def test_quality_disposition_drives_blackboard() -> None:
    st = initial_state(danone_meta())
    eng = build_engine()
    asyncio.run(data_agent.score_data(eng, st, _task("2.11")))
    card = st.quality_scorecard

    # Flip the first *kept* metric to drop → accepted count falls by one.
    before = len(accepted_metric_labels(card))
    first_kept = next(r for r in card.rows if r.disposition != "drop")
    rows = [r.model_copy(update={"disposition": "drop"}) if r.id == first_kept.id else r
            for r in card.rows]
    edited = QualityScorecard(rows=rows)
    assert len(accepted_metric_labels(edited)) == before - 1
    # Re-render still produces a valid 2-sheet body.
    assert [s["name"] for s in quality_sheet(edited)["sheets"]] == ["2.11打分规则", "2.12数据质量评分"]


def test_2_33_screening_gate_question() -> None:
    st = initial_state(danone_meta())
    eng = build_engine()
    asyncio.run(data_agent.stat_screening(eng, st, _task("2.33")))
    assert st.artifact("a-stat-tests") is not None
    assert "screening_acceptable" in st.analysis
    # The G2.33 gate question is data-driven (mentions the Acceptable count).
    q = st.decisions["d-2.33"].question
    assert "Acceptable" in q


def test_2_34_metric_selection() -> None:
    st = initial_state(danone_meta())
    st.analysis["factor_l4"] = ["市场规模"]  # accepted factor with no usable driver
    eng = build_engine()
    asyncio.run(data_agent.pre_fit(eng, st, _task("2.34")))

    art = st.artifact("a-model-input")
    assert art is not None
    sheets = {s["name"]: s for s in art.body["sheets"]}
    assert "指标筛选" in sheets and "模型对象" in sheets
    assert sheets["指标筛选"]["columns"][0] == "L4 因子"

    selected = st.analysis["selected_metrics"]
    assert len(selected) > 0
    for info in selected.values():
        assert "metric" in info and "in_range" in info
    # The accepted-but-undriven factor is warned.
    assert any("市场规模" in w for w in st.analysis["selection_warnings"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all S2 round-trip tests passed")
