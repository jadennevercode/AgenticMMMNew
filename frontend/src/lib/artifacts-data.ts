import type { ArtifactBlueprint, ArtifactFormat, ArtifactType, StageId } from './types'

/**
 * Artifact blueprints — STRUCTURE ONLY (id, name, taskRef, type, stage,
 * lineage, format). This is product design metadata, NOT runtime data: it
 * drives the deliverable graph (lib/artifact-graph.ts), the Project
 * workspace columns and cross-navigation.
 *
 * Artifact BODIES and content are produced at runtime by the backend and
 * arrive via /api/state → store.artifacts. There is no mock content here.
 */

interface RawArtifact {
  id: string
  name: string
  taskRef: string
  type: ArtifactType
  stage: StageId
  lineage: string[]
  format: ArtifactFormat
  /** Deliverable template the consultant can download/send */
  exportable?: boolean
  /** Input / working material, not a stage deliverable */
  internal?: boolean
}

const RAW: RawArtifact[] = [
  /* ── S1 · Business Understanding — 5 deliverables + inputs ───── */
  { id: 'a-sow', name: 'SOW & Brief (provided)', taskRef: '1.0a', type: 'document', stage: 's1', lineage: [], format: 'doc', internal: true },
  { id: 'a-scope', name: 'Project Profile', taskRef: '1.0', type: 'document', stage: 's1', lineage: ['a-sow'], format: 'sheet', exportable: true },
  { id: 'a-source-materials', name: 'Reports & Materials (provided)', taskRef: '1.1a', type: 'document', stage: 's1', lineage: ['a-scope'], format: 'doc', internal: true },
  { id: 'a-knowledge-package', name: 'Industry Knowledge', taskRef: '1.1', type: 'master-data', stage: 's1', lineage: ['a-source-materials', 'a-scope'], format: 'sheet', internal: true },
  { id: 'a-factor-tree', name: 'Factor Tree', taskRef: '1.21', type: 'master-data', stage: 's1', lineage: ['a-knowledge-package', 'a-source-materials'], format: 'sheet', exportable: true },
  { id: 'a-interview', name: 'Interview', taskRef: '1.3', type: 'document', stage: 's1', lineage: ['a-factor-tree', 'a-scope', 'a-source-materials', 'a-knowledge-package'], format: 'sheet', exportable: true },
  { id: 'a-data-request', name: 'Data Request', taskRef: '1.5', type: 'document', stage: 's1', lineage: ['a-factor-tree'], format: 'sheet', exportable: true },
  { id: 'a-bu-summary', name: 'Business Understanding Summary', taskRef: '1.7', type: 'report', stage: 's1', lineage: ['a-scope', 'a-factor-tree', 'a-interview', 'a-data-request'], format: 'doc', exportable: true },

  /* ── S2 · Data Intake & Quality (2.1 Validation + 2.2 Process) ── */
  { id: 'a-data-files', name: 'Collected Client Data (provided)', taskRef: '2.0a', type: 'dataset', stage: 's2', lineage: ['a-data-request'], format: 'sheet', internal: true },
  { id: 'a-validation-standard', name: 'Data Validation Standard', taskRef: '2.11', type: 'document', stage: 's2', lineage: ['a-data-files'], format: 'sheet', internal: true },
  { id: 'a-quality-scorecard', name: 'Data Quality Score', taskRef: '2.12', type: 'scorecard', stage: 's2', lineage: ['a-validation-standard', 'a-data-files'], format: 'sheet', exportable: true },
  { id: 'a-schema', name: 'Wide-table Schema', taskRef: '2.21', type: 'master-data', stage: 's2', lineage: ['a-factor-tree', 'a-quality-scorecard'], format: 'sheet', internal: true },
  { id: 'a-data-dictionary', name: 'Data Processing (TaskLog)', taskRef: '2.22', type: 'document', stage: 's2', lineage: ['a-schema', 'a-quality-scorecard'], format: 'sheet' },
  { id: 'a-data-warehouse', name: 'Data Dictionary', taskRef: '2.23', type: 'master-data', stage: 's2', lineage: ['a-data-dictionary'], format: 'sheet', internal: true },
  { id: 'a-dataset', name: 'Master Dataset', taskRef: '2.24', type: 'dataset', stage: 's2', lineage: ['a-data-warehouse', 'a-schema'], format: 'sheet' },

  /* ── S3 · Validation & Hypotheses (2.3 Data Cross-Validation) ── */
  { id: 'a-drill-framework', name: 'Business Validation Rules & Drill-down Framework', taskRef: '2.31', type: 'document', stage: 's3', lineage: ['a-dataset'], format: 'sheet' },
  { id: 'a-trend-review', name: 'Data Review Deck', taskRef: '2.32', type: 'report', stage: 's3', lineage: ['a-dataset', 'a-drill-framework'], format: 'review' },
  { id: 'a-client-qa', name: 'Client Q&A Tracker', taskRef: '2.32', type: 'workflow', stage: 's3', lineage: ['a-factor-tree', 'a-drill-framework'], format: 'sheet' },
  { id: 'a-stat-tests', name: 'Statistical Screening Results', taskRef: '2.33', type: 'scorecard', stage: 's3', lineage: ['a-dataset', 'a-trend-review'], format: 'sheet' },
  { id: 'a-model-input', name: 'Model Input', taskRef: '2.34', type: 'dataset', stage: 's3', lineage: ['a-dataset', 'a-stat-tests'], format: 'sheet' },

  /* ── S4 · Modeling ───────────────────────────────────── */
  { id: 'a-prior-register', name: 'Prior Setting Rules', taskRef: '3.1', type: 'document', stage: 's4', lineage: ['a-knowledge-package', 'a-trend-review', 'a-model-input'], format: 'sheet' },
  { id: 'a-model-candidates', name: 'Model Candidates', taskRef: '3.2', type: 'model', stage: 's4', lineage: ['a-model-input', 'a-prior-register'], format: 'sheet' },
  { id: 'a-tech-review', name: 'Technical Review', taskRef: '3.3', type: 'report', stage: 's4', lineage: ['a-model-candidates'], format: 'sheet' },
  { id: 'a-model-diagnostics', name: 'Model Diagnostics', taskRef: '3.3', type: 'report', stage: 's4', lineage: ['a-model-candidates'], format: 'review' },

  /* ── S5 · Reporting ──────────────────────────────────── */
  { id: 'a-decomp-results', name: 'Model Interpretation (5D)', taskRef: '4.1a', type: 'report', stage: 's5', lineage: ['a-tech-review'], format: 'sheet' },
  { id: 'a-final-report', name: 'Final Report', taskRef: '4.1b', type: 'report', stage: 's5', lineage: ['a-decomp-results'], format: 'slides' },
  { id: 'a-results-dashboard', name: 'Results Dashboard', taskRef: '4.1a', type: 'report', stage: 's5', lineage: ['a-decomp-results'], format: 'review' },
]

export const ARTIFACTS: ArtifactBlueprint[] = RAW.map((r) => ({
  ...r,
  // Body/content are runtime-only (backend). Blueprints carry empty content.
  content: '',
}))

export const ARTIFACT_MAP = new Map(ARTIFACTS.map((a) => [a.id, a]))
