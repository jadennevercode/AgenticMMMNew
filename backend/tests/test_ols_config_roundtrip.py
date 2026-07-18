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
    st = ProjectState(project_id="ols-roundtrip")
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
    asyncio.run(data.propose_ols_setup(build_engine(), st, {"id": "2.5"}))
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


def test_propose_leaves_setup_state_unfitted() -> None:
    st = _proposed()
    art = st.artifact("a-ols-test")
    assert art is not None and art.state == "proposed"
    assert art.body["tree"] == [] and art.body["objects"] == []
    assert art.body["setup"]["configured"] is True
    assert st.ols_config is not None


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


def test_unticking_a_variable_changes_the_fit() -> None:
    """The whole point of 2.5x: the human's selection drives the regression."""
    st = _proposed()
    cfg = st.ols_config
    apply_ols_config(st, cfg)
    before = [o["drivers"] for o in st.artifact("a-ols-test").body["objects"] if not o["error"]]

    selected = [c for c in cfg.x_candidates if c.selected]
    assert len(selected) > 1
    selected[0].selected = False
    apply_ols_config(st, cfg)
    after = [o["drivers"] for o in st.artifact("a-ols-test").body["objects"] if not o["error"]]
    assert sum(after) < sum(before), (before, after)


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
