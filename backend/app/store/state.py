"""Project state + multi-project store.

Each project is an isolated `ProjectState` (the blackboard the engine mutates),
persisted to its own JSON file under `data/projects/{id}.json`. A lightweight
registry index (`data/projects/_index.json`) lists the `ProjectMeta` of every
project so the landing page can render the list without loading full states.

The real MMM engine + ingest loaders are Danone-specific, so every project
currently runs against the same reference dataset — isolation here is at the
state / run-loop / persistence / metadata level (see CLAUDE.md).
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.domain import blueprint as bp
from app.domain.models import (
    AiOptionSet,
    AnomalyReview,
    ArtifactInstance,
    AssignmentRuntime,
    AssistantTurn,
    DataAsset,
    DecisionRuntime,
    FactorTree,
    Indicator,
    IndustryRef,
    Insight,
    LedgerEntry,
    MasterDataMap,
    OlsConfig,
    ProjectMeta,
    TargetColumn,
    ProjectProfile,
    Proposal,
    QualityScorecard,
    SimEvent,
    StatScorecard,
    TaskFinding,
    TaskRuntime,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# The original real case — seeded on first run / migrated from the legacy file.
def danone_meta() -> ProjectMeta:
    return ProjectMeta(
        id="danone-mizone",
        name="Danone Mizone · MMM POC 2026",
        brand="脉动 Mizone",
        industry=IndustryRef(l1="food-bev", l2="beverage", l3="sports-functional"),
        kpi="Sell-out Volume",
        createdAt=_now_iso(),
    )


class ProjectState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_id: str = "danone-mizone"
    meta: Optional[ProjectMeta] = None
    profile: Optional[ProjectProfile] = None
    # (Model config is now a single global config, not per-project — any legacy
    # `modelConfig` key in a saved project JSON is silently ignored on load.)
    factor_tree: Optional[FactorTree] = None
    # How the factor-tree baseline is sourced: "template" (industry template, the
    # default flow) or "upload" (the user's own uploaded factor tree, AI-supplemented).
    # Picked at the 1.1a gate; read by derive_factor_tree (1.21).
    factor_tree_source: str = Field(default="template", alias="factorTreeSource")
    quality_scorecard: Optional[QualityScorecard] = None  # S2 · editable per-metric dispositions
    stat_scorecard: Optional[StatScorecard] = None        # S2 · 2.4 editable per-indicator stat scores
    # S2 · 2.3a: one card per detected anomaly — the AI's causal hypothesis and
    # proposed handling, and the human's ruling. The accepted handling is what
    # reaches the fit (event dummy / response capping / caveat), resolved at fit
    # time by `ledger.model_selection`. Source of truth → survives heal_state.
    anomaly_review: Optional[AnomalyReview] = None
    # S2 · 2.5 OLS setup: AI-proposed Y/X/params, confirmed by the human through
    # the 2.5y/2.5x/2.5p Process steps. Source of truth for the fit; editing it
    # re-fits synchronously (apply_ols_config). Survives heal_state.
    # No alias, unlike the models inside it: ProjectState's own fields serialize
    # snake_case (it is a plain BaseModel), and an aliased field here emits a
    # camelCase key the frontend's snake_case reader silently misses.
    ols_config: Optional[OlsConfig] = None
    # 2.1 Data Processing: factor rows the user explicitly ignores in the
    # FactorTree↔DataAssets mapping (rowId → note). A row is resolved when it is
    # either mapped by a published indicator or listed here; the 2.1 gate blocks
    # while any active row is still unresolved. Not blueprint-derived → persists.
    factor_map_ignores: dict[str, str] = Field(default_factory=dict, alias="factorMapIgnores")
    # Data Engine: project-scoped data assets + master-data maps (not blueprint-derived,
    # so they persist across heal_state like artifacts).
    data_assets: list[DataAsset] = Field(default_factory=list, alias="dataAssets")
    master_data: list[MasterDataMap] = Field(default_factory=list, alias="masterData")
    # Data Engine: the target long-table schema (None → the default) and the
    # indicators registered when assets publish.
    target_schema: Optional[list[TargetColumn]] = Field(default=None, alias="targetSchema")
    indicators: list[Indicator] = Field(default_factory=list, alias="indicators")
    tick: int = 0
    event_seq: int = 0
    tasks: dict[str, TaskRuntime] = {}
    decisions: dict[str, DecisionRuntime] = {}
    assignments: dict[str, AssignmentRuntime] = {}
    ai_choices: dict[str, AiOptionSet] = {}
    artifacts: list[ArtifactInstance] = []
    proposals: list[Proposal] = []
    insights: list[Insight] = []
    events: list[SimEvent] = []
    ledger: list[LedgerEntry] = []
    assistant: list[AssistantTurn] = []
    # Per-artifact chat threads for the "ask the AI to change this document" box.
    artifact_chats: dict[str, list[AssistantTurn]] = Field(default_factory=dict, alias="artifactChats")
    findings: dict[str, list[TaskFinding]] = {}
    # Non-UI blackboard for real computed results passed between tasks.
    analysis: dict = {}

    def artifact(self, artifact_id: str) -> Optional[ArtifactInstance]:
        for a in self.artifacts:
            if a.id == artifact_id:
                return a
        return None

    def data_asset(self, asset_id: str) -> Optional[DataAsset]:
        for a in self.data_assets:
            if a.id == asset_id:
                return a
        return None


def initial_state(meta: ProjectMeta) -> ProjectState:
    st = ProjectState(project_id=meta.id, meta=meta)
    for t in bp.TASKS:
        st.tasks[t["id"]] = TaskRuntime(
            id=t["id"], name=t["name"], agent=t["agent"], stage=t["stage"],
            **{"class": t["klass"]},
            summary=t.get("summary", ""), how=t.get("how", ""),
            basis_note=t.get("basis_note"), work_note=t.get("work_note", ""),
            depends_on=t.get("depends_on", []), duration=t.get("duration", 2),
            produces=t.get("produces", []),
            has_decision="decision" in t, has_assignment="assignment" in t,
            has_ai_options="ai_options" in t,
            status="pending", progress=0.0, runs=0,
        )
        if "decision" in t:
            d = t["decision"]
            st.decisions[d["id"]] = DecisionRuntime(
                id=d["id"], kind=d["kind"], title=d["title"], question=d["question"],
                evidence=[{"artifactId": e["artifactId"], "note": e.get("note")} for e in d.get("evidence", [])],
                recommendation=d.get("recommendation", ""),
                options=d.get("options", []),
                rework_task_id=d.get("rework_task_id"), rework_option_id=d.get("rework_option_id"),
                status="idle",
            )
        if "assignment" in t:
            a = t["assignment"]
            st.assignments[a["id"]] = AssignmentRuntime(
                id=a["id"], kind=a["kind"], title=a["title"], prompt=a.get("prompt", ""),
                items=a.get("items", []), submit_label=a.get("submit_label", "Submit"),
                category=a.get("category"), requiresUpload=a.get("requiresUpload", False),
                choicePrompt=a.get("choicePrompt", ""), choiceOptions=a.get("choiceOptions", []),
                choiceUploadCategory=a.get("choiceUploadCategory"),
                status="idle",
            )
        if "ai_options" in t:
            ao = t["ai_options"]
            st.ai_choices[ao["id"]] = AiOptionSet(
                id=ao["id"], prompt=ao.get("prompt", ""), options=ao.get("options", []),
                chosen_id=None,
            )
    return st


def heal_state(st: ProjectState) -> ProjectState:
    """Reconcile a loaded state with the current blueprint: add any missing
    tasks/decisions/assignments/ai-choices, and prune ones the blueprint no
    longer defines (e.g. removed tasks/artifacts), so blueprint changes don't
    leave stale entries on saved projects."""
    template = initial_state(st.meta or danone_meta())
    pre_existing = set(st.tasks)
    for tid, rt in template.tasks.items():
        st.tasks.setdefault(tid, rt)
    # New ASR step 1.4b sits between 1.4a and 1.4. On a project that already
    # finished 1.4 before this step existed, mark the freshly back-filled 1.4b as
    # done so the completed run isn't re-blocked waiting for transcription.
    if ("1.4b" not in pre_existing and "1.4b" in st.tasks
            and st.tasks.get("1.4") is not None and st.tasks["1.4"].status == "done"):
        st.tasks["1.4b"].status = "done"
        st.tasks["1.4b"].progress = 100.0
    for did, dr in template.decisions.items():
        st.decisions.setdefault(did, dr)
    for aid, ar in template.assignments.items():
        existing = st.assignments.get(aid)
        if existing is None:
            st.assignments[aid] = ar
        else:
            # Refresh blueprint-derived fields (prompt, items, upload requirement)
            # while preserving the runtime status/note/submission on saved projects.
            existing.kind = ar.kind
            existing.title = ar.title
            existing.prompt = ar.prompt
            existing.items = ar.items
            existing.submit_label = ar.submit_label
            existing.category = ar.category
            existing.requires_upload = ar.requires_upload
            existing.choice_prompt = ar.choice_prompt
            existing.choice_options = ar.choice_options
            existing.choice_upload_category = ar.choice_upload_category
            # existing.chosen_source is runtime — preserved across heal.
    for sid, ao in template.ai_choices.items():
        st.ai_choices.setdefault(sid, ao)
    # Prune entries removed from the blueprint.
    st.tasks = {tid: rt for tid, rt in st.tasks.items() if tid in template.tasks}
    st.decisions = {did: dr for did, dr in st.decisions.items() if did in template.decisions}
    st.assignments = {aid: ar for aid, ar in st.assignments.items() if aid in template.assignments}
    st.ai_choices = {sid: ao for sid, ao in st.ai_choices.items() if sid in template.ai_choices}
    st.artifacts = [a for a in st.artifacts if a.id in bp.ARTIFACT_MAP]
    # Refresh artifact format from the blueprint; drop a body that no longer matches
    # the format (e.g. a legacy slides body on the now-'review' Data Review Deck).
    for a in st.artifacts:
        meta_fmt = bp.ARTIFACT_MAP[a.id]["format"]
        if a.format != meta_fmt:
            a.format = meta_fmt
            a.body = None
            a.state = "draft"
    st.findings = {tid: f for tid, f in st.findings.items() if tid in template.tasks}
    # Backfill the factor-tree Dimension column on saved projects: seed empty
    # dimensions from the profile's model scope, then re-render the artifact sheet
    # so the new column shows on already-persisted projects.
    if st.factor_tree is not None:
        if st.profile is not None:
            dim = ", ".join(d.name.strip() for d in st.profile.model_scope.dimensions if d.name.strip())
            if dim:
                for r in st.factor_tree.rows:
                    if not r.dimension:
                        r.dimension = dim
        from app.agents.business import _factor_tree_sheet
        art = next((a for a in st.artifacts if a.id == "a-factor-tree"), None)
        if art is not None and art.body is not None:
            art.body = _factor_tree_sheet(st.factor_tree)
    return st


def _slug(text: str) -> str:
    """ASCII slug from a (possibly Chinese) name; empty -> 'project'."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:32] or "project"


def project_summary(st: ProjectState) -> tuple[int, int]:
    """(tasks_done, tasks_total) for the registry list."""
    total = len(st.tasks)
    done = sum(1 for t in st.tasks.values() if t.status == "done")
    return done, total


class ProjectStore:
    """Multi-project JSON-file-backed store with per-process locking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._root: Path = get_settings().data_path / "projects"
        self._index_path: Path = self._root / "_index.json"
        self._legacy_path: Path = get_settings().data_path / "project_state.json"
        self._states: dict[str, ProjectState] = {}
        self._initialized = False

    # ── paths ────────────────────────────────────────────
    def _state_path(self, project_id: str) -> Path:
        return self._root / f"{project_id}.json"

    # ── index ────────────────────────────────────────────
    def _read_index(self) -> list[ProjectMeta]:
        if not self._index_path.exists():
            return []
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
            return [ProjectMeta.model_validate(m) for m in raw]
        except (json.JSONDecodeError, ValueError):
            return []

    def _write_index(self, metas: list[ProjectMeta]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps([m.model_dump(by_alias=True) for m in metas], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _upsert_index(self, meta: ProjectMeta) -> None:
        metas = [m for m in self._read_index() if m.id != meta.id]
        metas.append(meta)
        self._write_index(metas)

    # ── lifecycle / migration ────────────────────────────
    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        self._root.mkdir(parents=True, exist_ok=True)
        if not self._read_index():
            meta = danone_meta()
            # Migrate a legacy single-project file if present, else seed fresh.
            if self._legacy_path.exists():
                try:
                    raw = json.loads(self._legacy_path.read_text(encoding="utf-8"))
                    st = ProjectState.model_validate(raw)
                    st.project_id = meta.id
                    st.meta = meta
                    st = heal_state(st)
                except (json.JSONDecodeError, ValueError):
                    st = initial_state(meta)
            else:
                st = initial_state(meta)
            self._states[meta.id] = st
            self._write_state(st)
            self._upsert_index(meta)
        self._initialized = True

    def _write_state(self, st: ProjectState) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        self._state_path(st.project_id).write_text(
            st.model_dump_json(by_alias=True, indent=2), encoding="utf-8",
        )

    def _load_state(self, project_id: str) -> Optional[ProjectState]:
        path = self._state_path(project_id)
        if not path.exists():
            return None
        try:
            return heal_state(ProjectState.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, ValueError):
            return None

    # ── public API ───────────────────────────────────────
    def list_meta(self) -> list[ProjectMeta]:
        with self._lock:
            self._ensure_initialized()
            return self._read_index()

    def exists(self, project_id: str) -> bool:
        with self._lock:
            self._ensure_initialized()
            return self._state_path(project_id).exists() or project_id in self._states

    def get(self, project_id: str) -> Optional[ProjectState]:
        with self._lock:
            self._ensure_initialized()
            if project_id not in self._states:
                st = self._load_state(project_id)
                if st is None:
                    return None
                self._states[project_id] = st
            return self._states[project_id]

    def create(self, name: str, brand: str, industry: IndustryRef, kpi: str = "Sell-out Volume") -> ProjectMeta:
        with self._lock:
            self._ensure_initialized()
            existing = {m.id for m in self._read_index()}
            base = _slug(name)
            project_id = base if base not in existing else f"{base}-{uuid.uuid4().hex[:6]}"
            meta = ProjectMeta(
                id=project_id, name=name.strip(), brand=brand.strip(),
                industry=industry, kpi=kpi, createdAt=_now_iso(),
            )
            st = initial_state(meta)
            self._states[project_id] = st
            self._write_state(st)
            self._upsert_index(meta)
            return meta

    def save(self, project_id: str) -> None:
        with self._lock:
            st = self._states.get(project_id)
            if st is None:
                return
            self._write_state(st)
            if st.meta is not None:
                st.meta.updated_at = _now_iso()
                self._upsert_index(st.meta)

    def reset(self, project_id: str) -> Optional[ProjectState]:
        with self._lock:
            self._ensure_initialized()
            meta = next((m for m in self._read_index() if m.id == project_id), None)
            if meta is None:
                return None
            st = initial_state(meta)
            self._states[project_id] = st
            self._write_state(st)
            return st

    def delete(self, project_id: str) -> bool:
        with self._lock:
            self._ensure_initialized()
            metas = self._read_index()
            if not any(m.id == project_id for m in metas):
                return False
            self._write_index([m for m in metas if m.id != project_id])
            self._states.pop(project_id, None)
            path = self._state_path(project_id)
            if path.exists():
                path.unlink()
            return True


_store: Optional[ProjectStore] = None


def get_store() -> ProjectStore:
    global _store
    if _store is None:
        _store = ProjectStore()
    return _store
