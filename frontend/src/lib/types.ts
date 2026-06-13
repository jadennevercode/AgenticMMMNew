/**
 * Domain types — aligned with docs/agent-design/08-product-architecture-v2.md.
 * Internal architecture terms (Proposal, AutomationClass, …) are allowed in code
 * identifiers but must NEVER appear in UI copy — see ui-language.ts (decision D4).
 */

export type AgentId = 'control' | 'business' | 'data' | 'model' | 'report'

export type StageId = 's1' | 's2' | 's3' | 's4' | 's5'

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
  /** Body — may contain Chinese client/business content (content language) */
  content: string
  /** Deliverable template the consultant can download/send */
  exportable?: boolean
}

export interface ArtifactInstance extends ArtifactBlueprint {
  version: number
  state: ArtifactState
  producedByAgent: AgentId
  producedAtTick: number
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
}

export type AssignmentStatus = 'idle' | 'open' | 'submitted'

export interface AssignmentRuntime {
  status: AssignmentStatus
  submittedAtTick?: number
  note?: string
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

export interface SimEvent {
  id: number
  tick: number
  agent: AgentId
  taskId?: string
  type: SimEventType
  message: string
}

/* ── Assistant ─────────────────────────────────────────── */

export interface AssistantTurn {
  role: 'user' | 'assistant'
  text: string
  evidence?: EvidenceRef[]
}

export interface AssistantScriptEntry {
  /** Keywords that trigger this canned answer */
  match: string[]
  answer: string
  evidence?: EvidenceRef[]
}
