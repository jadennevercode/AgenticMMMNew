"""Autopilot + interactive runner over the DAG.

Drives tasks, generates grounded decision recommendations via the LLM, and (in
autopilot) auto-resolves decision gates with the recommended option. S1 upload
gates are NOT auto-satisfied — they block until the user uploads real files, so
Business Understanding is parsed only from genuine input (no reference fallback).
"""
from __future__ import annotations

from typing import Callable, Optional

from app.agents.common import agent_system, artifact_text, llm_recommendation
from app.domain import blueprint as bp
from app.orchestrator.engine import Engine, _default_choice, _mapping_complete
from app.store.files import get_files
from app.store.state import ProjectState


def _recommended_option(task_def: dict) -> str:
    opts = task_def.get("decision", {}).get("options", [])
    for o in opts:
        if o.get("recommended"):
            return o["id"]
    return opts[0]["id"] if opts else "approve"


async def ensure_recommendation(eng: Engine, st: ProjectState, decision_id: str) -> None:
    dr = st.decisions.get(decision_id)
    if dr is None or dr.recommendation:
        return
    task_def = next((t for t in bp.TASKS if t.get("decision", {}).get("id") == decision_id), None)
    if task_def is None:
        return
    ev_ids = [e.artifact_id for e in dr.evidence]
    ctx = artifact_text(st, ev_ids)
    findings = st.findings.get(task_def["id"], [])
    finding_text = "\n".join(f"- {f.text}" for f in findings)
    opts = "\n".join(f"- {o['id']}: {o['label']} ({o.get('consequence','')})"
                     for o in task_def["decision"].get("options", []))
    rec = await llm_recommendation(
        agent_system(task_def["agent"]),
        f"Decision: {dr.title}\nQuestion: {dr.question}\nOptions:\n{opts}\n\n"
        f"Findings:\n{finding_text}\n\nEvidence:\n{ctx}\n\n"
        "Recommend which option to take and why, grounded in the evidence above.",
    )
    if rec:
        dr.recommendation = rec


async def run_until_blocked(eng: Engine, st: ProjectState, *, autopilot: bool, max_steps: int = 200,
                            save: Optional[Callable[[], None]] = None) -> dict:
    """Advance the workflow. In autopilot, resolve human gates automatically.
    Returns a small status dict."""
    steps = 0
    while steps < max_steps:
        steps += 1
        # 1) generate recommendations for any open decision lacking one
        open_decisions = [d for d in st.decisions.values() if d.status == "open"]
        for d in open_decisions:
            await ensure_recommendation(eng, st, d.id)

        if autopilot:
            # 2) auto-submit open assignments. Upload gates that require real files
            #    (S1: SOW / materials / minutes) are NOT auto-satisfied — they stay
            #    blocked until the user actually uploads, so S1 is parsed only from
            #    real input. Non-upload gates (and the S2 data gate) still proceed.
            acted = False
            for t in bp.TASKS:
                if "assignment" in t and st.assignments[t["assignment"]["id"]].status == "open":
                    asg = t["assignment"]
                    if asg.get("requiresUpload") and not get_files().has_category(
                            st.project_id, asg.get("category")):
                        # The 2.1 data gate also clears on a resolved Data-Engine
                        # mapping (no raw files needed) — let submit_assignment judge it.
                        if not (asg.get("requiresMapping") and _mapping_complete(st)):
                            continue  # blocked: needs a real upload
                    # Source-choice gates auto-pick the recommended option (template),
                    # so autopilot never depends on an uploaded-own-tree file.
                    auto_choice = _default_choice(asg) if asg.get("choiceOptions") else None
                    if await eng.submit_assignment(st, t["assignment"]["id"], note="auto",
                                                   choice=auto_choice):
                        acted = True
            # 3) auto-resolve open decisions with the recommended option
            for t in bp.TASKS:
                if "decision" in t and st.decisions[t["decision"]["id"]].status == "open":
                    eng.resolve_decision(st, t["decision"]["id"], _recommended_option(t),
                                         note="auto: recommended")
                    acted = True
            if acted:
                if save:
                    save()
                continue

        # 4) run the next ready task
        task = eng.next_actionable(st)
        if task is None:
            break
        await eng.run_task(st, task)
        if save:
            save()

    done = sum(1 for r in st.tasks.values() if r.status == "done")
    waiting = [t.id for t in st.tasks.values() if t.status == "awaiting_human"]
    return {"steps": steps, "tasks_done": done, "tasks_total": len(st.tasks),
            "awaiting_human": waiting, "complete": done == len(st.tasks)}
