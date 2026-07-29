"""The 2.5 OLS setup round-trip: propose → edit → apply (re-fit) → artifact.

Locks the contract the Process steps rely on: `apply_ols_config` persists the
config, re-fits synchronously, re-renders `a-ols-test` and syncs the blackboard —
so a human can adjust Y / X / settings and see a new fit without `rework`.

Runnable with pytest or plain python (asserts run under __main__).
"""
from __future__ import annotations

import asyncio

from app.agents.artifact_edit import apply_ols_config
from app.agents.ols_review import build_ols_proposal
from app.agents.registry import build_engine
from app.domain.models import IndustryRef, ProjectMeta
from app.store.state import ProjectState


def _state() -> ProjectState:
    # No project_id on purpose: `dataset_cache._allow_reference` only serves the
    # Danone reference table to the seeded demo or an explicit opt-in, so a state
    # carrying an arbitrary id resolves to *no data* and every assertion below
    # would be vacuously about an empty fit.
    st = ProjectState()
    st.meta = ProjectMeta(
        id="ols-roundtrip", name="Roundtrip", brand="B",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
        createdAt="2026-01-01",
    )
    return st


def _proposed() -> ProjectState:
    """A state after step 1 (2.5 propose)."""
    from app.agents import data

    st = _state()
    asyncio.run(data.fit_models(build_engine(), st, {"id": "2.5"}))
    return st


def test_proposal_is_grounded() -> None:
    st = _state()
    cfg = build_ols_proposal(st)
    assert cfg.y_candidates and cfg.x_candidates
    # Exactly one recommended response per model object, and a default chosen.
    objects = {c.object for c in cfg.y_candidates}
    for obj in objects:
        recs = [c for c in cfg.y_candidates if c.object == obj and c.recommended]
        assert len(recs) == 1, obj
        assert any(y.object == obj for y in cfg.y), obj
    # Never hand back an empty selection — the fit needs at least one variable.
    assert any(c.selected for c in cfg.x_candidates)
    # Stats are real numbers carried over from 2.4's scoring, not placeholders.
    assert any(c.vif > 1.0 or abs(c.pearson) > 0.0 for c in cfg.x_candidates)


def test_task_2_5_searches_and_fits_in_one_step() -> None:
    """Since the v3 revamp 2.5 is a single task: it searches each L4's candidate
    indicators and fits the winning setup, rather than only proposing one for a
    separate confirm step (the old 2.5y/2.5x/2.5p chain is gone)."""
    st = _proposed()
    art = st.artifact("a-ols-test")
    assert art is not None
    assert art.body["setup"]["configured"] is True
    assert st.ols_config is not None
    assert art.body["objects"], "2.5 must leave a fitted model behind"
    assert art.body["tree"], "2.5 must leave a populated factor tree behind"


def test_apply_config_refits_and_rerenders() -> None:
    st = _proposed()
    art = st.artifact("a-ols-test")
    v0 = art.version

    apply_ols_config(st, st.ols_config)
    art = st.artifact("a-ols-test")
    assert art.version > v0                      # bumped for the poll to pick up
    assert art.body["objects"], "the fit must produce model objects"
    assert art.body["tree"], "the fit must populate the factor tree"
    assert "prefit" in st.analysis              # blackboard synced for 2.6
    assert "ols_flagged" in st.analysis


def _in_model(st) -> set[tuple[str, str, str]]:
    """(object, l4, indicator) for every variable that actually entered a fit."""
    out: set[tuple[str, str, str]] = set()
    for node in st.artifact("a-ols-test").body["tree"]:
        for res in node.get("results") or []:
            if res.get("inModel") or res.get("contribution") is not None:
                out.add((res["object"], node["l4"], node["indicator"]))
    return out


def test_unticking_a_variable_changes_the_fit() -> None:
    """The whole point of 2.5x: the human's selection drives the regression.

    Two things make the naive version of this test lie, and both are real product
    behaviour rather than accidents:

    * candidates are **per model object** (`OlsXCandidate.object`), so unticking
      one row excludes that variable from *that* object's fit and no other;
    * the engine independently holds out variables the design cannot identify
      (`_drop_singular_drivers`), so unticking one that was already held out there
      is a genuine no-op, and unticking one that was in frees a slot a previously
      unidentifiable variable can take — leaving the driver *count* unchanged.

    So: pick a candidate that actually entered its own object's fit, and assert it
    leaves that object's fit.
    """
    st = _proposed()
    cfg = st.ols_config
    apply_ols_config(st, cfg)
    before = _in_model(st)
    assert before, "the first fit produced no drivers at all"

    victim = next((c for c in cfg.x_candidates
                   if c.selected and (c.object, c.l4, c.indicator) in before), None)
    assert victim is not None, "no ticked candidate actually entered its object's fit"

    victim.selected = False
    apply_ols_config(st, cfg)
    after = _in_model(st)

    key = (victim.object, victim.l4, victim.indicator)
    assert key in before and key not in after, (
        f"unticking {key} did not remove it from that object's fit")


def test_money_response_switches_the_roi_unit() -> None:
    """Choosing a money Y in 2.5y turns ROI into a real revenue/spend ratio."""
    st = _proposed()
    cfg = st.ols_config
    money = next((c for c in cfg.y_candidates if c.is_money), None)
    if money is None:  # pragma: no cover — reference data always has one
        print("  ~ skipped (no money response candidate)")
        return
    cfg.y = [y for y in cfg.y if y.object != money.object] + [
        type(cfg.y[0])(object=money.object, metric=money.metric,
                       metricType=money.metric_type, isMoney=True)
    ]
    apply_ols_config(st, cfg)
    obj = next((o for o in st.artifact("a-ols-test").body["objects"]
                if o["object"] == money.object), None)
    assert obj is not None and not obj["error"], obj
    assert obj["yMetric"] == money.metric
    assert obj["roiUnit"] == "revenue/spend"


def test_bad_setup_does_not_raise() -> None:
    """An empty selection must degrade to per-object errors, never a 500."""
    st = _proposed()
    cfg = st.ols_config
    for c in cfg.x_candidates:
        c.selected = False
    apply_ols_config(st, cfg)          # must not raise
    body = st.artifact("a-ols-test").body
    assert body["tree"] == []
    assert all(o["error"] for o in body["objects"]), "each object should report why"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("all ols_config roundtrip tests passed")
