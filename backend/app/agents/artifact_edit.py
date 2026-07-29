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
    OlsRangeScorecard,
    ProjectProfile,
    QualityScorecard,
    StatScorecard,
)
from app.llm.volcano import get_llm
from app.store.state import ProjectState


class ArtifactEditError(Exception):
    """A chat edit could not be drafted or applied (surfaced to the user)."""


# How many times `apply_ols_config` may re-fit to settle the 2.5 verdicts against
# the model they describe. Two passes is what convergence takes in practice (the
# fit, then the fit without whatever the first pass rejected); the rest is a
# backstop against a pathological oscillation, not an expected path.
_SETTLE_REFITS = 4


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


def _refuse_if_locked(st: ProjectState, what: str) -> None:
    """Upstream verdicts are frozen once 2.5's selection is signed off.

    Everything from 2.5 on was fitted against the verdicts as they stood then, so
    an edit here would leave the model claiming a filtering chain that no longer
    describes it — and nothing on screen would say the two had diverged.
    """
    from app.agents.ledger import downstream_locked

    if downstream_locked(st):
        raise ArtifactEditError(
            f"{what} is locked: the OLS selection (d-2.5) is already signed off, and "
            "2.5 / 2.6 were built on these verdicts. Re-open d-2.5 first, then edit "
            "and re-run — changing it here would silently invalidate them.")


def apply_quality_scorecard(st: ProjectState, model: QualityScorecard) -> None:
    from app.agents.data import accepted_metric_labels, quality_sheet

    _refuse_if_locked(st, "The 2.2 data-quality scorecard")
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

    _refuse_if_locked(st, "The 2.4 statistical scorecard")
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

    Iterating is the point of this surface — but only until `d-2.5` is signed off.
    After that, 2.6 and the master data are built on this exact selection, and
    d-2.5 has pinned its own drops onto its resolution; re-fitting underneath them
    would leave every one of those claims describing a model that no longer exists.
    """
    _refuse_if_locked(st, "The 2.5 OLS setup")

    from app.agents.ols_review import build_ols_review
    from app.agents.ols_scorecard import build_scorecard

    st.ols_config = model
    art = st.artifact("a-ols-test")
    if art is None:
        return
    fit = bool(model.y)  # no response confirmed yet → stay in the setup state

    def _render() -> tuple[dict, dict, list]:
        try:
            return build_ols_review(st, fit=fit)
        except Exception as e:  # noqa: BLE001 — a bad setup must not 500 the editor
            body, prefit, flagged = build_ols_review(st, fit=False)
            body["note"] = f"The fit could not run with this setup: {e}"
            return body, prefit, flagged

    body, prefit, flagged = _render()
    if fit:
        # Refresh the 2.5d review sheet against the new fit, then settle.
        #
        # One pass is not enough, and the reason is structural: the fit is run on
        # the selection as it stood, and the sheet is derived *from that fit* — so
        # a newly out-of-range factor is rejected only after the model that
        # produced it was already rendered. The artifact would then show a model
        # containing variables its own verdicts reject, which is precisely the
        # "the deliverable describes a model nobody fitted" failure this work is
        # about. Re-fit until the reject set stops moving.
        #
        # The merge keeps every verdict the human has already made
        # (`ols_scorecard.build_scorecard`), so this can never revert a reviewer's
        # call — only settle the rows the AI still owns. It converges in one extra
        # pass in practice; the cap is a backstop, not the expected path.
        from app.agents.ols_scorecard import reject_pairs_by_object

        # `used` is the reject set the current `body` was fitted under. Rebuild the
        # sheet from it; if that yields the same set, the two agree and we stop.
        used = reject_pairs_by_object(st)
        for _ in range(_SETTLE_REFITS):
            st.ols_scorecard = build_scorecard(st, body)
            derived = reject_pairs_by_object(st)
            if derived == used:
                break
            used = derived
            body, prefit, flagged = _render()
        else:
            # Cap reached (oscillating verdicts). Keep the sheet describing the
            # model actually rendered rather than leaving the two disagreeing.
            st.ols_scorecard = build_scorecard(st, body)

    art.body = body
    art.version += 1
    art.edited_at_tick = st.tick
    if fit:
        st.analysis["prefit"] = prefit
        st.analysis["ols_flagged"] = flagged
        st.analysis["selection_warnings"] = [
            f"{f['l4']} · {f['indicator']}" for f in flagged][:20]


def apply_ols_scorecard(st: ProjectState, model: OlsRangeScorecard) -> None:
    """Persist the 2.5d accept/reject verdicts and re-fit.

    Unlike 2.2 and 2.4 — where a disposition only changes what a later layer
    inherits — a rejection here removes the variable from a model that has already
    been fitted, so the remaining coefficients are no longer the ones on screen.
    Re-fitting is the honest response, and it is what the reviewer is asking for
    when they reject a variable.

    The re-fit re-derives the sheet, which is where the merge earns its keep: the
    rejected rows vanish from the new tree (they were excluded) and every row the
    human ruled on must come back unchanged.
    """
    _refuse_if_locked(st, "The 2.5 range verdicts")

    st.ols_scorecard = model
    cfg = getattr(st, "ols_config", None)
    if cfg is None:
        return
    # Route through apply_ols_config so there is exactly one re-fit path; it
    # rebuilds the sheet from the new body, merging over what we just stored.
    apply_ols_config(st, cfg)


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
