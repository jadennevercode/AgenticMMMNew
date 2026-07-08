import type { AgentId, AgentProfile, StageId, StageProfile } from './types'

export const AGENTS: Record<AgentId, AgentProfile> = {
  control: {
    id: 'control',
    name: 'Project Control',
    role: 'Orchestration · Pace & checkpoints',
    capabilities: [
      'Task breakdown & scheduling',
      'Context sync across agents',
      'Escalation to people',
      'Full project journal',
    ],
  },
  business: {
    id: 'business',
    name: 'Business Agent',
    role: 'Strategy · Factor structure & interviews',
    capabilities: [
      'Scope drafting',
      'Factor & metric recall',
      'Key business questions',
      'Interview digestion',
    ],
  },
  data: {
    id: 'data',
    name: 'Data Agent',
    role: 'Data quality · Integration & validation',
    capabilities: [
      'Quality scoring',
      'Pipeline & data dictionary',
      'Business sense-check (6 steps)',
      'Statistical screening',
    ],
  },
  model: {
    id: 'model',
    name: 'Model Agent',
    role: 'Bayesian MMM · Diagnostics',
    capabilities: [
      'Prior registry',
      'Training & tuning',
      'Technical review (R²/MAPE/DW)',
      'Business plausibility check',
    ],
  },
  report: {
    id: 'report',
    name: 'Report Agent',
    role: 'Narrative · Charts & Q&A',
    capabilities: [
      'Decomposition & ROI charts',
      'Narrative drafting',
      'Interactive Q&A',
    ],
  },
}

export const AGENT_ORDER: AgentId[] = ['control', 'business', 'data', 'model', 'report']

export const STAGES: Record<StageId, StageProfile> = {
  s1: {
    id: 's1', index: 1, name: 'Business Understanding',
    goal: 'Scope, factor tree (L1–L4), metrics, interviews and data request',
    milestone: 'M1 · Scope, factor tree & data request confirmed',
  },
  s2: {
    id: 's2', index: 2, name: 'Data Intake & Quality',
    goal: 'Collect, score, integrate client data into one governed dataset',
    milestone: 'M2 · Data acceptance completed',
  },
  s3: {
    id: 's3', index: 3, name: 'Validation & Hypotheses',
    goal: 'Business sense-check, client sign-off, statistical screening, model input',
    milestone: 'M3 · Client sign-off & model input ready',
  },
  s4: {
    id: 's4', index: 4, name: 'Modeling',
    goal: 'Priors, training, technical and business review',
    milestone: 'M4 · Model passed both reviews',
  },
  s5: {
    id: 's5', index: 5, name: 'Reporting',
    goal: 'Standard report, narrative and interactive Q&A',
    milestone: 'M5 · Client review passed',
  },
}

export const STAGE_ORDER: StageId[] = ['s1', 's2', 's3', 's4', 's5']

export const AGENT_COLOR: Record<AgentId, string> = {
  control: 'var(--color-agent-orchestration)',
  business: 'var(--color-agent-business)',
  data: 'var(--color-agent-data)',
  model: 'var(--color-agent-model)',
  report: 'var(--color-agent-report)',
}

// Project metadata (name / brand / industry / window) is now per-project and
// comes from the backend registry — see store `activeMeta` and ProjectMeta.
