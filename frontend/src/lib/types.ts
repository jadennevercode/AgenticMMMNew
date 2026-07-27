/**
 * Domain types — aligned with docs/agent-design/08-product-architecture-v2.md.
 * Internal architecture terms (Proposal, AutomationClass, …) are allowed in code
 * identifiers but must NEVER appear in UI copy — see ui-language.ts (decision D4).
 */

export type AgentId = 'control' | 'business' | 'data' | 'model' | 'report'

export type StageId = 's1' | 's2' | 's4' | 's5'

/**
 * Automation class per task sub-step (08 §2):
 * M mechanical · A AI-automatable · C cognitive · H human-only.
 */
export type AutomationClass = 'M' | 'A' | 'C' | 'H'

export type TaskStatus = 'pending' | 'ready' | 'running' | 'awaiting_human' | 'done'

export interface AgentProfile {
  id: AgentId
  name: string
  role: string
  capabilities: string[]
}

export interface StageProfile {
  id: StageId
  index: number
  name: string
  goal: string
  /** Milestone closing this stage (human-confirmed) */
  milestone: string
}

/* ── Artifacts ─────────────────────────────────────────── */

export type ArtifactType =
  | 'document'
  | 'master-data'
  | 'dataset'
  | 'scorecard'
  | 'workflow'
  | 'model'
  | 'report'

/** Lifecycle per 08 §8 Artifact Management */
export type ArtifactState = 'draft' | 'proposed' | 'confirmed' | 'frozen'

/**
 * Board-level status of a deliverable, derived from the status of the
 * task chain that builds it (see lib/artifact-graph.ts). Drives the
 * artifact-driven Project workspace.
 */
export type DeliverableState = 'locked' | 'queued' | 'building' | 'needs-you' | 'ready' | 'confirmed'

/**
 * The document kind a deliverable takes — mirrors the reference pack
 * (Excel workbooks, slide decks, Word-style notes, markdown). Drives the
 * canvas renderer/editor.
 */
export type ArtifactFormat =
  | 'sheet' | 'slides' | 'doc' | 'markdown' | 'review' | 'validation' | 'olsTree' | 'masterData'

/** A spreadsheet: one or more named sheets, each a column header + rows */
export interface SheetData {
  /** `preRows` are free-form banner rows rendered above the column header (e.g. a
   *  per-target title + meta line); ragged widths are allowed. */
  sheets: { name: string; columns: string[]; rows: string[][]; preRows?: string[][] }[]
}
/** A slide deck */
export interface SlidesData {
  slides: { title: string; bullets: string[] }[]
}
/** A Word-style document of typed blocks */
export interface DocData {
  blocks: { type: 'h1' | 'h2' | 'p' | 'li'; text: string }[]
}

/** A visualized business-validation review (2.31/2.32) — computed chart series. */
export type ChartType = 'line' | 'bar' | 'dualAxis' | 'share' | 'quadrant' | 'waterfall'
export interface ChartSeries {
  name: string
  data: number[]
  axis?: 'left' | 'right'
  color?: string
}
export interface QuadrantPoint {
  label: string
  x: number
  y: number
}
export interface ReviewChart {
  id: string
  type: ChartType
  title: string
  x: string[]
  series: ChartSeries[]
  points?: QuadrantPoint[] // for quadrant scatter
  unit?: string
  factors?: string[]
  interpretation?: string
  conclusion?: string
  signoff?: string // '' | 'yes' | 'no'
}
export interface ReviewTable {
  title: string
  columns: string[]
  rows: string[][]
  note?: string
}
export interface ReviewStep {
  id: string
  title: string
  intro?: string
  charts: ReviewChart[]
  tables?: ReviewTable[]
}
export interface ReviewData {
  steps: ReviewStep[]
}

/**
 * Business Validation (task 2.3) body — per-FactorTree-L3 metadata. The chart
 * series themselves are NOT stored here; they are queried live (`validationSeries`)
 * so the page's filters resolve against real rows. This body only persists the
 * per-factor interpretation and sign-off.
 */
export interface ValidationGroup {
  l1: string
  l2: string
  l3: string
  rowIds: string[]
  defaultIndicators: string[]
  interpretation: string
  signoff: string // '' | 'yes' | 'no'
  /** The (l4, indicator) pairs this chart covers — the sign-off key space.
   *  Optional: legacy artifact bodies predate this field. */
  pairs?: { l4: string; indicator: string }[]
}
export interface ValidationAnomaly {
  channel: string
  year: string
  growthPct: number
}
export interface ValidationReviewData {
  kpiMetric: string
  groups: ValidationGroup[]
  anomalies: ValidationAnomaly[]
  note?: string
  specs?: ValidationSpec[]
}

/** Explorer dataset row for a single L3 (task 2.3 self-serve explorer). */
export interface ValidationField {
  fid: string
  name: string
  semanticType: 'quantitative' | 'nominal' | 'ordinal' | 'temporal'
  analyticType: 'dimension' | 'measure'
}
export interface ValidationDataset {
  columns: ValidationField[]
  rows: Record<string, string | number | null>[]
  rowCount: number
  capped: boolean
  note: string
}
export interface ValidationSpec {
  specId: string
  l3: string
  title: string
  encoding: { x: string; yKpi: string; yOverlay: string[]; overlayKind: 'bar' | 'line' }
  filter: { l3: string; kpiL3?: string }
}
/** A saved Graphic Walker chart list + version (opaque GW chart JSON). */
export interface ValidationSpecStore {
  specs: unknown[]
  version: number
}

/** Live series payload from `/validation/series` (one L3 chart's data). */
export interface ValidationSeriesRequest {
  l3: string
  l4?: string
  l5?: string  // DATA-004: L4–L8 cascade drilldown
  l6?: string
  l7?: string
  l8?: string
  indicators?: string[]
  grain?: string
  sources?: string[]
  brand?: string[]
  channelType?: string[]
  provinceGroup?: string[]
  timeWindowId?: string  // DATA-005: scope + compare against a saved time window
  kpiMetric?: string     // explorer-only override; the 2.3 chart never sends one
  /** 1–12 → the yearly table compares that calendar month across years; 0 = full year. */
  yoyMonth?: number
}
/** DATA-008: display metadata attached to a series/row so the UI formats it right. */
export interface IndicatorDisplayMeta {
  unit?: string
  numberFormat?: string  // money | percent | index | integer | number
  aggregation?: string   // DATA-007
  semanticType?: string
}
export interface ValidationKpi extends IndicatorDisplayMeta {
  metric: string
  kind: 'area'
  data: number[]
}
export interface ValidationOverlay extends IndicatorDisplayMeta {
  metric: string
  metricType: string
  kind: 'bar' | 'line'
  data: (number | null)[]
}
export interface ValidationYearlyRow extends IndicatorDisplayMeta {
  metric: string
  values: (number | null)[]
  yoy: (number | null)[]
}
export interface ValidationIndicatorOption {
  metric: string
  metricType: string
  l4: string
}
export interface ValidationBreadcrumbStep {
  level: string
  value: string
}
/** DATA-005: current-window vs comparison-window totals for one indicator. */
export interface ValidationComparisonRow extends IndicatorDisplayMeta {
  metric: string
  current: number
  comparison: number | null
  deltaPct: number | null
}
export interface ValidationComparison {
  name: string
  current: { start: string; end: string; label: string }
  comparison: { start: string; end: string; label: string } | null
  comparisonType: string
  equalLength: boolean
  rows: ValidationComparisonRow[]
}
export interface ValidationSeriesResponse {
  l3: string
  grain: string
  x: string[]
  kpi: ValidationKpi | null
  /** DATA-009: the KPI metric currently used as the backdrop. */
  kpiMetric?: string
  series: ValidationOverlay[]
  yearly: {
    years: number[]
    rows: ValidationYearlyRow[]
    /** Echo of the requested month (0 = full year) and its label. */
    yoyMonth?: number
    monthLabel?: string
  }
  /** DATA-005: current vs comparison window totals (present when a window is applied). */
  comparison?: ValidationComparison | null
  /** DATA-004: resolved L3 → L4…L8 drill path, shared by chart/table/export. */
  breadcrumb?: ValidationBreadcrumbStep[]
  options: {
    grains: string[]
    l4: string[]
    /** DATA-004: cascade options; empty list = level Not Available (hide it). */
    l5: string[]
    l6: string[]
    l7: string[]
    l8: string[]
    indicators: ValidationIndicatorOption[]
    sources: string[]
    brand: string[]
    channelType: string[]
    provinceGroup: string[]
  }
}

/** One thing the chart analysis noticed, anchored to a period. */
export interface ChartObservation {
  period: string
  metric: string
  note: string
}
/**
 * The AI's reading of exactly the series a factor chart is showing. Cached per
 * filter state; `seriesDigest` is a fingerprint of the plotted numbers, so a
 * reading of data that has since moved can be told apart from a current one.
 */
export interface ValidationChartAnalysis {
  key: string
  l3: string
  filterLabel: string
  headline: string
  trends: string[]
  anomalies: ChartObservation[]
  inflections: ChartObservation[]
  caveats: string[]
  seriesDigest: string
  generatedAt: string
  /** True when no language model was configured and the computed facts were
   *  rendered as prose instead. */
  fallback: boolean
}

/** ── OLS Regression Test (2.5, format 'olsTree') ── */
export type OlsRowStatus = 'inRange' | 'review' | 'noBenchmark' | 'notInModel' | 'dropped' | 'notMapped'
export type OlsRangeStatus = 'in' | 'out' | 'none'
export interface OlsObjectSummary {
  object: string
  nObs: number
  drivers: number
  r2: number | null
  adjR2: number | null
  mape: number | null
  durbinWatson: number | null
  baselinePct: number | null
  redFlags: string[]
  error: string
  /** The response actually fitted, the df left after controls, and the controls used. */
  yMetric?: string
  roiUnit?: string
  dfRemaining?: number | null
  controls?: string[]
}
export interface OlsRowResult {
  object: string
  coef: number | null
  tValue: number | null
  pValue: number | null
  roi: number | null
  contribution: number | null
}
export interface OlsTreeRow {
  key: string
  treeRowId: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  mapped: boolean
  inModel: boolean
  droppedBy: '' | 'mapping' | 'quality' | 'signoff' | 'statistical' | 'range'
  objects: string[]
  coef: number | null
  tValue: number | null
  pValue: number | null
  significant: boolean | null
  roi: number | null
  contribution: number | null
  /** Set only when the ROI borrowed its L4's spend as the denominator (the
   *  indicator itself is not a spend metric) — e.g. `÷ 站内投流 spend (Spending)`. */
  roiBasis?: string
  roiRange: string
  contributionRange: string
  rangeSource: 'knowledge' | 'reference' | ''
  roiStatus: OlsRangeStatus
  contributionStatus: OlsRangeStatus
  status: OlsRowStatus
  flagReason: string
  results: OlsRowResult[]
  /** The AI's judgement of this factor against its Knowledge band. Rides alongside
   *  `roiStatus` / `contributionStatus` — it never replaces the computed check. */
  aiVerdict?: '' | 'consistent' | 'questionable' | 'implausible' | 'noBenchmark'
  aiRationale?: string
}
/** One trial regression the 2.5 indicator search ran. */
export interface OlsSearchTrial {
  trial: number
  seed: boolean
  triedFor: string
  alternate: string
  l4: string
  indicator: string
  r2: number
  coef: number | null
  tValue: number | null
  pValue: number | null
  significant: boolean | null
  signExpected: boolean
  signCorrect: boolean
  roi: number | null
  contribution: number | null
  roiStatus: OlsRangeStatus
  contributionStatus: OlsRangeStatus
  roiRange: string
  contributionRange: string
  objectiveInRange: number
  objectiveSigned: number
}
export interface OlsSearchFactor {
  l4: string
  chosen: string
  candidates: string[]
  status: OlsRangeStatus
}
/** What the per-L4 indicator search tried, and what won. */
export interface OlsSearchTrace {
  fits: number
  l4Searched: number
  candidates: number
  swaps: number
  inRange: number
  signedOk?: number
  r2: number
  factorsSkipped?: number
  trials: OlsSearchTrial[]
  perFactor: OlsSearchFactor[]
  note: string
}
export interface OlsTreeSummary {
  total: number
  inModel: number
  inRange: number
  flagged: number
  noBenchmark: number
  notInModel: number
  dropped: number
  notMapped: number
}
export interface OlsSetupSummary {
  dataSource: string
  roiUnit: string
  configured: boolean
  selectedX: number
  totalX: number
  params: OlsParams | null
  y: OlsYChoice[]
}
export interface OlsTreeData {
  objects: OlsObjectSummary[]
  tree: OlsTreeRow[]
  summary: OlsTreeSummary
  setup?: OlsSetupSummary
  note?: string
  /** Present once 2.5 has run its per-L4 indicator search. */
  search?: OlsSearchTrace | null
}

/**
 * OLS setup (2.5) — AI-proposed, human-confirmed through the 2.5y / 2.5x / 2.5p
 * Process steps. Mirrors backend/app/domain/models.py OlsConfig. Saving it
 * re-fits the regression (PUT /ols-config → apply_ols_config).
 */
export type OlsSaturation = 'hill' | 'none'
export type OlsTrend = 'linear' | 'none'
export type OlsSeasonality = 'fourier' | 'dummies' | 'none'
export interface OlsYCandidate {
  object: string
  metric: string
  metricType: string
  months: number
  isMoney: boolean
  recommended: boolean
  rationale: string
}
export interface OlsYChoice {
  object: string
  metric: string
  metricType: string
  isMoney: boolean
}
export interface OlsXCandidate {
  key: string
  /** Model object (channel type) this row was screened under. */
  object?: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  metric: string
  isSpend: boolean
  pearson: number
  vif: number
  cv: number
  statVerdict: string
  recommended: boolean
  selected: boolean
  /** An earlier S2 layer rejected this indicator: shown so the human can see
   *  where it went, but never selectable. `lockedBy` is the ledger layer id. */
  locked: boolean
  lockedBy: string
  rationale: string
}
export interface OlsParams {
  adstock: number
  saturation: OlsSaturation
  hillHalf: number
  trend: OlsTrend
  seasonality: OlsSeasonality
  fourierK: number
  pricePerUnit: number | null
}
export interface OlsConfig {
  dataSource: string
  yCandidates: OlsYCandidate[]
  y: OlsYChoice[]
  xCandidates: OlsXCandidate[]
  params: OlsParams
  proposedAt: string
}

/**
 * Master Data (2.6) — the modeling feature table plus the filter funnel that
 * produced it. Mirrors backend/app/agents/data.py::assemble_master_data.
 *
 * The table itself is NOT in here: the user slices it by product × channel ×
 * region and it is fetched live (POST /master-data/table). What the artifact
 * carries is the funnel, the slicing options, and every indicator's fate.
 */
export interface LedgerVerdict {
  layer: string
  task: string
  label: string
  /** adopted | rejected | flagged | pending | inherited */
  status: string
  note: string
}
export interface MasterDataObject {
  object: string
  months: number
  features: number
  y: string
  error?: string
}
export interface FunnelLayer {
  layer: string
  task: string
  label: string
  intake: number
  rejected: number
  survivors: number
  dropped: { l4: string; indicator: string; reason: string }[]
}
export interface MasterDataDimensions {
  brand: string[]
  provinceGroup: string[]
  channelType: string[]
  channel: string[]
  grains: string[]
  indicators: string[]
}
export interface MasterDataAdopted {
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
}
export interface MasterDataRejected extends MasterDataAdopted {
  rejectedAt: string
  reason: string
  verdicts: LedgerVerdict[]
}
/** Per-object adopted row (Tab 2's per-channel breakdown) — the flat
 *  MasterDataAdopted shape plus the row's full verdict chain. */
export interface MasterDataObjectAdopted extends MasterDataAdopted {
  verdicts: LedgerVerdict[]
}
export interface MasterData {
  objects: MasterDataObject[]
  /** 2.32 sheet 1: per-indicator model granularity (渠道 scope × 区域 granularity;
   *  blank scopes = not selected into the model). */
  granularityRef?: MasterGranularityRow[]
  /** {combined, byObject} — combined is the pre-per-object rollup every
   *  reader used to get directly; byObject is each channel's own funnel. */
  funnel: { combined: FunnelLayer[]; byObject: Record<string, FunnelLayer[]> }
  dimensions: MasterDataDimensions
  adopted: MasterDataAdopted[]
  rejected: MasterDataRejected[]
  /** Per-object adopted/rejected indicators, each carrying its full verdict
   *  chain (spec §3.5) — Tab 2's per-channel breakdown. */
  byObject?: Record<string, { adopted: MasterDataObjectAdopted[]; rejected: MasterDataRejected[] }>
  note?: string
}
/** 2.32 模型颗粒度参考表 row: a factor's model granularity. */
export interface MasterGranularityRow {
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  adopted: boolean
  /** 渠道 scope (全渠道 or a channel-type list); blank when not adopted. */
  channelScope: string
  /** 区域 granularity (National or a province-group list); blank when not adopted. */
  regionScope: string
}
/** GET /master-data/data-station — the 2.32 D.Data Station sheet. */
export interface MasterDataStation {
  columns: string[]
  rows: (string | number | null)[][]
  rowCount: number
  truncated: boolean
}
/** One live slice of the master feature table (POST /master-data/table). */
export interface MasterTable {
  columns: string[]
  rows: (string | number | null)[][]
  kpi: string
  grain?: string
  truncated: boolean
  rowCount: number
  colCount: number
  note?: string
}
export interface MasterTableQuery {
  brand?: string[]
  provinceGroup?: string[]
  channelType?: string[]
  channel?: string[]
  indicators?: string[]
  grain?: string
}

/** GET /indicator-ledger — every indicator's fate across the six S2 layers. */
export interface IndicatorLedgerRow {
  /** Model object (channel type) this row was screened under. Present only on the
   *  per-object `rowsByObject` rows; undefined on the collapsed `rows`. */
  object?: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  adopted: boolean
  rejectedAt: string
  reason: string
  verdicts: LedgerVerdict[]
}
export interface IndicatorLedger {
  layers: { layer: string; task: string; label: string }[]
  rows: IndicatorLedgerRow[]
  /** Per-Channel-Type verdicts (additive); the collapsed `rows` stays one-per-indicator. */
  rowsByObject?: Record<string, IndicatorLedgerRow[]>
  funnel: FunnelLayer[]
  adopted: number
  rejected: number
}

export type ArtifactBody =
  | SheetData | SlidesData | DocData | ReviewData | ValidationReviewData | OlsTreeData | MasterData

export interface ArtifactBlueprint {
  id: string
  /** UI display name — English (product language) */
  name: string
  /** Task number that produces it, e.g. "1.21" */
  taskRef: string
  type: ArtifactType
  stage: StageId
  /** Upstream artifact ids (lineage) */
  lineage: string[]
  /** Document kind — picks the canvas renderer */
  format: ArtifactFormat
  /** Structured body for sheet/slides/doc; markdown uses `content` */
  body?: ArtifactBody
  /** Markdown fallback / preview text — may contain Chinese content */
  content: string
  /** Deliverable template the consultant can download/send */
  exportable?: boolean
  /** Input / working material, not a stage deliverable — hidden from the deliverables column */
  internal?: boolean
}

export interface ArtifactInstance extends ArtifactBlueprint {
  version: number
  state: ArtifactState
  producedByAgent: AgentId
  producedAtTick: number
  /** Set when a person edits the content on the canvas (directly or via chat) */
  editedAtTick?: number
}

/* ── Suggested changes (internal: Proposal, 08 §3) ─────── */

export interface DiffLine {
  kind: 'add' | 'remove' | 'keep'
  text: string
}

export interface ProposalBlueprint {
  id: string
  targetArtifactId: string
  /** English headline */
  title: string
  /** What/why — may quote Chinese content */
  summary: string
  diff: DiffLine[]
  /** Evidence references shown to the user */
  evidence: EvidenceRef[]
  confidence: number
  sourceAgent: AgentId
  sourceMode: 'pipeline' | 'assistant'
  /** Appears once this task is done */
  afterTask: string
}

export type ProposalStatus = 'open' | 'accepted' | 'dismissed'

export interface ProposalRuntime {
  status: ProposalStatus
  decidedAtTick?: number
}

/* ── Decisions (internal: Gate, 08 §8) ─────────────────── */

export interface EvidenceRef {
  artifactId: string
  note?: string
}

export interface DecisionOption {
  id: string
  label: string
  detail: string
  /** What happens if chosen */
  consequence: string
  recommended?: boolean
}

export type DecisionKind = 'approval' | 'choice' | 'signoff'

export interface DecisionBlueprint {
  id: string
  kind: DecisionKind
  title: string
  question: string
  evidence: EvidenceRef[]
  recommendation: string
  options: DecisionOption[]
  /** Task re-opened when the blocking option is chosen */
  reworkTaskId?: string
  /** Option id that triggers rework instead of completing */
  reworkOptionId?: string
}

export type DecisionStatus = 'idle' | 'open' | 'resolved'

export interface DecisionRuntime {
  status: DecisionStatus
  openedAtTick?: number
  resolution?: {
    optionId: string
    note: string
    decidedAtTick: number
  }
}

/* ── AI findings (internal: InsightCard, 08 §5) ────────── */

export type InsightKind = 'connection' | 'gap' | 'conflict' | 'reference'

export interface InsightAction {
  kind: 'create_task' | 'client_question' | 'open_asset'
  label: string
  artifactId?: string
}

export interface InsightBlueprint {
  id: string
  kind: InsightKind
  title: string
  finding: string
  evidence: EvidenceRef[]
  confidence: number
  actions: InsightAction[]
  afterTask: string
}

export type InsightStatus = 'new' | 'actioned' | 'dismissed'

export interface InsightRuntime {
  status: InsightStatus
  surfacedAtTick?: number
}

/* ── Human input assignments (internal; UI: "Your input") ─ */

export type AssignmentKind = 'upload' | 'form' | 'export'

export interface AssignmentBlueprint {
  id: string
  kind: AssignmentKind
  title: string
  /** What the person needs to provide (may be Chinese) */
  prompt: string
  /** Mock attachment chips the person "provides" */
  items: string[]
  /** Label on the submit control */
  submitLabel: string
  /** Project-Folder category this upload feeds (for upload assignments). */
  category?: FileCategory
  /** When true, real parsed files must exist in `category` before submit; the
   *  gate stays blocked otherwise (S1 deliverables have no reference fallback). */
  requiresUpload?: boolean
  /** When true (data gate 2.1), the data-request manifest must report every L3
   *  slot validated (per-L3 coverage) before submit, not just any file present. */
  requiresManifest?: boolean
  /** When true (data gate 2.1, Data-Engine path), every active factor-tree
   *  indicator must be mapped to a published data asset or explicitly ignored
   *  before submit. Combined with `requiresManifest`: either path clears the gate. */
  requiresMapping?: boolean
  /** Optional source-choice gate (e.g. 1.1a factor-tree origin). When present the
   *  UI shows `choiceOptions`; the option whose id is the upload option requires a
   *  real file in `choiceUploadCategory` before the gate clears. */
  choicePrompt?: string
  choiceOptions?: AssignmentChoiceOption[]
  choiceUploadCategory?: FileCategory
}

/** One option in an assignment source-choice gate. */
export interface AssignmentChoiceOption {
  id: string
  label: string
  detail?: string
  recommended?: boolean
}

export type AssignmentStatus = 'idle' | 'open' | 'submitted'

export interface AssignmentRuntime {
  status: AssignmentStatus
  submittedAtTick?: number
  note?: string
  /** The picked source-choice option id (source-choice gates only). */
  chosenSource?: string
}

/* ── AI cognitive options (non-blocking; AI picks, human can switch) ── */

export interface AiOption {
  id: string
  label: string
  /** Why the AI would pick this */
  rationale: string
  /** What you give up by picking it */
  tradeoff: string
  recommended?: boolean
}

export interface AiOptionSet {
  id: string
  /** What the AI is choosing between (may be Chinese) */
  prompt: string
  options: AiOption[]
}

export interface AiChoiceRuntime {
  chosenId: string
  decidedAtTick: number
}

/* ── Tasks ─────────────────────────────────────────────── */

export interface TaskBlueprint {
  /** Checklist number, e.g. "1.21" — shown in UI as reference code */
  id: string
  name: string
  agent: AgentId
  stage: StageId
  class: AutomationClass
  /** English summary of what the step does */
  summary: string
  /** How the step is actually executed (method / approach) */
  how: string
  /** What it draws on beyond its upstream artifacts (knowledge basis) */
  basisNote?: string
  /** Working note shown while running (may quote Chinese content) */
  workNote: string
  dependsOn: string[]
  duration: number
  produces: string[]
  /** A task carries at most one human touchpoint */
  decision?: DecisionBlueprint
  assignment?: AssignmentBlueprint
  /** AI cognitive alternatives the step weighed — non-blocking, switchable */
  aiOptions?: AiOptionSet
  /**
   * Structured input panel rendered inside this Process step (mirrors how
   * `decision`/`assignment` are declared). The id maps to a component —
   * the 2.5 setup steps use 'ols-y' | 'ols-x' | 'ols-params'.
   */
  panel?: TaskPanelKind
}

/** Panels a Process step can render inline (see components/project/ols/). */
export type TaskPanelKind =
  | 'ols-y' | 'ols-x' | 'ols-params' | 'quality-review' | 'stat-review' | 'anomaly-review'

/**
 * 2.3a anomaly review — the AI hypothesizes a cause per detected anomaly and
 * proposes a handling; the human rules. Mirrors backend AnomalyHypothesis.
 * An accepted handling reaches the fit (event dummy / response capping /
 * caveat); pending and rejected cards do nothing.
 */
export type AnomalyHandling = 'event' | 'cap' | 'raw'
export type AnomalyStatus = 'pending' | 'accepted' | 'rejected'
export interface AnomalyHypothesis {
  id: string
  channel: string
  year: string
  growthPct: number
  hypothesis: string
  proposed: AnomalyHandling
  rationale: string
  tradeoff: string
  status: AnomalyStatus
  handling: AnomalyHandling
  note: string
  /** yyyymm, inclusive — the window the handling applies to. */
  start: number
  end: number
}
export interface AnomalyReview {
  rows: AnomalyHypothesis[]
}

/** What this task needs from a person, if anything */
export function taskNeed(task: TaskBlueprint): 'decision' | 'input' | null {
  if (task.decision) return 'decision'
  if (task.assignment) return 'input'
  return null
}

export interface TaskRuntime {
  status: TaskStatus
  progress: number
  startedTick?: number
  finishedTick?: number
  runs: number
}

/* ── Task detail: process trace + grounded findings ────── */

/** One concrete sub-step in a task's run trace */
export interface TaskStep {
  label: string
  /** Optional one-line detail (may be Chinese) */
  detail?: string
}

/** A grounded result tied to its evidence */
export interface TaskFinding {
  /** The conclusion (may be Chinese) */
  text: string
  evidence?: EvidenceRef[]
  /** flag = needs attention (conflict / gap / anomaly) */
  tone?: 'info' | 'flag'
}

/* ── Activity stream ───────────────────────────────────── */

export type SimEventType =
  | 'task_start'
  | 'task_done'
  | 'artifact'
  | 'decision_open'
  | 'decision_resolved'
  | 'suggestion'
  | 'finding'
  | 'info'
  | 'tool'

export interface SimEvent {
  id: number
  tick: number
  agent: AgentId
  taskId?: string
  type: SimEventType
  message: string
}

/* ── Tools ─────────────────────────────────────────────── */

export type ToolCategory = 'quality' | 'statistical' | 'model'
export type ToolStatus = 'running' | 'ok' | 'error'

/** A registered analysis tool — the catalog entry in the Tools module. */
export interface ToolSpec {
  id: string
  name: string
  category: ToolCategory
  description: string
  inputSummary: string
  outputSummary: string
  wraps: string
  usedBy: string[]
  version: string
}

/** Where a tool's implementation lives, plus its real source code. */
export interface ToolSource {
  module: string
  path: string
  symbol: string
  line: number
  code: string
}

/** One way to reach a tool over the API. */
export interface ToolApiCall {
  method: string
  path: string
  note: string
  example: string
}

/** The full tool page: scenario, method, decision bands, source, API surface. */
export interface ToolDetail extends ToolSpec {
  scenario: string
  method: string
  logic: string[]
  /** [name, value, meaning] */
  params: string[][]
  source: ToolSource | null
  api: ToolApiCall[]
}

/** One explicit tool call recorded while a task ran. */
export interface ToolInvocation {
  id: string
  toolId: string
  toolName: string
  category: ToolCategory
  taskId: string
  argsSummary: string
  resultSummary: string
  status: ToolStatus
  startedTick: number
  startedAt: string
  finishedAt: string
  durationMs: number | null
  error: string
}

/* ── Assistant ─────────────────────────────────────────── */

/**
 * An object the user pinned as the subject of a question.
 *
 * `payload` carries the `ValidationSeriesRequest` that produced a chart, so the
 * backend re-resolves the rows itself instead of trusting numbers from the client.
 */
export interface ChatMention {
  kind: 'chartTable' | 'chartAnalysis' | 'artifact'
  refId: string
  label: string
  payload?: Record<string, unknown>
}
/** One `@`-mentionable object, from `GET /mentionables`. */
export interface Mentionable {
  kind: ChatMention['kind']
  refId: string
  label: string
  group: string
}
export interface AssistantTurn {
  role: 'user' | 'assistant'
  text: string
  evidence?: EvidenceRef[]
  /** What the user pinned on this turn — re-rendered as chips on reload. */
  mentions?: { kind: ChatMention['kind']; refId: string; label: string }[]
}

/** A drafted-but-unapplied chat edit to an artifact (preview-then-confirm). */
export interface ArtifactEditProposal {
  artifactId: string
  /** 'model' edits a backing domain model; 'free' rewrites body/content directly. */
  kind: 'free' | 'model'
  format: ArtifactFormat
  summary: string
  /** Proposed new structured body (sheet/slides/doc/review) — preview + apply. */
  body?: ArtifactBody | null
  /** Proposed new markdown content (format === 'markdown'). */
  content?: string
  /** Revised backing domain model JSON (kind === 'model'), applied server-side. */
  model?: Record<string, unknown> | null
}

export interface AssistantScriptEntry {
  /** Keywords that trigger this canned answer */
  match: string[]
  answer: string
  evidence?: EvidenceRef[]
}

/* ── Project registry ──────────────────────────────────── */

import type { IndustryRef } from './industries'

export type { IndustryRef }

/** Lightweight project-registry record — mirrors backend ProjectMeta. */
export interface ProjectMeta {
  id: string
  name: string
  brand: string
  industry: IndustryRef
  kpi: string
  createdAt: string
  updatedAt?: string
}

/** A registry entry augmented with live run status for the landing list. */
export interface ProjectListItem extends ProjectMeta {
  status: 'draft' | 'running' | 'blocked' | 'complete'
  tasksDone: number
  tasksTotal: number
}

/* ── Project Folder (uploaded source files) ─────────────── */

export type FileCategory =
  | 'project_background'
  | 'industry_reference'
  | 'interview_minutes'
  | 'factor_tree'
  | 'data'
  | 'raw_data'
  | 'other'

/** A user-uploaded file stored in the per-project folder — mirrors backend ProjectFile. */
export type AsrStatus = '' | 'pending' | 'transcribing' | 'done' | 'error'

export interface ProjectFile {
  id: string
  category: FileCategory
  filename: string
  size: number
  contentType: string
  uploadedAt: string
  parsed: boolean
  parseChars: number
  parseError?: string
  slot?: string | null
  /** ASR transcription status for interview audio uploads ('' when not audio). */
  asrStatus?: AsrStatus
  asrError?: string | null
}

/** Data-request upload manifest — the BU-derived L3 directory. */
export type DataSlotStatus = 'pending' | 'uploaded' | 'incomplete' | 'validated' | 'error'

export interface DataRequestSlot {
  l3: string
  expectedL4s: string[]
  expectedIndicators: number
  status: DataSlotStatus
  fileId?: string | null
  filename: string
  coveredIndicators: number
  missingL4s: string[]
  missingIndicators: string[]
}

export interface DataRequestManifest {
  slots: DataRequestSlot[]
  total: number
  validated: number
  timeGranularity: string
  scopeDims: string[]
}

/** Display metadata for the folder's category sections. */
export interface FileCategoryMeta {
  id: FileCategory
  label: string
  hint: string
}

/** Interview Recordings accept audio (transcribed by the ASR step) plus text minutes. */
export const INTERVIEW_ACCEPT = '.mp3,.wav,.m4a,.aac,.ogg,.flac,.mp4,.webm,.docx,.md,.txt,.pdf'

export const FILE_CATEGORIES: FileCategoryMeta[] = [
  { id: 'project_background', label: 'Project Background', hint: 'SOW, brief, kickoff deck' },
  { id: 'industry_reference', label: 'Industry Reference', hint: 'Category & competitor research' },
  { id: 'interview_minutes', label: 'Interview Recordings', hint: 'Audio (.mp3/.wav/.m4a) — auto-transcribed — or text minutes' },
  { id: 'factor_tree', label: 'Factor Tree', hint: 'Your own factor-tree workbook (L1–L4 + indicators)' },
  { id: 'data', label: 'Data', hint: 'Data-request feedback & datasets' },
  { id: 'other', label: 'Other', hint: 'Anything else worth keeping' },
]

/* ── Project Profile (parsed + editable framing) ────────── */

export type TimeGranularity = 'Year' | 'Month' | 'Week'

export interface ModelScopeDimension {
  name: string
  values: string[]
}

export interface ModelScope {
  dimensions: ModelScopeDimension[]
  rows: string[][]
}

export interface ProjectProfile {
  projectIntro: string
  timeGranularity: TimeGranularity
  modelScope: ModelScope
  sourceOrigin: string
}

/* ── Global model-service configuration (LLM + ASR) ──────
 * ONE config shared by every project. Holds the ACTUAL credentials the user
 * enters once in Settings — the real API key, base URL, and model name (not an
 * env-var reference). Persisted server-side in data/model_service.json. */
export interface ServiceCreds {
  apiKey: string
  baseUrl: string
  model: string
}

export interface GlobalModelConfig {
  llm: ServiceCreds
  asr: ServiceCreds
}

/** Greyed placeholders shown in the Settings fields — hints only, never saved. */
export const MODEL_PLACEHOLDERS = {
  llm: { baseUrl: 'https://ark.cn-beijing.volces.com/api/coding/v3', model: 'ark-code-latest' },
  asr: { baseUrl: 'https://api.openai.com/v1', model: 'whisper-1' },
} as const

export function emptyModelConfig(): GlobalModelConfig {
  return {
    llm: { apiKey: '', baseUrl: '', model: '' },
    asr: { apiKey: '', baseUrl: '', model: '' },
  }
}

/** The LLM is "configured" once the key, base URL, and model are all filled. */
export function isLlmConfigured(cfg: GlobalModelConfig | null | undefined): boolean {
  return !!(cfg && cfg.llm.apiKey && cfg.llm.baseUrl && cfg.llm.model)
}

/* ── Factor tree (per-project, with per-node confirm) ───── */

export type FactorSource = 'template' | 'ai' | 'interview' | 'manual' | 'upload'
export type FactorStatus = 'baseline' | 'proposed' | 'accepted' | 'rejected'

export interface FactorRow {
  id: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  /** Dimensions the indicator is measured by (e.g. "by brand, by product"); defaults from the project profile's model scope. Free text, comma-separated. */
  dimension: string
  source: FactorSource
  status: FactorStatus
  rationale: string
  evidence: string
}

export interface FactorTree {
  rows: FactorRow[]
}

// ── Data quality scorecard (S2 · per-metric, editable disposition) ──
export type QualityDisposition = 'accept' | 'flag' | 'drop'

/** One 2.11 subcheck under a dimension — the driver behind a dimension score. */
export interface QualitySubScore {
  key: string // e.g. "consistency.time"
  dimension: string // consistency | accuracy | completeness | granularity
  label: string
  score: number // 0 / 0.5 / 1
  note: string
  computed: boolean // false = advisory default (needs external reference)
  blocking: boolean // whether it can drag the dimension score down
}

export interface QualityRow {
  id: string
  /** Model object (channel type) this row was screened under. */
  object?: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  consistency: number
  accuracy: number // authenticity / numeric+business accuracy
  completeness: number
  granularity: number
  // Per-dimension narratives (Excel 2.12 "...情况" columns), AI-written.
  consistencyNote?: string
  accuracyNote?: string
  completenessNote?: string
  granularityNote?: string
  // The 10-subcheck breakdown behind the four dimension scores.
  subScores?: QualitySubScore[]
  total: number // Excel 2.12 Total = product of the four dimensions
  autoVerdict: string // pass | borderline | unusable
  disposition: QualityDisposition
  note: string
}

export interface QualityScorecard {
  rows: QualityRow[]
}

// ── Statistical score (S2 · 2.4 · per-indicator CV/Pearson/VIF) ──
export type StatDisposition = 'include' | 'review' | 'drop'

export interface StatScoreRow {
  id: string
  /** Model object (channel type) this row was screened under. */
  object?: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  cv: number // reference CV (scaled variance / mean)
  pearson: number // Pearson r vs KPI (signed)
  vif: number // variance inflation factor
  cvScore: number // 0 / 0.5 / 1
  pearsonScore: number
  vifScore: number
  total: number // cvScore * pearsonScore * vifScore
  autoVerdict: string // Good | Acceptable | unconsiderable
  disposition: StatDisposition
  note: string
}

export interface StatScorecard {
  rows: StatScoreRow[]
}

/* ── Knowledge packs (per-industry, editable) ───────────── */

/** Sentinel industry code for cross-industry (general) knowledge. */
export const GENERAL_INDUSTRY = 'general'

/** A pack section. factor_tree/interview/rules/industry_knowledge are industry-scoped;
 *  general_knowledge is cross-industry (industryL1 === GENERAL_INDUSTRY). */
export type TemplateKind =
  | 'factor_tree'
  | 'interview'
  | 'rules'
  | 'industry_knowledge'
  | 'general_knowledge'
export type InterviewCategory = 'Leadership' | 'Management' | 'Operation' | 'Data'
export type RuleCategory = 'quality' | 'statistical' | 'technical' | 'business'
export type RuleSeverity = 'block' | 'warn' | 'info'

export interface FactorTreeRow {
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  /** Expected post-OLS ROI band, e.g. "0.8~1.3" or "/" (N/A). Matched against the fitted ROI. */
  roiRange: string
  /** Expected yearly contribution band, e.g. "-5%~5%". Matched against the fitted contribution. */
  contributionRange: string
}

export interface InterviewQuestion {
  category: InterviewCategory
  role: string
  question: string
}

/** One reusable validation/business rule (S2 quality / statistical / technical). */
export interface RuleRow {
  id: string
  category: RuleCategory
  name: string
  detail: string
  severity: RuleSeverity
}

/** One free-form knowledge note — industry know-how or general method/style. */
export interface KnowledgeNote {
  id: string
  title: string
  body: string
  tags: string[]
}

/** One reusable, editable section of an industry knowledge pack — mirrors backend. */
export interface KnowledgeTemplate {
  id: string
  kind: TemplateKind
  name: string
  industryL1: string
  industryL2?: string
  version: number
  builtin: boolean
  factorRows: FactorTreeRow[]
  interviewQuestions: InterviewQuestion[]
  ruleRows: RuleRow[]
  knowledgeNotes: KnowledgeNote[]
  updatedAt: string
}

/* ── Change ledger (per-project audit trail; lives in project state) ── */

export interface LedgerEntry {
  id: string
  action: 'add' | 'remove' | 'merge'
  target: string
  reason: string
  source: 'interview' | 'report' | 'ai' | 'stats'
  confirmedBy: string
  /** Day index, or undefined for pre-seeded */
  day?: number
}

/* ── Data Engine (raw → review → clean → publish data asset) ── */

export type DataAssetStatus = 'raw' | 'reviewed' | 'published'

/** One discovered raw table (a sheet or CSV) inside a registered source file. */
export interface RawTable {
  name: string
  fileId: string
  filename: string
  rowCount: number
  columns: string[]
}

/** Per-column quick-review profile — mirrors backend FieldProfile. */
export interface FieldProfile {
  name: string
  table: string
  dtype: string // number | integer | text | date | datetime | boolean | empty
  nonNull: number
  nullRatio: number
  distinct: number
  sampleValues: string[]
  /** full distinct values for low-cardinality text fields (enum candidates) */
  enumValues: string[]
  min?: number | null
  max?: number | null
  mean?: number | null
  std?: number | null
  cv?: number | null // volatility = std / |mean|
  negatives: number
  isTimeAxis: boolean
  timeGranularity?: string | null // day | week | month | quarter | year
  continuity?: number | null // fraction of present periods over span [0,1]
  gapCount?: number | null
  note: string
}

/** Quick-review output: per-field profiles + charts (reuse ReviewChart renderer). */
/** Review of ONE raw table — its own fields, charts, time axis, warnings. */
export interface TableReview {
  name: string
  rowCount: number
  columnCount: number
  fields: FieldProfile[]
  charts: ReviewChart[]
  timeField?: string | null
  timeGranularity?: string | null
  warnings: string[]
}

export interface ReviewReport {
  rowCount: number
  columnCount: number
  tables: RawTable[]
  fields: FieldProfile[]
  tableReviews: TableReview[]
  charts: ReviewChart[] // deprecated global charts; use tableReviews[].charts
  timeField?: string | null
  timeGranularity?: string | null
  warnings: string[]
  generatedAt: string
}

export type CleaningTransform = 'passthrough' | 'mapping' | 'transform' | 'calc' | 'hardcode' | 'drop'
export type NaPolicy = 'keep' | 'drop' | 'zero' | 'na'

/** One row of the vertical cleaning-spec editor — mirrors backend FieldRule. */
export interface FieldRule {
  id: string
  sourceField: string
  targetColumn: string
  transform: CleaningTransform
  rule: string
  naPolicy: NaPolicy
  dtype: string
  masterDataRef?: string | null
  enabled: boolean
}

export interface CleaningSpec {
  rules: FieldRule[]
  targetSchema: string[]
  note: string
}

/** An AI-drafted (human-editable) DuckDB cleaning query + its last preview. */
export interface SqlDraft {
  sql: string
  status: 'draft' | 'ok' | 'error'
  error: string
  previewColumns: string[]
  previewRows: string[][]
  rowCount: number
  generatedAt: string
}

export interface DataAssetVersion {
  version: number
  parquetPath: string
  rowCount: number
  columns: string[]
  sql: string
  producedAt: string
}

/** One dbt node result (model / seed / test) from the last build. */
export interface DbtNode {
  uniqueId: string
  resourceType: string // model | seed | test
  name: string
  layer: string // staging | intermediate | marts (models only)
  status: string // success | error | pass | fail | skipped
  executionTime: number
  message: string
  failures?: number | null
  relation: string
}

export interface EnumViolation {
  column: string
  values: string[]
}

/** Strict field + enum mapping of the mart against the target schema. */
export interface SchemaConformance {
  ok: boolean
  checked: boolean
  missingRequired: string[]
  extra: string[]
  enumViolations: EnumViolation[]
  unenforcedDimensions: string[]
}

/** Summary of an asset's last `dbt build` — the dbt-workspace transform path. */
export interface DbtSummary {
  ok: boolean
  ranAt: string
  command: string
  error: string
  mart: string
  models: number
  tests: number
  passed: number
  failed: number
  aiRounds: number
  nodes: DbtNode[]
  /** pipeline step id → compiled dbt model name (per-step status + preview) */
  stepModels: Record<string, string>
  conformance?: SchemaConformance | null
}

/** A project-scoped data asset — mirrors backend DataAsset. */
export interface DataAsset {
  id: string
  name: string
  status: DataAssetStatus
  description: string
  sourceFileIds: string[]
  rawTables: RawTable[]
  review?: ReviewReport | null
  cleaningSpec?: CleaningSpec | null
  sqlDraft?: SqlDraft | null
  pipeline?: TransformPipeline | null
  dbt?: DbtSummary | null
  versions: DataAssetVersion[]
  latestVersion: number
  lineage: string[]
  createdAt: string
  updatedAt: string
}

export interface DbtModelFile {
  layer: string
  name: string
  sql: string
  description: string
}

export interface DbtSeed {
  name: string
  columns: string[]
  csv: string
}

/** One readable raw table an asset's uploads produced. */
export interface RawSourceTable {
  name: string
  filename: string
  fileId: string
  sheet: string
  /** Origin label stamped onto every row this table produces (the `source` column). */
  sourceLabel: string
  rowCount: number
  columns: string[]
}

/** A registered file that produced no table, and why — so an upload that never
 *  appeared in the editor can explain itself instead of being silently absent. */
export interface RawSourceIssue {
  fileId: string
  filename: string
  reason: string
}

export interface DbtWorkspaceInfo {
  available: boolean
  message: string
  models: DbtModelFile[]
  /** Raw table names, derived from the uploaded files (not from a dbt build). */
  sources: string[]
  sourceTables: RawSourceTable[]
  sourceIssues: RawSourceIssue[]
  seeds: DbtSeed[]
}

/** Distinct values of one column as they reach a step, most frequent first. */
export interface ColumnValuesResult {
  ok: boolean
  error: string
  values: [string, number][]
}

export interface DbtPreview {
  columns: string[]
  rows: string[][]
  rowCount: number
}

/** Per-column profile rendered in the preview grid's header. */
export interface ColumnStat {
  name: string
  type: string
  nullPct: number
  distinct: number
  min: string
  max: string
  top: [string, number][]   // value counts, categorical columns only
  histogram: number[]       // equal-width buckets, numeric columns only
}

/** Sandbox run of the pipeline prefix ending at one step — the editor's fast path. */
export interface StepPreview {
  ok: boolean
  error: string
  columns: string[]
  rows: string[][]
  rowCount: number
  stats: ColumnStat[]
}

/** Raw spellings that key-collision clustering judges to be the same value. */
export interface ValueCluster {
  key: string
  method: 'fingerprint' | 'ngram'
  suggestion: string
  rows: number
  values: [string, number][]
}

export interface ClusterResult {
  ok: boolean
  error: string
  values: number
  clusters: ValueCluster[]
}

// ── Transform pipeline (Data Engine) ──
export type StepKind =
  | 'field_map' | 'enum_map' | 'join' | 'union'
  | 'aggregate' | 'filter' | 'derive' | 'custom_sql'

export interface FieldMapEntry {
  source: string
  target: string
  cast: string // '' | integer | double | date | text
  expr: string
  /** Who decided this row — AI rows apply directly but are marked for review. */
  by: 'ai' | 'human'
}

/** Columns available at a step (field-map / custom-SQL grounding). */
export interface InputColumnsResult {
  ok: boolean
  error: string
  columns: string[]
}

/** AI-matched source→target column mappings, merged over human rows. */
export interface FieldMapSuggestion {
  ok: boolean
  error: string
  entries: FieldMapEntry[]
}

/** A custom_sql body drafted from plain English (already sandbox-validated). */
export interface SqlSuggestion {
  ok: boolean
  error: string
  sql: string
}

/** The transform pipeline compiled to one statement (Publish → export). */
export interface CompiledSql {
  ok: boolean
  error: string
  sql: string
}

/** Result of an AI enum-mapping pass — entries merged over the step's own decisions. */
export interface EnumSuggestion {
  ok: boolean
  error: string
  entries: EnumMapEntry[]
}

export interface EnumMapEntry {
  raw: string
  canonical: string
  confidence: number
  by: 'ai' | 'human'
  /** Only 'accepted' rows are compiled; 'proposed' awaits human confirmation. */
  status: 'accepted' | 'proposed'
}

export interface JoinConfig {
  how: 'left' | 'inner'
  leftOn: string[]
  rightOn: string[]
  rightColumns: string[]
}

export interface AggSpec {
  column: string
  func: 'sum' | 'avg' | 'min' | 'max' | 'count'
  alias: string
}

export interface DeriveSpec {
  name: string
  expr: string
}

export interface TransformStep {
  id: string
  kind: StepKind
  name: string
  note: string
  inputs: string[] // 'source:<table>' or step ids
  fieldMap: FieldMapEntry[]
  enumField: string
  /** Target-schema column supplying the standard values this field maps onto. */
  enumTarget: string
  enumMap: EnumMapEntry[]
  join?: JoinConfig | null
  groupBy: string[]
  aggs: AggSpec[]
  filterExpr: string
  derive: DeriveSpec[]
  sql: string
}

export interface TransformPipeline {
  steps: TransformStep[]
  outputStep: string
  note: string
}

export type TargetColumnKind = 'dimension' | 'time' | 'factor' | 'metric' | 'value'

export interface TargetColumn {
  name: string
  label: string
  definition: string
  kind: TargetColumnKind
  required: boolean
  standardValues: string[]
  /** Engine-owned (e.g. `source`): written automatically, cannot be renamed or removed. */
  system?: boolean
}

/** FND-001 · semantic type of an indicator (what kind of number it is). */
export type MetricType =
  | 'kpi_volume' | 'kpi_value' | 'spending' | 'count' | 'rate' | 'index' | 'other'
export type Aggregation =
  | 'sum' | 'count' | 'average' | 'min' | 'max' | 'distinct_count' | 'weighted_average'
export type IndicatorSource =
  | 'project_material' | 'interview' | 'uploaded_tree' | 'template' | 'ai' | 'data_upload'

export interface Indicator {
  id: string
  metric: string
  /** OLS model role: 'Y' | 'spending' | 'X'. */
  metricType: string
  l1: string
  l2: string
  l3: string
  l4: string
  /** FND-001 · full factor path (L5–L8 complete the L1–L8 lineage). */
  l5?: string
  l6?: string
  l7?: string
  l8?: string
  unit: string
  /** FND-001 · semantic metadata. */
  semanticType?: MetricType
  currency?: string | null
  aggregation?: Aggregation
  numberFormat?: string
  source?: IndicatorSource
  ruleVersion?: string
  assetId: string
  assetName: string
  coverageStart: string
  coverageEnd: string
  rows: number
  /** matched a Business-Understanding factor-tree row */
  treeGrounded: boolean
  treeRowId: string
}

/** One active factor-tree row's mapping status against the published data assets. */
export type FactorMapStatus = 'mapped' | 'ignored' | 'pending'

/**
 * An AI-proposed indicator for a pending factor row (2.1). The score is
 * deterministic (name overlap · path proximity · unit · coverage); only the
 * reason is AI-written. Accepting one binds it via PUT /factor-map/bind.
 */
export interface FactorMapSuggestion {
  indicatorId: string
  metric: string
  assetId: string
  assetName: string
  unit: string
  coverageStart: string
  coverageEnd: string
  /** 0–1; higher is a closer match. */
  score: number
  reason: string
}

export interface FactorMapRow {
  rowId: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  status: FactorMapStatus
  assetId: string
  assetName: string
  metric: string
  coverageStart: string
  coverageEnd: string
  ignoreNote: string
  /** Model role the user maintains in 2.1: 'Y' response / 'X' driver / 'excluded'. */
  metricType: MetricRole
  /** How the indicator rolls up over time/dimensions. */
  aggregation: string
  /** Ranked proposals, best first. Empty for mapped rows and for rows with no
   *  candidate above the suggestion threshold. */
  suggestions: FactorMapSuggestion[]
}

export type MetricRole = 'Y' | 'X' | 'excluded'

/**
 * The 2.1 gate verdict, decided by the backend (`app/agents/intake_status.py`).
 *
 * The UI renders `ready` and `blockers` directly and must NOT re-derive
 * readiness from Project-Folder file counts: the two rules disagreed, and a
 * project that had resolved its whole factor map in the Data Engine stayed
 * blocked in the UI forever because its raw uploads live under `raw_data`.
 */
export interface DataIntakeStatus {
  ready: boolean
  /** Which rule cleared the gate: 'mapping' | 'manifest' | 'upload' | 'none'. */
  path: string
  total: number
  mapped: number
  ignored: number
  pending: number
  /** Human-readable reasons the gate is shut. Empty when `ready`. */
  blockers: string[]
}

export interface FactorMap {
  rows: FactorMapRow[]
  total: number
  mapped: number
  ignored: number
  pending: number
  /** How many pending rows the AI could propose a match for. */
  suggested: number
  /** true when total > 0 and pending === 0 — the mapping path is resolved. */
  complete: boolean
  /** The gate verdict. `complete` only covers the mapping path; this also
   *  accounts for the legacy manifest path and modeling readiness. Optional:
   *  legacy artifact bodies predate this field. */
  intake?: DataIntakeStatus
}

export type MasterDataKind = 'product' | 'geo' | 'channel' | 'time'

export interface MasterDataMapRow {
  source: string
  target: string
}

export interface MasterDataMap {
  id: string
  kind: MasterDataKind
  name: string
  rows: MasterDataMapRow[]
}

/** FND-002 · a comparable-period definition, reused by Business Validation + Reporting. */
export type TimeWindowPeriod =
  | 'year' | 'half_year' | 'quarter' | 'month' | 'ytd' | 'rolling' | 'custom'
export type TimeComparison = 'none' | 'yoy' | 'pop' | 'custom'

export interface TimeWindow {
  id: string
  name: string
  periodType: TimeWindowPeriod
  /** inclusive 'YYYY-MM' bounds */
  currentStart: string
  currentEnd: string
  comparisonType: TimeComparison
  comparisonStart: string
  comparisonEnd: string
  rollingMonths: number
  version: number
}
