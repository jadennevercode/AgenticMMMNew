"""DAG execution engine.

Drives the 27-task workflow over a ProjectState. Each producing task has a
handler (app/agents) that does REAL work — deterministic computation (M) or an
LLM call grounded in real artifacts (A/C). Human tasks (H) are upload/export
assignments or decision gates. S1 upload gates require real files in the
Project Folder before they submit (no reference fallback); decision gates are
auto-resolved in autopilot or resolved via the API interactively.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from app.domain import blueprint as bp
from app.domain.models import (
    ArtifactInstance,
    EvidenceRef,
    Insight,
    LedgerEntry,
    Proposal,
    SimEvent,
    TaskFinding,
)
from app.store.state import ProjectState

# Handler signature: async (engine, state, task_def) -> None
Handler = Callable[["Engine", ProjectState, dict], Awaitable[None]]

# Decision-effect signature: (state, option_id) -> None. Runs the moment a gate
# is answered, so a verdict that later steps depend on becomes durable state
# instead of something re-derived from whatever the last run left behind.
DecisionEffect = Callable[[ProjectState, str], None]


def _default_choice(asg: dict) -> str:
    """The recommended (else first) option id of a source-choice assignment."""
    opts = asg.get("choiceOptions") or []
    for o in opts:
        if o.get("recommended"):
            return str(o.get("id", ""))
    return str(opts[0].get("id", "")) if opts else ""


def _mapping_complete(st: ProjectState) -> bool:
    """Every active factor row is mapped to a published asset or ignored."""
    try:
        from app.dataeng.mapping import mapping_complete
        return mapping_complete(st)
    except Exception:  # noqa: BLE001 — never let a mapping error hard-block the engine
        return False


def data_intake_ready(st: ProjectState, asg: dict) -> bool:
    """The 2.1 data gate. Clears when the FactorTree↔DataAssets mapping is fully
    resolved (Data-Engine path, ``requiresMapping``) OR the legacy per-L3 manifest
    validates (slot-upload path, ``requiresManifest``). A gate with only one flag
    is judged only by that flag."""
    ready = False
    if asg.get("requiresMapping") and _mapping_complete(st):
        ready = True
    if asg.get("requiresManifest") and not ready:
        try:
            from app.agents.data_request import manifest_satisfied
            ready = manifest_satisfied(st)
        except Exception:  # noqa: BLE001
            ready = True
    return ready




class Engine:
    def __init__(self) -> None:
        self.handlers: dict[str, Handler] = {}
        self.decision_effects: dict[str, DecisionEffect] = {}

    def register(self, task_id: str, handler: Handler) -> None:
        self.handlers[task_id] = handler

    def register_decision(self, decision_id: str, effect: DecisionEffect) -> None:
        """Attach an effect that runs when this gate is answered."""
        self.decision_effects[decision_id] = effect

    # ── event / artifact helpers ─────────────────────────
    def emit(self, st: ProjectState, agent: str, etype: str, message: str,
             task_id: Optional[str] = None) -> None:
        st.event_seq += 1
        st.events.insert(0, SimEvent(
            id=st.event_seq, tick=st.tick, agent=agent, task_id=task_id,
            type=etype, message=message,
        ))
        del st.events[400:]

    def produce(self, st: ProjectState, artifact_id: str, *, body: Optional[dict] = None,
                content: str = "", state: str = "confirmed", agent: str = "control") -> ArtifactInstance:
        meta = bp.ARTIFACT_MAP.get(artifact_id)
        if meta is None:
            raise ValueError(f"unknown artifact {artifact_id}")
        existing = st.artifact(artifact_id)
        if existing is not None:
            existing.body = body if body is not None else existing.body
            existing.content = content or existing.content
            existing.format = meta["format"]  # blueprint is source of truth (e.g. slides→review)
            existing.version += 1
            existing.state = state
            existing.produced_at_tick = st.tick
            inst = existing
        else:
            inst = ArtifactInstance(
                id=artifact_id, name=meta["name"], taskRef=meta["task_ref"],
                type=meta["type"], stage=meta["stage"], lineage=meta.get("lineage", []),
                format=meta["format"], body=body, content=content,
                exportable=meta.get("exportable"), internal=meta.get("internal"),
                version=1, state=state, producedByAgent=agent, producedAtTick=st.tick,
            )
            st.artifacts.append(inst)
        self.emit(st, agent, "artifact", f"{meta['name']} updated", meta["task_ref"])
        return inst

    def add_findings(self, st: ProjectState, task_id: str, findings: list[TaskFinding]) -> None:
        st.findings.setdefault(task_id, [])
        st.findings[task_id] = findings
        for f in findings:
            if f.tone == "flag":
                agent = bp.TASK_MAP[task_id]["agent"]
                self.emit(st, agent, "finding", f.text[:160], task_id)

    def add_proposal(self, st: ProjectState, prop: Proposal) -> None:
        if not any(p.id == prop.id for p in st.proposals):
            st.proposals.append(prop)
            self.emit(st, prop.source_agent, "suggestion", prop.title, prop.after_task)

    def add_insight(self, st: ProjectState, ins: Insight) -> None:
        if not any(i.id == ins.id for i in st.insights):
            ins.surfaced_at_tick = st.tick
            st.insights.append(ins)
            self.emit(st, bp.TASK_MAP.get(ins.after_task, {}).get("agent", "control"),
                      "finding", ins.title, ins.after_task)

    def add_ledger(self, st: ProjectState, entry: LedgerEntry) -> None:
        if not any(e.id == entry.id for e in st.ledger):
            st.ledger.append(entry)

    def set_analysis(self, st: ProjectState, key: str, value) -> None:
        st.analysis[key] = value

    # ── DAG control ──────────────────────────────────────
    def _deps_done(self, st: ProjectState, task_def: dict) -> bool:
        return all(st.tasks[d].status == "done" for d in task_def.get("depends_on", []))

    def _promote_ready(self, st: ProjectState) -> None:
        for t in bp.TASKS:
            rt = st.tasks[t["id"]]
            if rt.status == "pending" and self._deps_done(st, t):
                rt.status = "ready"

    def next_actionable(self, st: ProjectState) -> Optional[dict]:
        self._promote_ready(st)
        for t in bp.TASKS:
            if st.tasks[t["id"]].status == "ready":
                return t
        return None

    async def run_task(self, st: ProjectState, task_def: dict) -> None:
        """Execute one ready task's work up to its human gate (if any)."""
        tid = task_def["id"]
        rt = st.tasks[tid]
        rt.status = "running"
        rt.progress = 10.0
        rt.started_tick = st.tick
        st.tick += 1
        self.emit(st, task_def["agent"], "task_start", f"{task_def['name']} started", tid)

        handler = self.handlers.get(tid)
        if handler is not None:
            await handler(self, st, task_def)

        rt.progress = 100.0
        if "assignment" in task_def:
            aid = task_def["assignment"]["id"]
            st.assignments[aid].status = "open"
            rt.status = "awaiting_human"
        elif "decision" in task_def:
            did = task_def["decision"]["id"]
            st.decisions[did].status = "open"
            st.decisions[did].opened_at_tick = st.tick
            rt.status = "awaiting_human"
            self.emit(st, task_def["agent"], "decision_open", st.decisions[did].title, tid)
        else:
            self._finish(st, task_def)

    def _finish(self, st: ProjectState, task_def: dict) -> None:
        rt = st.tasks[task_def["id"]]
        rt.status = "done"
        rt.progress = 100.0
        rt.finished_tick = st.tick
        rt.runs += 1
        self.emit(st, task_def["agent"], "task_done", f"{task_def['name']} done", task_def["id"])
        self._promote_ready(st)

    # ── human actions ────────────────────────────────────
    async def submit_assignment(self, st: ProjectState, assignment_id: str, note: str = "",
                                choice: Optional[str] = None) -> bool:
        """Submit a human assignment. Returns False (leaving the gate blocked) when
        the assignment requires a real upload but its Project-Folder category is
        empty — S1 deliverables have no reference fallback."""
        for t in bp.TASKS:
            if t.get("assignment", {}).get("id") == assignment_id:
                asg = t["assignment"]
                from app.store.files import get_files
                # Data Engine: a resolved FactorTree↔DataAssets mapping (or published
                # indicators) satisfies the S2 data gate (2.1) in lieu of per-L3 slot
                # uploads. Additive — projects without indicators keep the original
                # upload/manifest flow unchanged.
                indicators_provide_data = bool(getattr(st, "indicators", None)) or _mapping_complete(st)
                if asg.get("requiresUpload"):
                    category = asg.get("category")
                    has_files = bool(category) and get_files().has_category(st.project_id, category)
                    if not has_files and not (category == "data" and indicators_provide_data):
                        return False
                # Optional source-choice gate (e.g. 1.1a factor-tree origin). Persist the
                # pick; the upload-option additionally requires a real file in its category.
                if asg.get("choiceOptions"):
                    ar0 = st.assignments[assignment_id]
                    picked = choice or ar0.chosen_source or _default_choice(asg)
                    ar0.chosen_source = picked
                    if assignment_id == "in-1.1a":
                        st.factor_tree_source = "upload" if picked == "upload" else "template"
                    up_cat = asg.get("choiceUploadCategory")
                    if picked == "upload" and up_cat and not get_files().has_category(st.project_id, up_cat):
                        return False
                # 2.1 data gate: clears when the FactorTree↔DataAssets mapping is fully
                # resolved (every indicator mapped or ignored) OR the legacy per-L3
                # manifest validates. Slot-upload projects keep using the manifest.
                if asg.get("requiresMapping") or asg.get("requiresManifest"):
                    if not data_intake_ready(st, asg):
                        return False
                ar = st.assignments[assignment_id]
                ar.status = "submitted"
                ar.submitted_at_tick = st.tick
                ar.note = note
                # Re-run the producing handler so the 'provided' artifact reflects
                # the files that are now actually in the Project Folder.
                handler = self.handlers.get(t["id"])
                if handler is not None:
                    await handler(self, st, t)
                self._finish(st, t)
                return True
        return False

    def resolve_decision(self, st: ProjectState, decision_id: str, option_id: str, note: str = "") -> None:
        for t in bp.TASKS:
            if t.get("decision", {}).get("id") == decision_id:
                dr = st.decisions[decision_id]
                dr.status = "resolved"
                dr.resolution = {"optionId": option_id, "note": note, "decidedAtTick": st.tick}
                effect = self.decision_effects.get(decision_id)
                if effect is not None:
                    effect(st, option_id)
                self.emit(st, t["agent"], "decision_resolved",
                          f"{dr.title}: {option_id}", t["id"])
                rework_opt = t["decision"].get("rework_option_id")
                rework_task = t["decision"].get("rework_task_id")
                if rework_opt and option_id == rework_opt and rework_task:
                    self._rework(st, rework_task)
                else:
                    self._finish(st, t)
                return

    def choose_ai_option(self, st: ProjectState, set_id: str, option_id: str) -> None:
        if set_id in st.ai_choices:
            st.ai_choices[set_id].chosen_id = option_id

    def resolve_proposal(self, st: ProjectState, proposal_id: str, accept: bool) -> None:
        for p in st.proposals:
            if p.id == proposal_id:
                p.status = "accepted" if accept else "dismissed"
                p.decided_at_tick = st.tick
                if accept:
                    target = st.artifact(p.target_artifact_id)
                    if target is not None:
                        target.version += 1
                        target.edited_at_tick = st.tick
                    self.add_ledger(st, LedgerEntry(
                        id=f"led-{p.id}", tick=st.tick, kind="proposal-accepted",
                        summary=p.title, detail=p.summary, source=p.source_agent,
                    ))
                return

    def resolve_insight(self, st: ProjectState, insight_id: str, actioned: bool) -> None:
        for i in st.insights:
            if i.id == insight_id:
                i.status = "actioned" if actioned else "dismissed"
                return

    def _rework(self, st: ProjectState, task_id: str) -> None:
        affected = {task_id} | bp.downstream_of(task_id)
        for tid in affected:
            rt = st.tasks[tid]
            rt.status = "pending"
            rt.progress = 0.0
            rt.started_tick = None
            rt.finished_tick = None
            tdef = bp.TASK_MAP[tid]
            if "decision" in tdef:
                st.decisions[tdef["decision"]["id"]].status = "idle"
            if "assignment" in tdef:
                st.assignments[tdef["assignment"]["id"]].status = "idle"
        self.emit(st, "control", "info", f"Rework triggered from {task_id}", task_id)
        self._promote_ready(st)
