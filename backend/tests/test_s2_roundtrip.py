"""Integration test for the S2 Data Intake & Validation chain.

Runs the real S2 handlers on the real reference dataset and asserts the property
the whole stage rests on: **a rejection is inherited**. An indicator the human
drops at any layer must not be re-scored by the next layer, must not be offered
back as a model variable, and must not reappear in the master table.

The LLM is stubbed out, so the A-class steps take their deterministic-score
fallback. That is deliberate: the subject here is the filter chain, and a machine
that happens to have a model configured must not silently turn these into slow,
non-deterministic network tests. Runnable with pytest or plain python.
"""
from __future__ import annotations

import asyncio

from app.agents import data as data_agent
from app.agents.data import accepted_metric_labels, quality_sheet
from app.agents.ledger import indicator_ledger, model_selection
from app.agents.registry import build_engine
from app.domain import blueprint as bp
from app.domain.models import QualityScorecard
from app.llm.volcano import LLMError
from app.store.state import danone_meta, initial_state


def _no_llm():
    raise LLMError("LLM disabled for tests")


data_agent.get_llm = _no_llm  # every A-step falls back to its computed scores


def _task(tid: str) -> dict:
    return bp.TASK_MAP[tid]


def _run(handler, st, tid):
    asyncio.run(handler(build_engine(), st, _task(tid)))


def _fresh():
    return initial_state(danone_meta())


# ── 2.2 · Data Quality Score ────────────────────────────────────────────────


def test_2_2_scorecard_roundtrip() -> None:
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")

    card = st.quality_scorecard
    assert card is not None and len(card.rows) > 0
    r0 = card.rows[0]
    assert r0.disposition in ("accept", "flag", "drop")
    assert 0.0 <= r0.total <= 1.0  # Total = product of four 0/0.5/1 dimensions

    art = st.artifact("a-quality-scorecard")
    assert art is not None
    score_sheet = art.body["sheets"][0]
    assert score_sheet["columns"][-2:] == ["Disposition", "Notes"]
    assert len(score_sheet["rows"]) == len(card.rows)

    kept = accepted_metric_labels(card)
    dropped = [r for r in card.rows if r.disposition == "drop"]
    assert len(kept) == len(card.rows) - len(dropped)
    assert st.analysis["quality"]["accepted_metrics"] == kept


def test_quality_disposition_drives_blackboard() -> None:
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    card = st.quality_scorecard

    before = len(accepted_metric_labels(card))
    first_kept = next(r for r in card.rows if r.disposition != "drop")
    rows = [r.model_copy(update={"disposition": "drop"}) if r.id == first_kept.id else r
            for r in card.rows]
    edited = QualityScorecard(rows=rows)
    assert len(accepted_metric_labels(edited)) == before - 1
    assert [s["name"] for s in quality_sheet(edited)["sheets"]] == ["Data Quality Score"]


def test_2_2_gate_question_is_data_driven() -> None:
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    q = st.decisions["d-2.2"].question
    assert "metric" in q.lower() or "verdict" in q.lower()


# ── 2.4 · Statistical Score ─────────────────────────────────────────────────


def test_2_4_screening_gate_question() -> None:
    st = _fresh()
    _run(data_agent.stat_screening, st, "2.4")
    assert st.artifact("a-stat-tests") is not None
    assert "screening_acceptable" in st.analysis
    assert "Acceptable" in st.decisions["d-2.4"].question


def test_2_4_does_not_rescore_what_2_2_dropped() -> None:
    """A settled quality drop must not come back as an open 2.4 row."""
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    victim = st.quality_scorecard.rows[0]
    victim.disposition = "drop"

    _run(data_agent.stat_screening, st, "2.4")
    scored = {(r.l4.strip().lower(), r.indicator.strip().lower())
              for r in st.stat_scorecard.rows}
    assert (victim.l4.strip().lower(), victim.indicator.strip().lower()) not in scored


# ── 2.5 · the OLS setup proposal ────────────────────────────────────────────


def test_2_5_locks_upstream_rejections_instead_of_hiding_them() -> None:
    """A rejected indicator stays visible in 2.5x — locked, and labelled with
    the layer that rejected it. Hiding it would leave the human no way to see
    where their variable went."""
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    victim = st.quality_scorecard.rows[0]
    victim.disposition = "drop"
    _run(data_agent.stat_screening, st, "2.4")
    _run(data_agent.propose_ols_setup, st, "2.5")

    cfg = st.ols_config
    assert cfg is not None and cfg.x_candidates
    key = (victim.l4.strip().lower(), victim.indicator.strip().lower())
    hit = next((c for c in cfg.x_candidates
                if (c.l4.strip().lower(), c.metric.strip().lower()) == key), None)
    if hit is not None:  # only if the victim is a driver (KPI rows are not offered)
        assert hit.locked and hit.locked_by == "quality"
        assert not hit.selected
        assert "quality" in hit.rationale.lower()
    # Nothing locked may ever be pre-ticked.
    assert not any(c.selected for c in cfg.x_candidates if c.locked)


# ── 2.6 · Master Data ───────────────────────────────────────────────────────


def test_2_6_master_data_carries_only_adopted_indicators() -> None:
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    _run(data_agent.stat_screening, st, "2.4")
    _run(data_agent.propose_ols_setup, st, "2.5")
    _run(data_agent.assemble_master_data, st, "2.6")

    art = st.artifact("a-master-data")
    assert art is not None
    body = art.body
    assert body["objects"], "at least one model object must assemble"
    assert [f["layer"] for f in body["funnel"]] == [
        "mapping", "quality", "signoff", "statistical", "selection", "range"]
    # The dimensions the user slices product × channel × region by.
    for dim in ("brand", "provinceGroup", "channelType", "channel", "grains"):
        assert dim in body["dimensions"]

    adopted = {(r["l4"].strip().lower(), r["indicator"].strip().lower())
               for r in body["adopted"]}
    rejected = {(r["l4"].strip().lower(), r["indicator"].strip().lower())
                for r in body["rejected"]}
    assert not (adopted & rejected), "an indicator cannot be both adopted and rejected"
    # Every rejected row explains itself.
    for r in body["rejected"]:
        assert r["rejectedAt"] and r["reason"]

    # The 2.6d gate reports what is actually being locked.
    assert "feature column" in st.decisions["d-2.6"].question


def test_2_6_honours_the_2_5x_variable_selection() -> None:
    """The master table must fit the variables the human ticked — not re-pick
    its own top-correlated set."""
    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    _run(data_agent.stat_screening, st, "2.4")
    _run(data_agent.propose_ols_setup, st, "2.5")

    cfg = st.ols_config
    ticked = [c for c in cfg.x_candidates if c.selected]
    assert len(ticked) >= 2, "need at least two ticked variables to untick one"
    victim = ticked[-1]
    victim.selected = False

    sel = model_selection(st)
    assert victim.metric.strip().lower() not in (sel.include or frozenset())
    _run(data_agent.assemble_master_data, st, "2.6")

    adopted = {r["indicator"].strip().lower() for r in st.artifact("a-master-data").body["adopted"]}
    assert victim.metric.strip().lower() not in adopted


def test_master_table_slices_by_product_channel_region() -> None:
    from app.agents.master_data import dimensions, master_table

    st = _fresh()
    dims = dimensions(st)
    assert dims["channelType"], "the reference case must expose channel types"

    full = master_table(st, grain="month")
    assert full["columns"][0] == "Period" and full["rows"]
    assert full["kpi"], "the response must be in the table it explains"

    one = master_table(st, channel_type=[dims["channelType"][0]], grain="year")
    assert one["rows"], "a real channel slice must return rows"
    assert len(one["rows"]) <= len(full["rows"])


def test_s4_training_fits_the_same_selection_s2_locked() -> None:
    """3.2 must train on what S2 locked, not re-pick its own drivers.

    This is the leak the ledger exists to close: `make_candidates` used to run
    with no exclude, no response and no variable list, so every quality drop,
    sign-off and human tick stopped at the S2 boundary.
    """
    from app.mmm import build_model_frame

    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    _run(data_agent.stat_screening, st, "2.4")
    _run(data_agent.propose_ols_setup, st, "2.5")

    cfg = st.ols_config
    ticked = [c for c in cfg.x_candidates if c.selected]
    assert len(ticked) >= 2
    victim = ticked[-1]
    victim.selected = False

    sel = model_selection(st)
    from app.agents.dataset_cache import model_df, model_objects
    df = model_df(st)
    obj = model_objects(st)[0]
    mf = build_model_frame(df, obj, exclude=sel.exclude, y_metric=sel.y_for(obj),
                           include=sel.include)
    # The frame S4 trains on carries the human's response and none of the
    # variables they unticked.
    assert sel.y_for(obj) is None or mf.y_col
    cols = {c.strip().lower() for c in mf.x_cols}
    assert victim.metric.strip().lower() not in cols


def test_master_table_never_carries_a_rejected_indicator() -> None:
    from app.agents.master_data import master_table

    st = _fresh()
    _run(data_agent.score_data, st, "2.2")
    victim = next(r for r in st.quality_scorecard.rows if r.indicator.strip())
    victim.disposition = "drop"

    t = master_table(st, grain="month")
    cols = {c.strip().lower() for c in t["columns"]}
    rejected = {r.key[1] for r in indicator_ledger(st) if not r.adopted}
    assert not (cols & rejected), "a dropped indicator must not reach the master table"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all S2 round-trip tests passed")
