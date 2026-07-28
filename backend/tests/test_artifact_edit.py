"""Smoke tests for chat-driven artifact editing (no live LLM calls).

The draft path needs the LLM, so these cover the deterministic halves: the
router/binding registry, the model-backed re-render helpers (shared with the
PUT routes), and `apply_proposal` for both free-form and model-backed artifacts.
Run:
    PYTHONPATH=. .venv/bin/python tests/test_artifact_edit.py
"""
from __future__ import annotations

from app.agents.artifact_edit import (
    MODEL_BINDINGS,
    ArtifactEditError,
    apply_proposal,
)
from app.domain.models import (
    ArtifactEditProposal,
    ArtifactInstance,
    FactorRow,
    FactorTree,
    IndustryRef,
    ProjectMeta,
    ProjectProfile,
)
from app.store.state import initial_state


def _meta() -> ProjectMeta:
    return ProjectMeta(
        id="edit-smoke", name="Edit Smoke", brand="脉动",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
        kpi="Vol", createdAt="2026-01-01T00:00:00+00:00",
    )


def _doc_artifact() -> ArtifactInstance:
    return ArtifactInstance(
        id="a-bu-summary", name="BU Summary", taskRef="1.7", type="document",
        stage="s1", format="doc", body={"blocks": [{"type": "h1", "text": "Old"}]},
        version=1,
    )


def _scope_artifact() -> ArtifactInstance:
    return ArtifactInstance(
        id="a-scope", name="Model Scope", taskRef="1.2", type="document",
        stage="s1", format="sheet", body={"sheets": []}, version=1,
    )


def test_router_registers_model_backed() -> None:
    assert set(MODEL_BINDINGS) == {
        "a-scope", "a-factor-tree", "a-quality-scorecard", "a-stat-tests"
    }


def test_apply_free_form_doc() -> None:
    st = initial_state(_meta())
    st.tick = 5
    art = _doc_artifact()
    st.artifacts.append(art)
    proposal = ArtifactEditProposal(
        artifactId="a-bu-summary", kind="free", format="doc",
        summary="x", body={"blocks": [{"type": "h1", "text": "New heading"}]},
    )
    updated = apply_proposal(st, proposal)
    assert updated.body == {"blocks": [{"type": "h1", "text": "New heading"}]}
    assert updated.version == 2, "version should bump"
    assert updated.edited_at_tick == 5, "editedAtTick should track the current tick"


def test_apply_free_form_markdown() -> None:
    st = initial_state(_meta())
    art = ArtifactInstance(
        id="a-final-report", name="Report", taskRef="5.3", type="report",
        stage="s5", format="markdown", content="# Old", version=3,
    )
    st.artifacts.append(art)
    proposal = ArtifactEditProposal(
        artifactId="a-final-report", kind="free", format="markdown",
        summary="x", content="# New report body",
    )
    updated = apply_proposal(st, proposal)
    assert updated.content == "# New report body"
    assert updated.version == 4


def test_apply_model_backed_profile_rerenders() -> None:
    st = initial_state(_meta())
    st.profile = ProjectProfile(timeGranularity="Month")
    st.artifacts.append(_scope_artifact())
    new_profile = ProjectProfile(timeGranularity="Week", projectIntro="ROI study")
    proposal = ArtifactEditProposal(
        artifactId="a-scope", kind="model", format="sheet",
        summary="x", model=new_profile.model_dump(by_alias=True),
    )
    updated = apply_proposal(st, proposal)
    # Backing model updated...
    assert st.profile.time_granularity == "Week"
    assert st.profile.project_intro == "ROI study"
    # ...and the deliverable re-rendered to reflect it.
    cells = [c for sheet in updated.body["sheets"] for row in sheet["rows"] for c in row]
    assert "Week" in cells, "re-rendered scope sheet should show the new granularity"
    assert updated.version == 2


def test_apply_model_backed_factor_tree_syncs_analysis() -> None:
    st = initial_state(_meta())
    st.factor_tree = FactorTree(rows=[])
    st.artifacts.append(ArtifactInstance(
        id="a-factor-tree", name="Factor Tree", taskRef="1.3", type="document",
        stage="s1", format="sheet", body={"sheets": []}, version=1,
    ))
    new_tree = FactorTree(rows=[
        FactorRow(id="fr-1", l1="生意", l2="营销", l3="促销", l4="单品折扣",
                  indicator="折扣率", status="accepted"),
    ])
    proposal = ArtifactEditProposal(
        artifactId="a-factor-tree", kind="model", format="sheet",
        summary="x", model=new_tree.model_dump(by_alias=True),
    )
    apply_proposal(st, proposal)
    assert st.analysis.get("factor_l4") == ["单品折扣"], st.analysis


def test_apply_rejects_unknown_artifact() -> None:
    st = initial_state(_meta())
    proposal = ArtifactEditProposal(
        artifactId="a-does-not-exist", kind="free", format="doc", summary="x",
        body={"blocks": []},
    )
    try:
        apply_proposal(st, proposal)
    except ArtifactEditError:
        pass
    else:
        raise AssertionError("expected ArtifactEditError for a missing artifact")


def test_apply_rejects_invalid_model_json() -> None:
    st = initial_state(_meta())
    st.profile = ProjectProfile()
    st.artifacts.append(_scope_artifact())
    bad = ArtifactEditProposal(
        artifactId="a-scope", kind="model", format="sheet", summary="x",
        model={"timeGranularity": "Decade"},  # not a valid TimeGranularity
    )
    try:
        apply_proposal(st, bad)
    except ArtifactEditError:
        pass
    else:
        raise AssertionError("expected ArtifactEditError for schema-invalid model")


if __name__ == "__main__":
    test_router_registers_model_backed()
    test_apply_free_form_doc()
    test_apply_free_form_markdown()
    test_apply_model_backed_profile_rerenders()
    test_apply_model_backed_factor_tree_syncs_analysis()
    test_apply_rejects_unknown_artifact()
    test_apply_rejects_invalid_model_json()
    print("all artifact-edit smoke tests passed")
