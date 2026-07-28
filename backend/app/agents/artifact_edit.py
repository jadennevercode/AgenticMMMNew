"""Chat-driven artifact editing — draft a proposed revision, then apply it.

The flow is two-step (preview-then-confirm), mirrored by two endpoints in
`main.py`:

  1. `draft_edit(st, artifact, instruction)` asks the LLM for a *proposed* new
     version of the artifact and returns an `ArtifactEditProposal` WITHOUT
     mutating any state.
  2. `apply_proposal(st, proposal)` persists the confirmed change (version bump,
     editedAtTick) — re-rendering through the domain model for the four
     model-backed artifacts so structured state stays consistent.

Two classes of artifact:

  • **model-backed** (`a-scope`, `a-factor-tree`, `a-quality-scorecard`,
    `a-stat-tests`) — the artifact body is *rendered from* a Pydantic domain
    model. We ask the LLM to revise the model JSON (validated against the
    schema), then re-render via the same helper the manual editors use, so the
    structured state (st.profile / factor_tree / ...) and the deliverable never
    diverge.
  • **free-form** (everything else) — sheet/slides/doc bodies, `review` dicts,
    or markdown `content` are rewritten directly.

Per the project convention the LLM is told the artifact's own computed numbers
are authoritative grounding; unlike narrative generation, chat edits MAY change
figures because the user explicitly asked for a content edit.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from pydantic import ValidationError

from app.agents.common import (
    agent_system,
    normalize_doc,
    normalize_sheet,
    normalize_slides,
)
from app.domain.models import (
    ArtifactEditProposal,
    ArtifactInstance,
    FactorTree,
    OlsConfig,
    ProjectProfile,
    QualityScorecard,
    StatScorecard,
)
from app.llm.volcano import get_llm
from app.store.state import ProjectState


class ArtifactEditError(Exception):
    """A chat edit could not be drafted or applied (surfaced to the user)."""


# ── model-backed re-render helpers (shared with the PUT routes in main.py) ─
def apply_profile(st: ProjectState, model: ProjectProfile) -> None:
    from app.agents.business import _profile_sheet

    st.profile = model
    art = st.artifact("a-scope")
    if art is not None:
        art.body = _profile_sheet(model, st.meta)
        art.version += 1
        art.edited_at_tick = st.tick


def apply_factor_tree(st: ProjectState, model: FactorTree) -> None:
    from app.agents.business import _factor_tree_sheet

    st.factor_tree = model
    art = st.artifact("a-factor-tree")
    if art is not None:
        art.body = _factor_tree_sheet(model)
        art.version += 1
        art.edited_at_tick = st.tick
    # Keep the analysis blackboard's accepted-L4 list in sync for downstream tasks.
    active = [r for r in model.rows if r.status in ("baseline", "accepted")]
    st.analysis["factor_l4"] = sorted({r.l4 for r in active if r.l4})


def apply_quality_scorecard(st: ProjectState, model: QualityScorecard) -> None:
    from app.agents.data import accepted_metric_labels, quality_sheet

    st.quality_scorecard = model
    art = st.artifact("a-quality-scorecard")
    if art is not None:
        art.body = quality_sheet(model)
        art.version += 1
        art.edited_at_tick = st.tick
    kept = accepted_metric_labels(model)
    quality = dict(st.analysis.get("quality") or {})
    quality["accepted"] = len(kept)
    quality["accepted_metrics"] = kept
    st.analysis["quality"] = quality


def apply_stat_scorecard(st: ProjectState, model: StatScorecard) -> None:
    from app.agents.stat_scoring import accepted_stat_labels, stat_sheet

    st.stat_scorecard = model
    art = st.artifact("a-stat-tests")
    if art is not None:
        art.body = stat_sheet(model)
        art.version += 1
        art.edited_at_tick = st.tick
    # Keep the 2.4 screening blackboard in sync with the human's kept indicators.
    kept = accepted_stat_labels(model)
    screening = dict(st.analysis.get("screening") or {})
    screening["kept"] = kept
    screening["drop"] = sum(1 for r in model.rows if r.disposition == "drop")
    st.analysis["screening"] = screening


def apply_ols_config(st: ProjectState, model: OlsConfig) -> None:
    """Persist the 2.5 setup and re-fit immediately.

    The OLS is cheap and the human is iterating (change Y, untick a collinear
    variable, adjust seasonality), so the fit runs synchronously here rather than
    through the run loop — there is no single-task rerun, and `d-2.5`'s rework
    resets 2.3 and everything downstream, which is far too destructive for a
    configuration tweak. Before Y is confirmed there is nothing to fit, so the
    config is just persisted.
    """
    from app.agents.ols_review import build_ols_review

    st.ols_config = model
    art = st.artifact("a-ols-test")
    if art is None:
        return
    fit = bool(model.y)  # no response confirmed yet → stay in the setup state
    try:
        body, prefit, flagged = build_ols_review(st, fit=fit)
    except Exception as e:  # noqa: BLE001 — a bad setup must not 500 the editor
        body, prefit, flagged = build_ols_review(st, fit=False)
        body["note"] = f"The fit could not run with this setup: {e}"
    art.body = body
    art.version += 1
    art.edited_at_tick = st.tick
    if fit:
        st.analysis["prefit"] = prefit
        st.analysis["ols_flagged"] = flagged
        st.analysis["selection_warnings"] = [
            f"{f['l4']} · {f['indicator']}" for f in flagged][:20]


# Registry: artifact id -> how to read / revise / apply its backing model.
class _ModelBinding:
    def __init__(
        self,
        model_cls: type,
        current: Callable[[ProjectState], Optional[object]],
        render: Callable[[ProjectState, object], dict],
        apply: Callable[[ProjectState, object], None],
    ) -> None:
        self.model_cls = model_cls
        self.current = current
        self.render = render
        self.apply = apply


def _render_profile(st: ProjectState, m: ProjectProfile) -> dict:
    from app.agents.business import _profile_sheet

    return _profile_sheet(m, st.meta)


def _render_factor_tree(st: ProjectState, m: FactorTree) -> dict:
    from app.agents.business import _factor_tree_sheet

    return _factor_tree_sheet(m)


def _render_quality(st: ProjectState, m: QualityScorecard) -> dict:
    from app.agents.data import quality_sheet

    return quality_sheet(m)


def _render_stat_scorecard(st: ProjectState, m: StatScorecard) -> dict:
    from app.agents.stat_scoring import stat_sheet

    return stat_sheet(m)


MODEL_BINDINGS: dict[str, _ModelBinding] = {
    "a-scope": _ModelBinding(
        ProjectProfile, lambda st: st.profile, _render_profile, apply_profile
    ),
    "a-factor-tree": _ModelBinding(
        FactorTree, lambda st: st.factor_tree, _render_factor_tree, apply_factor_tree
    ),
    "a-quality-scorecard": _ModelBinding(
        QualityScorecard, lambda st: st.quality_scorecard, _render_quality, apply_quality_scorecard
    ),
    "a-stat-tests": _ModelBinding(
        StatScorecard, lambda st: st.stat_scorecard, _render_stat_scorecard, apply_stat_scorecard
    ),
}

# Free-form structured formats whose body is rewritten directly.
_NORMALIZERS: dict[str, Callable[[object], dict]] = {
    "sheet": normalize_sheet,
    "slides": normalize_slides,
    "doc": normalize_doc,
}
_SCHEMA_HINTS = {
    "sheet": 'JSON shape: {"sheets":[{"name":str,"columns":[str],"rows":[[str,...]]}]}',
    "slides": 'JSON shape: {"slides":[{"title":str,"bullets":[str]}]}',
    "doc": 'JSON shape: {"blocks":[{"type":"h1|h2|p|li","text":str}]}',
}


def _grounding(st: ProjectState) -> str:
    """The authoritative computed numbers, so edits stay anchored to real results."""
    picked = st.analysis.get("picked", {}) if isinstance(st.analysis, dict) else {}
    parts = []
    for o, c in picked.items():
        try:
            parts.append(
                f"{o}: R²={c.get('r2'):.3f}, MAPE={c.get('mape'):.1f}%, "
                f"baseline={c.get('baseline_pct'):.1f}%"
            )
        except (TypeError, ValueError):
            continue
    return "; ".join(parts) or "no computed model results yet"


def _summarize(instruction: str) -> str:
    short = instruction.strip().replace("\n", " ")
    if len(short) > 80:
        short = short[:77] + "…"
    return f"Proposed an edit for: “{short}”. Review the diff, then Apply."


async def _draft_model_backed(
    st: ProjectState, artifact: ArtifactInstance, binding: _ModelBinding, instruction: str
) -> ArtifactEditProposal:
    current = binding.current(st)
    if current is None:
        raise ArtifactEditError(
            "This deliverable isn’t produced yet — run its steps first, then edit it here."
        )
    current_json = current.model_dump(by_alias=True)
    schema_json = json.dumps(binding.model_cls.model_json_schema(), ensure_ascii=False)
    system = agent_system("control")
    user = (
        f"You are revising the structured data behind the “{artifact.name}” deliverable.\n"
        f"GROUNDING (authoritative computed numbers): {_grounding(st)}\n\n"
        f"CURRENT VALUE (JSON):\n{json.dumps(current_json, ensure_ascii=False)}\n\n"
        f"JSON SCHEMA the value must conform to:\n{schema_json}\n\n"
        f"USER EDIT REQUEST: {instruction}\n\n"
        "Return the FULL updated value as a single JSON object conforming to the schema. "
        "Change only what the request implies; preserve every other field exactly. "
        "Keep all ids stable."
    )
    obj = await get_llm().json(system=system, user=user)
    if not isinstance(obj, dict):
        raise ArtifactEditError("The AI did not return a valid object for this deliverable.")
    try:
        model = binding.model_cls.model_validate(obj)
    except ValidationError as e:
        raise ArtifactEditError(f"The proposed change did not fit the schema: {e.errors()[:2]}")
    preview_body = binding.render(st, model)
    return ArtifactEditProposal(
        artifactId=artifact.id,
        kind="model",
        format=artifact.format,
        summary=_summarize(instruction),
        body=preview_body,
        model=model.model_dump(by_alias=True),
    )


async def _draft_free_form(
    st: ProjectState, artifact: ArtifactInstance, instruction: str
) -> ArtifactEditProposal:
    system = agent_system(artifact.produced_by_agent or "control")
    fmt = artifact.format
    if fmt == "markdown":
        current = artifact.content or ""
        text = await get_llm().chat(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        f"You are revising the document “{artifact.name}” (Markdown).\n"
                        f"GROUNDING (authoritative computed numbers): {_grounding(st)}\n\n"
                        f"CURRENT DOCUMENT:\n{current}\n\n"
                        f"USER EDIT REQUEST: {instruction}\n\n"
                        "Return the FULL revised document in Markdown. Change only what the "
                        "request implies; preserve the rest. No code fences, no commentary."
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        return ArtifactEditProposal(
            artifactId=artifact.id, kind="free", format=fmt,
            summary=_summarize(instruction), content=text.strip(),
        )

    current_body = artifact.body or {}
    normalizer = _NORMALIZERS.get(fmt)
    hint = _SCHEMA_HINTS.get(fmt, "")
    user = (
        f"You are revising the “{artifact.name}” deliverable (format: {fmt}).\n"
        f"GROUNDING (authoritative computed numbers): {_grounding(st)}\n\n"
        f"CURRENT BODY (JSON):\n{json.dumps(current_body, ensure_ascii=False)[:8000]}\n\n"
        f"USER EDIT REQUEST: {instruction}\n\n"
        f"Return the FULL updated body as JSON. {hint} "
        "Change only what the request implies; preserve the rest."
    )
    obj = await get_llm().json(system=system, user=user)
    try:
        body = normalizer(obj) if normalizer else _coerce_dict(obj)
    except (ValueError, KeyError, TypeError) as e:
        raise ArtifactEditError(f"The AI reply could not be parsed for this format: {e}")
    return ArtifactEditProposal(
        artifactId=artifact.id, kind="free", format=fmt,
        summary=_summarize(instruction), body=body,
    )


def _coerce_dict(obj: object) -> dict:
    """Fallback for `review` (and any other dict-bodied) formats."""
    if isinstance(obj, dict):
        return obj
    raise ValueError("expected a JSON object body")


async def draft_edit(
    st: ProjectState, artifact: ArtifactInstance, instruction: str
) -> ArtifactEditProposal:
    """Produce a proposed revision of `artifact` from a natural-language request.

    Does NOT mutate `st`. Raises `ArtifactEditError` with a user-facing message.
    """
    if not instruction.strip():
        raise ArtifactEditError("Please describe the change you want.")
    binding = MODEL_BINDINGS.get(artifact.id)
    if binding is not None:
        return await _draft_model_backed(st, artifact, binding, instruction)
    return await _draft_free_form(st, artifact, instruction)


def apply_proposal(st: ProjectState, proposal: ArtifactEditProposal) -> ArtifactInstance:
    """Persist a confirmed proposal onto the artifact. Raises `ArtifactEditError`."""
    artifact = st.artifact(proposal.artifact_id)
    if artifact is None:
        raise ArtifactEditError("That deliverable no longer exists.")

    if proposal.kind == "model":
        binding = MODEL_BINDINGS.get(artifact.id)
        if binding is None or proposal.model is None:
            raise ArtifactEditError("This deliverable can’t be applied as a model edit.")
        try:
            model = binding.model_cls.model_validate(proposal.model)
        except ValidationError as e:
            raise ArtifactEditError(f"The change no longer fits the schema: {e.errors()[:2]}")
        binding.apply(st, model)
        return st.artifact(proposal.artifact_id)  # type: ignore[return-value]

    # free-form: write body or content directly.
    if proposal.format == "markdown":
        artifact.content = proposal.content
    else:
        if not proposal.body:
            raise ArtifactEditError("The proposal has no content to apply.")
        artifact.body = proposal.body
    artifact.version += 1
    artifact.edited_at_tick = st.tick
    return artifact
