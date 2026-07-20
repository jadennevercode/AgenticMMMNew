"""Domain models — 1:1 mirror of frontend/src/lib/types.ts.

These are the API contract shared with the React frontend. Field names match
the TypeScript interfaces exactly (camelCase) so the frontend consumes them
without translation. Pydantic models use populate_by_name + alias where the
Python idiom (snake_case) differs.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AgentId = Literal["control", "business", "data", "model", "report"]
StageId = Literal["s1", "s2", "s3", "s4", "s5"]
AutomationClass = Literal["M", "A", "C", "H"]
TaskStatus = Literal["pending", "ready", "running", "awaiting_human", "done"]

ArtifactType = Literal[
    "document", "master-data", "dataset", "scorecard", "workflow", "model", "report"
]
ArtifactState = Literal["draft", "proposed", "confirmed", "frozen"]
ArtifactFormat = Literal[
    "sheet", "slides", "doc", "markdown", "review", "validation", "olsTree", "masterData"]

DecisionKind = Literal["approval", "choice", "signoff"]
DecisionStatus = Literal["idle", "open", "resolved"]
ProposalStatus = Literal["open", "accepted", "dismissed"]
InsightKind = Literal["connection", "gap", "conflict", "reference"]
InsightStatus = Literal["new", "actioned", "dismissed"]
AssignmentKind = Literal["upload", "form", "export"]
AssignmentStatus = Literal["idle", "open", "submitted"]
SimEventType = Literal[
    "task_start", "task_done", "artifact", "decision_open",
    "decision_resolved", "suggestion", "finding", "info",
]


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


# ── Artifacts ────────────────────────────────────────────
class SheetTable(CamelModel):
    name: str
    columns: list[str]
    rows: list[list[str]]


class SheetData(CamelModel):
    sheets: list[SheetTable]


class Slide(CamelModel):
    title: str
    bullets: list[str]


class SlidesData(CamelModel):
    slides: list[Slide]


class DocBlock(CamelModel):
    type: Literal["h1", "h2", "p", "li"]
    text: str


class DocData(CamelModel):
    blocks: list[DocBlock]


class ArtifactInstance(CamelModel):
    id: str
    name: str
    task_ref: str = Field(alias="taskRef")
    type: ArtifactType
    stage: StageId
    lineage: list[str] = []
    format: ArtifactFormat
    body: Optional[dict] = None  # SheetData | SlidesData | DocData (serialized)
    content: str = ""
    exportable: Optional[bool] = None
    internal: Optional[bool] = None
    version: int = 1
    state: ArtifactState = "draft"
    produced_by_agent: AgentId = Field(default="control", alias="producedByAgent")
    produced_at_tick: int = Field(default=0, alias="producedAtTick")
    edited_at_tick: Optional[int] = Field(default=None, alias="editedAtTick")


class ArtifactEditProposal(CamelModel):
    """A drafted-but-unapplied chat edit to an artifact (preview-then-confirm).

    `kind="model"` carries the revised backing domain model in `model` plus a
    re-rendered `body` for preview; `kind="free"` carries the new `body`
    (sheet/slides/doc/review) or `content` (markdown) to write directly.
    """
    artifact_id: str = Field(alias="artifactId")
    kind: Literal["free", "model"]
    format: ArtifactFormat
    summary: str = ""
    body: Optional[dict] = None
    content: str = ""
    model: Optional[dict] = None


# ── Evidence / decisions / proposals / insights ──────────
class EvidenceRef(CamelModel):
    artifact_id: str = Field(alias="artifactId")
    note: Optional[str] = None


class DecisionOption(CamelModel):
    id: str
    label: str
    detail: str = ""
    consequence: str = ""
    recommended: Optional[bool] = None


class DecisionRuntime(CamelModel):
    id: str
    kind: DecisionKind
    title: str
    question: str
    evidence: list[EvidenceRef] = []
    recommendation: str = ""
    options: list[DecisionOption] = []
    rework_task_id: Optional[str] = Field(default=None, alias="reworkTaskId")
    rework_option_id: Optional[str] = Field(default=None, alias="reworkOptionId")
    status: DecisionStatus = "idle"
    opened_at_tick: Optional[int] = Field(default=None, alias="openedAtTick")
    resolution: Optional[dict] = None


class DiffLine(CamelModel):
    kind: Literal["add", "remove", "keep"]
    text: str


class Proposal(CamelModel):
    id: str
    target_artifact_id: str = Field(alias="targetArtifactId")
    title: str
    summary: str = ""
    diff: list[DiffLine] = []
    evidence: list[EvidenceRef] = []
    confidence: float = 0.7
    source_agent: AgentId = Field(default="control", alias="sourceAgent")
    source_mode: Literal["pipeline", "assistant"] = Field(default="pipeline", alias="sourceMode")
    after_task: str = Field(default="", alias="afterTask")
    status: ProposalStatus = "open"
    decided_at_tick: Optional[int] = Field(default=None, alias="decidedAtTick")


class InsightAction(CamelModel):
    kind: Literal["create_task", "client_question", "open_asset"]
    label: str
    artifact_id: Optional[str] = Field(default=None, alias="artifactId")


class Insight(CamelModel):
    id: str
    kind: InsightKind
    title: str
    finding: str = ""
    evidence: list[EvidenceRef] = []
    confidence: float = 0.7
    actions: list[InsightAction] = []
    after_task: str = Field(default="", alias="afterTask")
    status: InsightStatus = "new"
    surfaced_at_tick: Optional[int] = Field(default=None, alias="surfacedAtTick")


# ── Assignments / AI options ─────────────────────────────
class AssignmentRuntime(CamelModel):
    id: str
    kind: AssignmentKind
    title: str
    prompt: str = ""
    items: list[str] = []
    submit_label: str = Field(default="Submit", alias="submitLabel")
    status: AssignmentStatus = "idle"
    submitted_at_tick: Optional[int] = Field(default=None, alias="submittedAtTick")
    note: Optional[str] = None
    # Project-Folder category this upload feeds, and whether real parsed files in
    # that category are mandatory before the assignment can be submitted. When
    # required and the folder is empty, the gate stays blocked — no reference
    # fallback (S1 deliverables are parsed only from the user's real uploads).
    category: Optional[str] = None
    requires_upload: bool = Field(default=False, alias="requiresUpload")
    # Optional source-choice gate (e.g. 1.1a: build the factor tree from the
    # industry template vs. upload your own). When present the UI shows the
    # options; picking `choice_upload_category`'s option additionally requires a
    # real file in that Project-Folder category before the gate clears.
    choice_prompt: str = Field(default="", alias="choicePrompt")
    choice_options: list[dict] = Field(default_factory=list, alias="choiceOptions")
    choice_upload_category: Optional[str] = Field(default=None, alias="choiceUploadCategory")
    chosen_source: Optional[str] = Field(default=None, alias="chosenSource")


class AiOption(CamelModel):
    id: str
    label: str
    rationale: str = ""
    tradeoff: str = ""
    recommended: Optional[bool] = None


class AiOptionSet(CamelModel):
    id: str
    prompt: str = ""
    options: list[AiOption] = []
    chosen_id: Optional[str] = Field(default=None, alias="chosenId")


# ── Tasks ────────────────────────────────────────────────
class TaskRuntime(CamelModel):
    id: str
    name: str
    agent: AgentId
    stage: StageId
    klass: AutomationClass = Field(alias="class")
    summary: str = ""
    how: str = ""
    basis_note: Optional[str] = Field(default=None, alias="basisNote")
    work_note: str = Field(default="", alias="workNote")
    depends_on: list[str] = Field(default_factory=list, alias="dependsOn")
    duration: int = 2
    produces: list[str] = []
    status: TaskStatus = "pending"
    progress: float = 0.0
    started_tick: Optional[int] = Field(default=None, alias="startedTick")
    finished_tick: Optional[int] = Field(default=None, alias="finishedTick")
    runs: int = 0
    has_decision: bool = Field(default=False, alias="hasDecision")
    has_assignment: bool = Field(default=False, alias="hasAssignment")
    has_ai_options: bool = Field(default=False, alias="hasAiOptions")

    model_config = ConfigDict(populate_by_name=True)


class TaskFinding(CamelModel):
    text: str
    evidence: list[EvidenceRef] = []
    tone: Literal["info", "flag"] = "info"


class TaskStep(CamelModel):
    label: str
    detail: Optional[str] = None


# ── Activity / ledger / assistant ────────────────────────
class SimEvent(CamelModel):
    id: int
    tick: int
    agent: AgentId
    task_id: Optional[str] = Field(default=None, alias="taskId")
    type: SimEventType
    message: str


class LedgerEntry(CamelModel):
    id: str
    tick: int
    kind: str
    summary: str
    detail: str = ""
    source: str = ""


class AssistantTurn(CamelModel):
    role: Literal["user", "assistant"]
    text: str
    evidence: list[EvidenceRef] = []


# ── Project registry ─────────────────────────────────────
class IndustryRef(CamelModel):
    """A fully-qualified industry selection (codes from domain/industries.py)."""
    l1: str
    l2: str
    l3: str


class ProjectMeta(CamelModel):
    """Lightweight project-registry record — what the landing page lists."""
    id: str
    name: str
    brand: str
    industry: IndustryRef
    kpi: str = "Sell-out Volume"
    created_at: str = Field(alias="createdAt")
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")


# ── Project Profile (parsed + editable framing) ──────────
TimeGranularity = Literal["Year", "Month", "Week"]


class ModelScopeDimension(CamelModel):
    """One axis of the model-scope matrix builder (e.g. Channel → [MT, TT, ...])."""
    name: str
    values: list[str] = []


class ModelScope(CamelModel):
    """The model granularity: dimensions + the resolved scope rows (editable)."""
    dimensions: list[ModelScopeDimension] = []
    rows: list[list[str]] = []  # each row aligns to `dimensions` order


class ProjectProfile(CamelModel):
    """Project framing: creation metadata + parsed intro + editable granularity."""
    project_intro: str = Field(default="", alias="projectIntro")
    time_granularity: TimeGranularity = Field(default="Month", alias="timeGranularity")
    model_scope: ModelScope = Field(default_factory=ModelScope, alias="modelScope")
    source_origin: str = Field(default="", alias="sourceOrigin")  # 'uploaded files' | 'reference case'


# ── Global model-service configuration (LLM + ASR) ───────
# ONE config for every project (not per-project). Holds the ACTUAL credentials
# the user enters once in Settings — the real API key, base URL, and model name —
# never an env-var reference. Empty apiKey ⇒ that service is unconfigured (the LLM
# run-gate blocks; ASR degrades gracefully). Persisted via app/store/model_service.py.
class ServiceCreds(CamelModel):
    api_key: str = Field(default="", alias="apiKey")
    base_url: str = Field(default="", alias="baseUrl")
    model: str = Field(default="", alias="model")


class GlobalModelConfig(CamelModel):
    llm: ServiceCreds = Field(default_factory=ServiceCreds)
    asr: ServiceCreds = Field(default_factory=ServiceCreds)


# ── Factor tree (per-project, with per-node confirm state) ─
FactorSource = Literal["template", "ai", "interview", "manual", "upload"]
FactorStatus = Literal["baseline", "proposed", "accepted", "rejected"]


class FactorRow(CamelModel):
    """One factor-tree leaf (L1→L4 + indicator) with its provenance + confirm state."""
    id: str
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    dimension: str = ""  # dimensions the indicator is measured by (comma-separated; defaults from the project profile's model scope)
    source: FactorSource = "template"
    status: FactorStatus = "baseline"
    rationale: str = ""
    evidence: str = ""  # source quote / citation


class FactorTree(CamelModel):
    rows: list[FactorRow] = []


# ── Data quality scorecard (S2 · per-metric, editable disposition) ─
QualityDisposition = Literal["accept", "flag", "drop"]


class QualitySubScore(CamelModel):
    """One 2.11 subcheck under a dimension (the driver behind a dimension score)."""
    key: str                       # e.g. "consistency.time"
    dimension: str                 # consistency | accuracy | completeness | granularity
    label: str = ""
    score: float = 0.0             # 0 / 0.5 / 1
    note: str = ""                 # English, evidence-grounded
    computed: bool = True          # False = advisory default (needs external ref)
    blocking: bool = True          # whether it can drag the dimension score down


class QualityRow(CamelModel):
    """One factor×metric quality score (2.11) with its human disposition."""
    id: str
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    consistency: float = 0.0
    accuracy: float = 0.0          # 真实性 (accuracy / authenticity)
    completeness: float = 0.0
    granularity: float = 0.0
    # Per-dimension narratives (the Excel 2.12 "...情况" columns), AI-written.
    consistency_note: str = Field(default="", alias="consistencyNote")
    accuracy_note: str = Field(default="", alias="accuracyNote")
    completeness_note: str = Field(default="", alias="completenessNote")
    granularity_note: str = Field(default="", alias="granularityNote")
    # The 10 subcheck breakdown behind the four dimension scores (transparency).
    sub_scores: list[QualitySubScore] = Field(default_factory=list, alias="subScores")
    total: float = 0.0             # Excel 2.12 Total = product of the four dimensions
    auto_verdict: str = Field(default="", alias="autoVerdict")  # pass | borderline | unusable
    disposition: QualityDisposition = "accept"
    note: str = ""


class QualityScorecard(CamelModel):
    rows: list[QualityRow] = []


# ── Statistical score (S2 · 2.4 · per-indicator CV/Pearson/VIF, editable) ─
StatDisposition = Literal["include", "review", "drop"]


class StatScoreRow(CamelModel):
    """One factor-tree indicator scored on the 2.33 statistical tests.

    Raw stats (cv/pearson/vif) plus their 0/0.5/1/2 band scores; Total = sum.
    Verdict follows the KB thresholds; disposition is the human's keep decision.
    """
    id: str
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    cv: float = 0.0                # reference CV (scaled variance / mean)
    pearson: float = 0.0           # Pearson r vs KPI (signed)
    vif: float = 1.0               # variance inflation factor
    cv_score: float = Field(default=0.0, alias="cvScore")
    pearson_score: float = Field(default=0.0, alias="pearsonScore")
    vif_score: float = Field(default=0.0, alias="vifScore")
    total: float = 0.0             # cv_score + pearson_score + vif_score
    auto_verdict: str = Field(default="", alias="autoVerdict")  # Good|Acceptable|unconsiderable
    disposition: StatDisposition = "include"
    # The AI's case for or against this indicator, grounded in the stats above —
    # what turns a bare score into a reviewable recommendation at 2.4d.
    rationale: str = ""
    note: str = ""


class StatScorecard(CamelModel):
    rows: list[StatScoreRow] = []


# ── OLS setup (S2 · 2.5 · AI-proposed, human-reviewed model configuration) ─
# The 2.5 Process asks the human to confirm the response (Y), review the model
# variables (X) and set the transform/control parameters before the fit runs.
# This config is the single source of truth for the OLS — `build_ols_review`
# reads it, and editing it re-fits synchronously (see agents/artifact_edit.py).
OlsSaturation = Literal["hill", "none"]
OlsTrend = Literal["linear", "none"]
OlsSeasonality = Literal["fourier", "dummies", "none"]


class OlsYCandidate(CamelModel):
    """One selectable response variable for a model object."""
    object: str = ""
    metric: str = ""
    metric_type: str = Field(default="", alias="metricType")
    months: int = 0                 # month coverage (selection evidence)
    is_money: bool = Field(default=False, alias="isMoney")  # RMB/value/GMV → money ROI
    recommended: bool = False
    rationale: str = ""


class OlsYChoice(CamelModel):
    """The confirmed response variable for one model object."""
    object: str = ""
    metric: str = ""
    metric_type: str = Field(default="", alias="metricType")
    is_money: bool = Field(default=False, alias="isMoney")


class OlsXCandidate(CamelModel):
    """One candidate model variable, with the 2.4 statistics behind the advice."""
    key: str = ""                   # f"{norm(l4)}|{norm(metric)}"
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    metric: str = ""                # long-table metric label
    is_spend: bool = Field(default=False, alias="isSpend")
    pearson: float = 0.0
    vif: float = 1.0
    cv: float = 0.0
    stat_verdict: str = Field(default="", alias="statVerdict")
    recommended: bool = False
    selected: bool = False          # the human's keep decision
    # An earlier S2 layer already rejected this indicator: it is shown (so the
    # human can see where it went) but can never be ticked back in. `lockedBy`
    # is the ledger layer id that rejected it.
    locked: bool = False
    locked_by: str = Field(default="", alias="lockedBy")
    rationale: str = ""


class OlsEvent(CamelModel):
    """A structural-event window entering the design matrix as a dummy control.

    This is how a 2.3 anomaly the human explained as a business event stops being
    mis-attributed to marketing: the dummy absorbs the window, so the paid
    variables do not have to explain a spike they did not cause.
    """
    id: str = ""
    label: str = ""
    start: int = 0   # yyyymm, inclusive
    end: int = 0     # yyyymm, inclusive


class OlsCapWindow(CamelModel):
    """A window where the response is winsorized (2.3 'outlier capping')."""
    id: str = ""
    label: str = ""
    start: int = 0   # yyyymm, inclusive
    end: int = 0     # yyyymm, inclusive


class OlsParams(CamelModel):
    """Transform + control settings for the fit."""
    adstock: float = 0.5
    saturation: OlsSaturation = "hill"
    hill_half: float = Field(default=1.0, alias="hillHalf")
    # Derived from the 2.3 anomaly review, never hand-edited here: `events` become
    # dummy controls, `caps` winsorize the response over their window. They are
    # resolved at fit time from `ProjectState.anomaly_review` so a stale params
    # draft can never drop a handling decision the human made at 2.3.
    events: list[OlsEvent] = Field(default_factory=list)
    caps: list[OlsCapWindow] = Field(default_factory=list)
    # Controls enter the design matrix raw (never adstocked/saturated) and fold
    # into the baseline — they absorb trend/seasonality so the paid drivers do not.
    trend: OlsTrend = "linear"
    seasonality: OlsSeasonality = "fourier"
    fourier_k: int = Field(default=2, alias="fourierK")
    # Optional unit price: converts an incremental *volume* Y into revenue so ROI
    # becomes a real 增量Revenue/Spend. None → ROI stays volume-per-spend.
    price_per_unit: Optional[float] = Field(default=None, alias="pricePerUnit")


# ── 2.3 anomaly review (AI hypothesizes, the human rules) ─
# Each detected YoY anomaly becomes a card: the AI states a causal hypothesis and
# proposes a handling; the human accepts, edits or rejects it. The accepted
# handling is what actually reaches the model (see `ledger.model_selection`) —
# this replaces the old `ai-2.3` option set, which was chosen and then ignored.
AnomalyHandling = Literal["event", "cap", "raw"]
AnomalyStatus = Literal["pending", "accepted", "rejected"]


class AnomalyHypothesis(CamelModel):
    id: str = ""
    channel: str = ""
    year: str = ""
    growth_pct: float = Field(default=0.0, alias="growthPct")
    # AI's reading of the anomaly, grounded in the computed move + interviews.
    hypothesis: str = ""
    proposed: AnomalyHandling = "event"
    rationale: str = ""
    tradeoff: str = ""
    # The human's ruling. `handling` only bites once status == "accepted".
    status: AnomalyStatus = "pending"
    handling: AnomalyHandling = "event"
    note: str = ""
    # The window the handling applies to (yyyymm, inclusive). Defaults to the
    # anomaly's own year; the human narrows it once the client confirms dates.
    start: int = 0
    end: int = 0


class AnomalyReview(CamelModel):
    rows: list[AnomalyHypothesis] = []


class OlsConfig(CamelModel):
    data_source: str = Field(default="", alias="dataSource")  # "project" | "reference"
    y_candidates: list[OlsYCandidate] = Field(default_factory=list, alias="yCandidates")
    y: list[OlsYChoice] = Field(default_factory=list)
    x_candidates: list[OlsXCandidate] = Field(default_factory=list, alias="xCandidates")
    params: OlsParams = Field(default_factory=OlsParams)
    proposed_at: str = Field(default="", alias="proposedAt")


# ── Knowledge packs (per-industry, editable) ─────────────
# A "knowledge pack" is the set of templates sharing one industry (L1/L2). Each
# section of a pack is one KnowledgeTemplate of a given `kind`:
#   factor_tree · interview · rules · industry_knowledge   (industry-scoped)
#   general_knowledge                                       (cross-industry, l1="general")
TemplateKind = Literal[
    "factor_tree", "interview", "rules", "industry_knowledge", "general_knowledge"]
InterviewCategory = Literal["Leadership", "Management", "Operation", "Data"]

# Sentinel industry code for cross-industry (general) knowledge.
GENERAL_INDUSTRY = "general"

RuleCategory = Literal["quality", "statistical", "technical", "business"]
RuleSeverity = Literal["block", "warn", "info"]


class FactorTreeRow(CamelModel):
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    indicator: str = ""
    # Expected post-OLS bands for this factor, used for fast range-match validation
    # (see agents/data_rules.match_factor_range). Free text, e.g. "0.8~1.3" / "/".
    roi_range: str = Field(default="", alias="roiRange")
    contribution_range: str = Field(default="", alias="contributionRange")


class InterviewQuestion(CamelModel):
    category: InterviewCategory
    role: str = ""
    question: str = ""


class RuleRow(CamelModel):
    """One reusable validation/business rule (S2 quality / statistical / technical)."""
    id: str = ""
    category: RuleCategory = "business"
    name: str = ""
    detail: str = ""
    severity: RuleSeverity = "warn"


class KnowledgeNote(CamelModel):
    """One free-form knowledge note — industry know-how or general method/style."""
    id: str = ""
    title: str = ""
    body: str = ""
    tags: list[str] = Field(default_factory=list)


class KnowledgeTemplate(CamelModel):
    """One reusable, editable section of an industry knowledge pack.

    `kind` selects which payload array is meaningful (the others stay empty),
    mirroring the long-standing factor_rows/interview_questions design."""
    id: str
    kind: TemplateKind
    name: str
    industry_l1: str = Field(alias="industryL1")
    industry_l2: Optional[str] = Field(default=None, alias="industryL2")
    version: int = 1
    builtin: bool = False
    factor_rows: list[FactorTreeRow] = Field(default_factory=list, alias="factorRows")
    interview_questions: list[InterviewQuestion] = Field(
        default_factory=list, alias="interviewQuestions")
    rule_rows: list[RuleRow] = Field(default_factory=list, alias="ruleRows")
    knowledge_notes: list[KnowledgeNote] = Field(
        default_factory=list, alias="knowledgeNotes")
    updated_at: str = Field(default="", alias="updatedAt")


# ── Project Folder (user-uploaded source files) ──────────
FileCategory = Literal[
    "project_background", "industry_reference", "interview_minutes",
    "factor_tree", "data", "raw_data", "other",
]


class ProjectFile(CamelModel):
    """A user-uploaded file stored in the per-project folder + its parse status."""
    id: str
    category: FileCategory
    filename: str
    size: int = 0
    content_type: str = Field(default="", alias="contentType")
    uploaded_at: str = Field(alias="uploadedAt")
    parsed: bool = False
    parse_chars: int = Field(default=0, alias="parseChars")
    parse_error: Optional[str] = Field(default=None, alias="parseError")
    slot: Optional[str] = None  # data-request L3 slot this file is bound to (data category)
    # ASR transcription status for interview audio uploads:
    # "" (not audio) | "pending" | "transcribing" | "done" | "error".
    asr_status: str = Field(default="", alias="asrStatus")
    asr_error: Optional[str] = Field(default=None, alias="asrError")


# ── Data-request upload manifest (S2 · BU-derived L3 directory) ─
DataSlotStatus = Literal["pending", "uploaded", "incomplete", "validated", "error"]


class DataRequestSlot(CamelModel):
    """One L3 workbook slot from the Data Request, + its upload/coverage status."""
    l3: str
    expected_l4s: list[str] = Field(default_factory=list, alias="expectedL4s")
    expected_indicators: int = Field(default=0, alias="expectedIndicators")
    status: DataSlotStatus = "pending"
    file_id: Optional[str] = Field(default=None, alias="fileId")
    filename: str = ""
    covered_indicators: int = Field(default=0, alias="coveredIndicators")
    missing_l4s: list[str] = Field(default_factory=list, alias="missingL4s")
    missing_indicators: list[str] = Field(default_factory=list, alias="missingIndicators")


class DataRequestManifest(CamelModel):
    slots: list[DataRequestSlot] = []
    total: int = 0
    validated: int = 0
    time_granularity: str = Field(default="Month", alias="timeGranularity")
    scope_dims: list[str] = Field(default_factory=list, alias="scopeDims")


# ── Data Engine (raw → review → clean → publish data asset) ─────────
# A standalone, project-scoped data-preparation surface. Client data rarely
# arrives in our standard collection format, so the engine turns arbitrary raw
# uploads into a registered, reusable **data asset** = a slice of the 2.21
# unified long table. AI drafts DuckDB SQL from a field-level cleaning spec; the
# cleaned output persists as parquet and, once published, feeds ``model_df``.

DataAssetStatus = Literal["raw", "reviewed", "spec", "cleaned", "published"]


class RawTable(CamelModel):
    """One discovered raw table (a sheet or CSV) inside a registered source file."""
    name: str
    file_id: str = Field(alias="fileId")
    filename: str = ""
    row_count: int = Field(default=0, alias="rowCount")
    columns: list[str] = []


class FieldProfile(CamelModel):
    """Per-column quick-review profile: type, completeness, and (for numeric /
    time fields) volatility, time granularity and continuity."""
    name: str
    table: str = ""
    dtype: str = "text"  # number | integer | text | date | datetime | boolean | empty
    non_null: int = Field(default=0, alias="nonNull")
    null_ratio: float = Field(default=0.0, alias="nullRatio")
    distinct: int = 0
    sample_values: list[str] = Field(default_factory=list, alias="sampleValues")
    # Full distinct values for low-cardinality text fields (enum candidates).
    enum_values: list[str] = Field(default_factory=list, alias="enumValues")
    # numeric stats (None for non-numeric fields)
    minimum: Optional[float] = Field(default=None, alias="min")
    maximum: Optional[float] = Field(default=None, alias="max")
    mean: Optional[float] = None
    std: Optional[float] = None
    cv: Optional[float] = None  # volatility = std / |mean| (coefficient of variation)
    negatives: int = 0
    # time-axis detection
    is_time_axis: bool = Field(default=False, alias="isTimeAxis")
    time_granularity: Optional[str] = Field(default=None, alias="timeGranularity")  # day|week|month|quarter|year
    continuity: Optional[float] = None  # fraction of present periods over the span [0,1]
    gap_count: Optional[int] = Field(default=None, alias="gapCount")
    note: str = ""


class TableReview(CamelModel):
    """The review of ONE raw table — its own fields, charts, time axis and warnings.
    Every quality and chart is scoped to this single dataset (no cross-table merge)."""
    name: str
    row_count: int = Field(default=0, alias="rowCount")
    column_count: int = Field(default=0, alias="columnCount")
    fields: list[FieldProfile] = []
    charts: list[dict] = []  # ReviewChart[] built from THIS table only
    time_field: Optional[str] = Field(default=None, alias="timeField")
    time_granularity: Optional[str] = Field(default=None, alias="timeGranularity")
    warnings: list[str] = []


class ReviewReport(CamelModel):
    """Quick-review output for a registered source. Reviews are PER TABLE: the AI /
    UI look at one dataset at a time. ``fields`` is the flattened union (kept for the
    long-table grounding + back-compat); ``table_reviews`` is the per-dataset view."""
    row_count: int = Field(default=0, alias="rowCount")
    column_count: int = Field(default=0, alias="columnCount")
    tables: list[RawTable] = []
    fields: list[FieldProfile] = []
    table_reviews: list[TableReview] = Field(default_factory=list, alias="tableReviews")
    charts: list[dict] = []  # deprecated global charts (empty); use table_reviews[].charts
    time_field: Optional[str] = Field(default=None, alias="timeField")
    time_granularity: Optional[str] = Field(default=None, alias="timeGranularity")
    warnings: list[str] = []
    generated_at: str = Field(default="", alias="generatedAt")


CleaningTransform = Literal["passthrough", "mapping", "transform", "calc", "hardcode", "drop"]
NaPolicy = Literal["keep", "drop", "zero", "na"]


class FieldRule(CamelModel):
    """One row of the vertical cleaning-spec editor: how a raw field maps/transforms
    into a target 2.21 long-table column."""
    id: str
    source_field: str = Field(default="", alias="sourceField")  # raw column ('' for hardcoded/synth)
    target_column: str = Field(default="", alias="targetColumn")  # a 2.21 schema column
    transform: CleaningTransform = "passthrough"
    rule: str = ""  # NL cleaning requirement / SQL fragment / mapping name / constant
    na_policy: NaPolicy = Field(default="keep", alias="naPolicy")
    dtype: str = ""  # desired output dtype
    master_data_ref: Optional[str] = Field(default=None, alias="masterDataRef")
    enabled: bool = True


class CleaningSpec(CamelModel):
    rules: list[FieldRule] = []
    target_schema: list[str] = Field(default_factory=list, alias="targetSchema")  # 2.21 columns to emit
    note: str = ""


class SqlDraft(CamelModel):
    """An AI-drafted (human-editable) DuckDB cleaning query + its last preview."""
    sql: str = ""
    status: Literal["draft", "ok", "error"] = "draft"
    error: str = ""
    preview_columns: list[str] = Field(default_factory=list, alias="previewColumns")
    preview_rows: list[list[str]] = Field(default_factory=list, alias="previewRows")
    row_count: int = Field(default=0, alias="rowCount")
    generated_at: str = Field(default="", alias="generatedAt")


class DataAssetVersion(CamelModel):
    version: int
    parquet_path: str = Field(alias="parquetPath")  # relative to the data dir
    row_count: int = Field(default=0, alias="rowCount")
    columns: list[str] = []
    sql: str = ""
    produced_at: str = Field(default="", alias="producedAt")


class DbtNode(CamelModel):
    """One dbt node result (model / seed / test) from the last build, for the UI."""
    unique_id: str = Field(default="", alias="uniqueId")
    resource_type: str = Field(default="", alias="resourceType")  # model|seed|test
    name: str = ""
    layer: str = ""             # staging|intermediate|marts (models only)
    status: str = ""            # success|error|pass|fail|skipped
    execution_time: float = Field(default=0.0, alias="executionTime")
    message: str = ""
    failures: Optional[int] = None  # failing-row count for tests
    relation: str = ""


class EnumViolation(CamelModel):
    """A mart column carrying values outside its target column's standard-value set."""
    column: str
    values: list[str] = []      # offending (out-of-vocabulary) values, capped


class SchemaConformance(CamelModel):
    """Strict field + enum mapping of the mart against the target schema. The publish
    gate requires ``ok`` — a data asset may not enter the long table half-mapped."""
    ok: bool = False
    checked: bool = False        # False when the mart could not be read (e.g. no build)
    missing_required: list[str] = Field(default_factory=list, alias="missingRequired")
    extra: list[str] = []        # mart columns not in the schema (period_date excluded)
    enum_violations: list[EnumViolation] = Field(default_factory=list, alias="enumViolations")
    unenforced_dimensions: list[str] = Field(default_factory=list, alias="unenforcedDimensions")


class DbtSummary(CamelModel):
    """Summary of the asset's last ``dbt build`` — the dbt-workspace transform path."""
    ok: bool = False
    ran_at: str = Field(default="", alias="ranAt")
    command: str = ""
    error: str = ""
    mart: str = ""              # the mart model name (published relation)
    models: int = 0
    tests: int = 0
    passed: int = 0
    failed: int = 0
    ai_rounds: int = Field(default=0, alias="aiRounds")  # repair rounds if AI-generated
    nodes: list[DbtNode] = []
    # pipeline step id → compiled dbt model name (drives per-step status/preview in the UI)
    step_models: dict[str, str] = Field(default_factory=dict, alias="stepModels")
    conformance: Optional[SchemaConformance] = None


# ── Transform pipeline (Data Engine) ─────────────────────
# Typed, human-reviewable transform steps. The AI proposes step parameters; the
# human edits each step in its own inspector; the compiler turns the step DAG
# deterministically into dbt models — no opaque AI SQL on the main path.
StepKind = Literal[
    "field_map", "enum_map", "join", "union", "aggregate", "filter", "derive", "custom_sql"
]


class FieldMapEntry(CamelModel):
    """Map one source column (or SQL expression) onto an output column."""
    source: str = ""            # source column name ('' when expr is used)
    target: str = ""            # output column name
    cast: str = ""              # '' | integer | double | date | text
    expr: str = ""              # optional SQL expression overriding source (e.g. a constant)


class EnumMapEntry(CamelModel):
    """Map one raw value to its canonical value (compiled into a dbt seed)."""
    raw: str
    canonical: str = ""
    confidence: float = 1.0     # AI-suggestion confidence; 1.0 for human entries
    by: Literal["ai", "human"] = "human"


class JoinConfig(CamelModel):
    how: Literal["left", "inner"] = "left"
    left_on: list[str] = Field(default_factory=list, alias="leftOn")
    right_on: list[str] = Field(default_factory=list, alias="rightOn")
    # Right-side columns to carry into the output (left columns always pass through).
    right_columns: list[str] = Field(default_factory=list, alias="rightColumns")


class AggSpec(CamelModel):
    column: str
    func: Literal["sum", "avg", "min", "max", "count"] = "sum"
    alias: str = ""


class DeriveSpec(CamelModel):
    name: str
    expr: str                   # SQL expression over the input columns


class TransformStep(CamelModel):
    """One node of the transform pipeline. ``inputs`` reference upstream step ids
    or raw sources as ``source:<table>``. Exactly the config for ``kind`` is used."""
    id: str
    kind: StepKind
    name: str = ""              # display name; basis of the compiled model name
    note: str = ""              # plain-English description (AI-filled, human-editable)
    inputs: list[str] = Field(default_factory=list)
    field_map: list[FieldMapEntry] = Field(default_factory=list, alias="fieldMap")
    enum_field: str = Field(default="", alias="enumField")   # column the enum_map applies to
    enum_map: list[EnumMapEntry] = Field(default_factory=list, alias="enumMap")
    join: Optional[JoinConfig] = None
    group_by: list[str] = Field(default_factory=list, alias="groupBy")
    aggs: list[AggSpec] = Field(default_factory=list)
    filter_expr: str = Field(default="", alias="filterExpr")
    derive: list[DeriveSpec] = Field(default_factory=list)
    sql: str = ""               # custom_sql body; inputs exposed as CTEs input_1..n
    # aggregate only: collapse rows across their originating source file instead of
    # keeping the compiler's default per-source granularity (see compiler provenance).
    merge_sources: bool = Field(default=False, alias="mergeSources")


class TransformPipeline(CamelModel):
    steps: list[TransformStep] = []
    output_step: str = Field(default="", alias="outputStep")  # step id that becomes the mart
    note: str = ""


TargetColumnKind = Literal["dimension", "time", "factor", "metric", "value"]


class TargetColumn(CamelModel):
    """One column of the project's target long-table schema — the shape every
    published mart must emit. Seeded from reference/target-schema.xlsx, editable
    per project, and used to ground the AI's dbt codegen."""
    name: str                       # the mart column to emit (e.g. "brand")
    label: str = ""                 # human label ("Brand")
    definition: str = ""            # plain-English meaning
    kind: TargetColumnKind = "dimension"
    required: bool = True
    standard_values: list[str] = Field(default_factory=list, alias="standardValues")


# FND-001 · Unified indicator metadata.
# `metric_type` (below) stays the OLS **model role** — "Y" | "spending" | "X" — the
# engine has always used. The SEMANTIC type (what kind of number it is) is the new
# `semantic_type` enum, which drives display/format/aggregation/OLS-eligibility and
# is the one the client asked to see (DATA-008). The two are kept consistent by
# `app/agents/indicator_metadata.py` (model_role derives the role from the semantic).
MetricType = Literal[
    "kpi_volume", "kpi_value", "spending", "count", "rate", "index", "other"]
Aggregation = Literal[
    "sum", "count", "average", "min", "max", "distinct_count", "weighted_average"]
IndicatorSource = Literal[
    "project_material", "interview", "uploaded_tree", "template", "ai", "data_upload"]


class Indicator(CamelModel):
    """A published, reusable indicator = one metric × factor-tree path, registered
    when a data asset publishes. Data Intake references these instead of raw files."""
    id: str
    metric: str
    metric_type: str = Field(default="", alias="metricType")  # OLS role: Y | spending | X
    l1: str = ""
    l2: str = ""
    l3: str = ""
    l4: str = ""
    # Full factor path (FND-001): L5–L8 complete the L1–L8 lineage for L4–L8 drilldown.
    l5: str = ""
    l6: str = ""
    l7: str = ""
    l8: str = ""
    unit: str = ""
    # FND-001 semantic metadata (see indicator_metadata.classify_indicator).
    semantic_type: MetricType = Field(default="other", alias="semanticType")
    currency: Optional[str] = None
    aggregation: Aggregation = "sum"
    number_format: str = Field(default="number", alias="numberFormat")  # money|percent|index|integer|number
    source: IndicatorSource = "data_upload"
    rule_version: str = Field(default="", alias="ruleVersion")
    asset_id: str = Field(default="", alias="assetId")
    asset_name: str = Field(default="", alias="assetName")
    coverage_start: str = Field(default="", alias="coverageStart")
    coverage_end: str = Field(default="", alias="coverageEnd")
    rows: int = 0
    # Grounding against the Business-Understanding factor tree: matched → the
    # FactorRow id; unmatched → flagged for human review in the catalog.
    tree_grounded: bool = Field(default=False, alias="treeGrounded")
    tree_row_id: str = Field(default="", alias="treeRowId")


class DataAsset(CamelModel):
    """A project-scoped data asset: raw source(s) → review → cleaning spec → SQL →
    published versions (parquet). Published assets feed the 2.21 long table."""
    id: str
    name: str
    status: DataAssetStatus = "raw"
    description: str = ""
    source_file_ids: list[str] = Field(default_factory=list, alias="sourceFileIds")
    raw_tables: list[RawTable] = Field(default_factory=list, alias="rawTables")
    review: Optional[ReviewReport] = None
    cleaning_spec: Optional[CleaningSpec] = Field(default=None, alias="cleaningSpec")
    sql_draft: Optional[SqlDraft] = Field(default=None, alias="sqlDraft")
    pipeline: Optional[TransformPipeline] = None
    dbt: Optional[DbtSummary] = None
    versions: list[DataAssetVersion] = []
    latest_version: int = Field(default=0, alias="latestVersion")
    lineage: list[str] = []
    created_at: str = Field(default="", alias="createdAt")
    updated_at: str = Field(default="", alias="updatedAt")


# Master-data mapping (Phase 4): editable Product/Geo/Channel/Time lookups applied
# as DuckDB joins during cleaning so raw names normalise to canonical values.
MasterDataKind = Literal["product", "geo", "channel", "time"]


class MasterDataMapRow(CamelModel):
    source: str = ""
    target: str = ""


class MasterDataMap(CamelModel):
    id: str
    kind: MasterDataKind
    name: str
    rows: list[MasterDataMapRow] = []


# FND-002 · Time window (comparable-period definition), maintained per project and
# reused by Business Validation and Reporting via its id (DATA-005 consumes it — it
# generalises the period engine to half-year / quarter / YTD / rolling / custom and
# enforces equal-length, same-season comparison windows).
TimeWindowPeriod = Literal[
    "year", "half_year", "quarter", "month", "ytd", "rolling", "custom"]
TimeComparison = Literal["none", "yoy", "pop", "custom"]  # yoy=same window prior year


class TimeWindow(CamelModel):
    id: str
    name: str
    period_type: TimeWindowPeriod = Field(default="custom", alias="periodType")
    # Inclusive month bounds as 'YYYY-MM' (empty until set).
    current_start: str = Field(default="", alias="currentStart")
    current_end: str = Field(default="", alias="currentEnd")
    comparison_type: TimeComparison = Field(default="none", alias="comparisonType")
    comparison_start: str = Field(default="", alias="comparisonStart")
    comparison_end: str = Field(default="", alias="comparisonEnd")
    # For period_type == 'rolling': window length in months (e.g. 12 = last 12 months).
    rolling_months: int = Field(default=0, alias="rollingMonths")
    version: int = 1
