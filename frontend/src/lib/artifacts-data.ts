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

  /* ── S2 · Data Intake & Validation — six artifacts, each a filter layer:
        Processing → Quality → Business → Statistical → OLS test → Master data ── */
  { id: 'a-data-processing', name: 'Data Processing', taskRef: '2.1', type: 'dataset', stage: 's2', lineage: ['a-data-request', 'a-factor-tree'], format: 'sheet', exportable: true },
  { id: 'a-quality-scorecard', name: 'Data Quality Score', taskRef: '2.2', type: 'scorecard', stage: 's2', lineage: ['a-data-processing'], format: 'sheet', exportable: true },
  { id: 'a-business-validation', name: 'Business Validation', taskRef: '2.3', type: 'report', stage: 's2', lineage: ['a-data-processing', 'a-quality-scorecard'], format: 'validation' },
  { id: 'a-stat-tests', name: 'Statistical Score', taskRef: '2.4', type: 'scorecard', stage: 's2', lineage: ['a-data-processing', 'a-business-validation'], format: 'sheet' },
  { id: 'a-ols-test', name: 'OLS Regression Test', taskRef: '2.5', type: 'report', stage: 's2', lineage: ['a-stat-tests', 'a-factor-tree', 'a-knowledge-package'], format: 'olsTree' },
  { id: 'a-master-data', name: 'Master Data', taskRef: '2.6', type: 'dataset', stage: 's2', lineage: ['a-data-processing', 'a-quality-scorecard', 'a-business-validation', 'a-stat-tests', 'a-ols-test'], format: 'masterData', exportable: true },

  /* ── S4 · Modeling ───────────────────────────────────── */
  { id: 'a-prior-register', name: 'Prior Setting Rules', taskRef: '3.1', type: 'document', stage: 's4', lineage: ['a-knowledge-package', 'a-business-validation', 'a-master-data'], format: 'sheet' },
  { id: 'a-model-candidates', name: 'Model Candidates', taskRef: '3.2', type: 'model', stage: 's4', lineage: ['a-master-data', 'a-prior-register'], format: 'sheet' },
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
