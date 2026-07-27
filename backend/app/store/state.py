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
    IndicatorCoverage,
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
    TimeWindow,
    ToolInvocation,
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
    # S2 · 2.3s: the client's business-validation sign-off ("<l4>|<indicator>" ->
    # "yes"|"no", both normalised — see `ledger.signoff_key`). Bare keys with no
    # '|' are legacy: they carry a normalised L3 and mean "this whole factor",
    # expanded against the indicator universe on read (`ledger.signoff_drop_pairs`).
    # The two shapes coexist in one dict with no migration step.
    # Source of truth for the ledger's signoff layer. It lives HERE and not in the
    # a-business-validation body because a producing handler rewrites that body on
    # every run — a human verdict stored there is erased by the next re-render (and
    # was never persisted at all: the UI only mutated its local copy).
    # No alias — see the note on `ols_config`.
    signoffs: dict[str, str] = Field(default_factory=dict)
    # S2 · 2.3: per-tab Graphic Walker chart specs the user saved in the Business
    # Validation explorer, as {"specs": [...], "version": int}. Empty {} → the
    # frontend falls back to the generated default tabs. NO alias (see ols_config).
    validation_specs: dict = Field(default_factory=dict)
    # S2 · 2.3: per-chart AI analyses, keyed by the filter state that produced the
    # chart (`validation_analysis.analysis_key`). Cleared wholesale when the dataset
    # or a 2.1 role/aggregation override changes — every analysis is a reading of
    # numbers that just moved. NO alias (see ols_config).
    validation_chart_analyses: dict = Field(default_factory=dict)
    # 2.1 Data Processing: factor rows the user explicitly ignores in the
    # FactorTree↔DataAssets mapping (rowId → note). A row is resolved when it is
    # either mapped by a published indicator or listed here; the 2.1 gate blocks
    # while any active row is still unresolved. Not blueprint-derived → persists.
    factor_map_ignores: dict[str, str] = Field(default_factory=dict, alias="factorMapIgnores")
    # 2.1 Data Processing: per-indicator human overrides keyed by
    # `indicator_metadata.indicator_key(l4, metric)`.
    #  · metric_type_overrides: the model role the user assigned — "Y" (response) /
    #    "X" (driver) / "excluded" (not in model). Applied at the `model_df` seam so
    #    every downstream reader is consistent and there is exactly one Y. Absent key
    #    → fall back to the name-based `classify_indicator` role.
    #  · aggregation_overrides: how the indicator rolls up over time/dimensions
    #    ("sum"/"average"/"weighted_average"/"min"/"max"), consumed by the national
    #    aggregation layer, the 2.3 chart series and master data. Absent → the
    #    classifier default (spend/volume/count→sum, rate/price/index→average).
    # No alias (internally consumed; surfaced to the UI via FactorMapRow) — see the
    # note on `ols_config`.
    metric_type_overrides: dict[str, str] = Field(default_factory=dict)
    aggregation_overrides: dict[str, str] = Field(default_factory=dict)
    # Data Engine: project-scoped data assets + master-data maps (not blueprint-derived,
    # so they persist across heal_state like artifacts).
    data_assets: list[DataAsset] = Field(default_factory=list, alias="dataAssets")
    master_data: list[MasterDataMap] = Field(default_factory=list, alias="masterData")
    # FND-002: project-scoped time windows (comparable-period definitions), reused by
    # Business Validation and Reporting. Not blueprint-derived → persists across heal.
    time_windows: list[TimeWindow] = Field(default_factory=list, alias="timeWindows")
    # Data Engine: the target long-table schema (None → the default).
    target_schema: Optional[list[TargetColumn]] = Field(default=None, alias="targetSchema")
    # LEGACY (drained by heal_state): indicators used to be stored here, built by
    # groupby over each published mart. They are now derived from the factor tree
    # (app/dataeng/indicators.py). The field stays declared only so a saved
    # project's human bindings can be migrated — Pydantic drops unknown keys on
    # load, so removing it outright would destroy them before the migration ran.
    indicators: list[Indicator] = Field(default_factory=list, alias="indicators")
    # What publish persists: which (asset × metric) supplies which factor row.
    indicator_coverage: list[IndicatorCoverage] = Field(default_factory=list)
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
    # Explicit tool-call trace (newest first, capped) — see app/tools/tracing.py.
    # snake_case with no alias, like `events`: the frontend store reads it as-is.
    tool_invocations: list[ToolInvocation] = Field(default_factory=list)
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


def _seed_reference_data(st: ProjectState) -> None:
    """Register the reference case's real data as per-source Data-Engine assets.

    Only for reference-backed projects (the Danone demo): their "uploaded data" is
    the real 23.8k-row client reference table. Registering it by source through the
    real ``claim_published_metrics`` path gives every coverage a real asset + window,
    so 2.1 mapping resolves against genuine published indicators — never the
    fabricated ``st.indicators`` splat the v2 demo used. A no-op (best-effort) for
    projects that bring their own data or when the reference files are absent.
    """
    try:
        from app.agents.dataset_cache import _allow_reference
        if not _allow_reference(st.project_id):
            return
        from app.dataeng.seed_reference_assets import seed_reference_assets
        seed_reference_assets(st.project_id, st)
    except Exception:  # noqa: BLE001 — seeding data must never block project reset
        pass


def _migrate_indicators_to_coverage(st: ProjectState) -> int:
    """Carry a saved project's manual factor bindings onto coverage records.

    Indicators used to be stored, built by groupby over each published mart. They
    are now derived from the factor tree, so the stored list is drained here.
    **A binding destroyed here cannot be recovered**, so the rule is deliberately
    conservative: carry every binding EXCEPT the ones explicitly marked ``auto``,
    which are the only ones a re-publish provably reproduces.

    ``bound_by`` postdates some of the data. The real Danone project holds its 2.1
    gate open with ten bindings carrying ``""`` whose indicator path matches their
    factor row's by no rule in the code — only the metric name lines up — so
    ``_reclaim_published_assets`` does not reproduce them either. Treating "not
    marked human" as "safe to drop" silently re-blocked that gate.

    Carried bindings land as ``human``: they are not re-derivable, so a later
    re-publish must not quietly discard them.

    Returns the number of bindings carried, for logging/verification.
    """
    if not st.indicators:
        return 0
    known = {c.id: c for c in st.indicator_coverage}
    carried = 0
    for ind in st.indicators:
        if ind.bound_by == "auto" or not ind.tree_row_id:
            continue
        existing = known.get(ind.id)
        if existing is not None:
            # `_reclaim_published_assets` already rebuilt this coverage from the
            # parquet and found no factor row for it — that is precisely the
            # binding this migration exists to preserve, so overlay it rather
            # than treating the record's presence as "already handled".
            if not existing.tree_row_id:
                existing.tree_row_id = ind.tree_row_id
                existing.bound_by = "human"
                carried += 1
            continue
        st.indicator_coverage.append(IndicatorCoverage(
            id=ind.id, treeRowId=ind.tree_row_id,
            assetId=ind.asset_id, assetName=ind.asset_name,
            metric=ind.metric, metricType=ind.metric_type,
            l1=ind.l1, l2=ind.l2, l3=ind.l3, l4=ind.l4,
            semanticType=ind.semantic_type, unit=ind.unit, currency=ind.currency,
            aggregation=ind.aggregation, numberFormat=ind.number_format,
            ruleVersion=ind.rule_version,
            coverageStart=ind.coverage_start, coverageEnd=ind.coverage_end,
            rows=ind.rows, boundBy="human"))
        carried += 1
    st.indicators = []
    return carried


def _reclaim_published_assets(st: ProjectState) -> int:
    """Replay the publish-time claim over assets that published before the refactor.

    ``_migrate_indicators_to_coverage`` drops automatic bindings on purpose — they
    are derived, and a re-publish rebuilds them. But an existing project can have
    dozens of published assets, and nobody is going to re-publish them by hand to
    get its 2.1 mapping back. The parquet is still on disk, so the claim is
    replayed from it, producing exactly what the publish path would have written.

    Runs before ``_migrate_indicators_to_coverage`` so the legacy bindings overlay
    a complete rebuild rather than competing with one, and only for published
    assets that have no coverage yet — after a full pass every one of them does,
    so this is effectively a one-shot. ``heal_state`` itself runs once per project
    per process (``ProjectStore.get`` caches), so the parquet reads are not on a
    request path. Returns the number of assets reclaimed.
    """
    covered = {c.asset_id for c in st.indicator_coverage}
    published = [a for a in st.data_assets
                 if a.status == "published" and a.versions and a.id not in covered]
    if not published:
        return 0
    from app.dataeng import assets as asset_svc
    from app.dataeng.dbt.service import claim_published_metrics

    done = 0
    for asset in published:
        latest = max(asset.versions, key=lambda v: v.version)
        df = asset_svc.read_version(st.project_id, latest)
        if df is None or df.empty:
            continue
        claim_published_metrics(st, asset, df)
        done += 1
    return done


def heal_state(st: ProjectState) -> ProjectState:
    """Reconcile a loaded state with the current blueprint: add any missing
    tasks/decisions/assignments/ai-choices, and prune ones the blueprint no
    longer defines (e.g. removed tasks/artifacts), so blueprint changes don't
    leave stale entries on saved projects."""
    # Order matters: rebuild coverage from the published parquet FIRST, then
    # overlay the legacy bindings nothing reproduces.
    _reclaim_published_assets(st)
    _migrate_indicators_to_coverage(st)
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
    # Same idea for the new 2.1d mapping-review gate, which sits between 2.1
    # and 2.2. On a project that already finished 2.2 before this gate
    # existed, mark the freshly back-filled 2.1d as done so a completed run
    # isn't reopened at a mid-S2 human gate.
    if ("2.1d" not in pre_existing and "2.1d" in st.tasks
            and st.tasks.get("2.2") is not None and st.tasks["2.2"].status == "done"):
        st.tasks["2.1d"].status = "done"
        st.tasks["2.1d"].progress = 100.0
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
    # Back-fill for projects saved before validation_specs existed.
    if not hasattr(st, "validation_specs") or st.validation_specs is None:
        st.validation_specs = {}
    if not hasattr(st, "validation_chart_analyses") or st.validation_chart_analyses is None:
        st.validation_chart_analyses = {}
    # 2.1 now offers only SUM / AVG. Legacy overrides are mapped onto the closest
    # of the two rather than left as values the canvas cannot display: an averaging
    # variant becomes `average`, everything else `sum`.
    legacy_agg = getattr(st, "aggregation_overrides", None)
    if isinstance(legacy_agg, dict):
        for k, v in list(legacy_agg.items()):
            if v not in ("sum", "average"):
                legacy_agg[k] = "average" if v == "weighted_average" else "sum"
    # Per-channel-type screening migration: legacy scorecard rows / OLS candidates
    # carry object="" (pre-migration global verdicts). The ledger resolvers treat an
    # empty object as OBJECT_ANY (applies to every channel), so a saved global verdict
    # keeps its exact effect — no row rewrite required. Left as a comment so a future
    # reader does not "fix" the empty object by guessing a channel.
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
    # BIZ-001 migration: the model scope is now fixed to Brand × Channel × Geo. Relabel
    # our own legacy default skeleton names on saved profiles ("Product" → "Brand",
    # "Platform & Region" → "Geo"). This is a label-only rename of the shipped defaults;
    # we deliberately do NOT remap dimensions that hold real platform values into "Geo"
    # (that would silently mislabel Platform data as geography — the exact risk the client
    # flagged). Projects with real inferred scope re-frame to Brand/Channel/Geo on re-run.
    if st.profile is not None:
        _LEGACY_DIM_RELABEL = {"Product": "Brand", "Platform & Region": "Geo"}
        for d in st.profile.model_scope.dimensions:
            if d.name.strip() in _LEGACY_DIM_RELABEL:
                d.name = _LEGACY_DIM_RELABEL[d.name.strip()]
    # FND-001 backfill: coverage published before the semantic classifier existed
    # carries no ruleVersion — classify it now so its type/unit/aggregation/format
    # are populated (the OLS role `metric_type` is left untouched). Runs after the
    # migration above, so records carried off the legacy list are covered too.
    if st.indicator_coverage:
        from app.agents.indicator_metadata import (
            INDICATOR_META_RULE_VERSION, classify_indicator)
        for cov in st.indicator_coverage:
            if not cov.rule_version:
                meta = classify_indicator(cov.metric)
                cov.semantic_type = meta.metric_type
                cov.unit = cov.unit or meta.unit
                cov.currency = meta.currency
                cov.aggregation = meta.aggregation
                cov.number_format = meta.fmt
                cov.rule_version = INDICATOR_META_RULE_VERSION
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
            _seed_reference_data(st)
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
