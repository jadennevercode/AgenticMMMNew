/**
 * Backend API client — talks to the real Agentic MMM FastAPI service.
 * Multi-project: registry calls live under /api/projects; per-project calls are
 * scoped to /api/projects/{projectId}/... Base URL is configurable via
 * VITE_API_BASE (defaults to the local backend).
 */
import type {
  ArtifactEditProposal,
  ArtifactInstance,
  CleaningSpec,
  ClientQA,
  DataAsset,
  DataRequestManifest,
  FactorTree,
  FileCategory,
  GlobalModelConfig,
  IndustryRef,
  KnowledgeTemplate,
  ProjectFile,
  ProjectListItem,
  ProjectMeta,
  ProjectProfile,
  QualityScorecard,
  TemplateKind,
} from '../lib/types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API ${path} failed: ${res.status} ${text.slice(0, 200)}`)
  }
  return res.json() as Promise<T>
}

export interface BackendMeta {
  stages: unknown[]
  agents: unknown[]
  artifacts: unknown[]
  tasks: unknown[]
}

export interface RunStatus {
  running: boolean
  status: {
    steps: number
    tasks_done: number
    tasks_total: number
    awaiting_human: string[]
    complete: boolean
  } | null
}

export interface CreateProjectBody {
  name: string
  brand: string
  industry: IndustryRef
  kpi?: string
}

const p = (projectId: string) => `/api/projects/${encodeURIComponent(projectId)}`

export const api = {
  health: () => req<{ ok: boolean; running: boolean }>('/api/health'),
  meta: () => req<BackendMeta>('/api/meta'),

  // ── project registry ──────────────────────────────────
  listProjects: () => req<ProjectListItem[]>('/api/projects'),
  createProject: (body: CreateProjectBody) =>
    req<ProjectMeta>('/api/projects', { method: 'POST', body: JSON.stringify(body) }),
  deleteProject: (projectId: string) =>
    req<{ ok: boolean }>(p(projectId), { method: 'DELETE' }),

  // ── per-project state / execution ─────────────────────
  state: (projectId: string) => req<Record<string, unknown>>(`${p(projectId)}/state`),
  reset: (projectId: string) => req<{ ok: boolean }>(`${p(projectId)}/reset`, { method: 'POST' }),
  run: (projectId: string, autopilot = true, maxSteps = 300) =>
    req<{ started: boolean }>(`${p(projectId)}/run`, {
      method: 'POST',
      body: JSON.stringify({ autopilot, max_steps: maxSteps }),
    }),
  runStatus: (projectId: string) => req<RunStatus>(`${p(projectId)}/run/status`),

  // ── human actions ─────────────────────────────────────
  resolveDecision: (projectId: string, id: string, optionId: string, note = '') =>
    req(`${p(projectId)}/decisions/${id}/resolve`, { method: 'POST', body: JSON.stringify({ optionId, note }) }),
  submitAssignment: (projectId: string, id: string, note = '', choice?: string) =>
    req(`${p(projectId)}/assignments/${id}/submit`, {
      method: 'POST',
      body: JSON.stringify(choice !== undefined ? { note, choice } : { note }),
    }),
  resolveProposal: (projectId: string, id: string, accept: boolean) =>
    req(`${p(projectId)}/proposals/${id}/resolve`, { method: 'POST', body: JSON.stringify({ accept }) }),
  resolveInsight: (projectId: string, id: string, actioned: boolean) =>
    req(`${p(projectId)}/insights/${id}/resolve`, { method: 'POST', body: JSON.stringify({ actioned }) }),
  chooseAiOption: (projectId: string, setId: string, optionId: string) =>
    req(`${p(projectId)}/ai-choices/${setId}`, { method: 'POST', body: JSON.stringify({ optionId }) }),
  askAssistant: (projectId: string, text: string) =>
    req<{ role: 'assistant'; text: string }>(`${p(projectId)}/assistant`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  // ── chat-driven artifact editing (draft → preview → apply) ──
  draftArtifactEdit: (projectId: string, artifactId: string, text: string) =>
    req<{ reply: { role: 'assistant'; text: string }; proposal: ArtifactEditProposal | null }>(
      `${p(projectId)}/artifacts/${artifactId}/edit`,
      { method: 'POST', body: JSON.stringify({ text }) },
    ),
  applyArtifactEdit: (projectId: string, artifactId: string, proposal: ArtifactEditProposal) =>
    req<ArtifactInstance>(`${p(projectId)}/artifacts/${artifactId}/edit/apply`, {
      method: 'POST',
      body: JSON.stringify(proposal),
    }),

  // ── project folder (uploaded source files) ────────────
  listFiles: (projectId: string) => req<ProjectFile[]>(`${p(projectId)}/files`),
  uploadFile: async (projectId: string, category: FileCategory, file: File, slot?: string): Promise<ProjectFile> => {
    const form = new FormData()
    form.append('category', category)
    form.append('file', file)
    if (slot) form.append('slot', slot)
    const res = await fetch(`${BASE}${p(projectId)}/files`, { method: 'POST', body: form })
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`Upload failed: ${res.status} ${text.slice(0, 200)}`)
    }
    return res.json() as Promise<ProjectFile>
  },
  dataManifest: (projectId: string) =>
    req<DataRequestManifest>(`${p(projectId)}/data-request/manifest`),
  deleteFile: (projectId: string, fileId: string) =>
    req<{ ok: boolean }>(`${p(projectId)}/files/${fileId}`, { method: 'DELETE' }),
  fileDownloadUrl: (projectId: string, fileId: string) => `${BASE}${p(projectId)}/files/${fileId}`,
  /** URL of the Data Request export (ZIP of one .xlsx per L3, one sheet per L4). */
  dataRequestExportUrl: (projectId: string) => `${BASE}${p(projectId)}/data-request/export`,

  // ── project profile (editable granularity + scope) ────
  updateProfile: (projectId: string, profile: ProjectProfile) =>
    req<ProjectProfile>(`${p(projectId)}/profile`, { method: 'PUT', body: JSON.stringify(profile) }),

  // ── global model-service config (LLM + ASR, one for all projects) ──
  getModelConfig: () =>
    req<GlobalModelConfig>('/api/model-config'),
  updateModelConfig: (config: GlobalModelConfig) =>
    req<GlobalModelConfig>('/api/model-config', { method: 'PUT', body: JSON.stringify(config) }),

  // ── factor tree (per-node accept / reject / edit) ─────
  updateFactorTree: (projectId: string, tree: FactorTree) =>
    req<FactorTree>(`${p(projectId)}/factor-tree`, { method: 'PUT', body: JSON.stringify(tree) }),
  updateQualityScorecard: (projectId: string, card: QualityScorecard) =>
    req<QualityScorecard>(`${p(projectId)}/quality-scorecard`, { method: 'PUT', body: JSON.stringify(card) }),
  updateClientQA: (projectId: string, qa: ClientQA) =>
    req<ClientQA>(`${p(projectId)}/client-qa`, { method: 'PUT', body: JSON.stringify(qa) }),

  // ── data engine (raw → review → clean → publish data asset) ──
  listDataAssets: (projectId: string) =>
    req<DataAsset[]>(`${p(projectId)}/data-assets`),
  createDataAsset: (projectId: string, body: { name: string; description?: string; sourceFileIds?: string[] }) =>
    req<DataAsset>(`${p(projectId)}/data-assets`, { method: 'POST', body: JSON.stringify(body) }),
  getDataAsset: (projectId: string, assetId: string) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}`),
  updateDataAsset: (projectId: string, assetId: string, body: { name?: string; description?: string; sourceFileIds?: string[] }) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteDataAsset: (projectId: string, assetId: string) =>
    req<{ ok: boolean }>(`${p(projectId)}/data-assets/${assetId}`, { method: 'DELETE' }),
  reviewDataAsset: (projectId: string, assetId: string) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}/review`, { method: 'POST' }),
  updateCleaningSpec: (projectId: string, assetId: string, spec: CleaningSpec) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}/cleaning-spec`, { method: 'PUT', body: JSON.stringify(spec) }),
  generateAssetSql: (projectId: string, assetId: string) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}/sql/generate`, { method: 'POST' }),
  runAssetSql: (projectId: string, assetId: string, sql: string) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}/sql/run`, { method: 'POST', body: JSON.stringify({ sql }) }),
  publishDataAsset: (projectId: string, assetId: string) =>
    req<DataAsset>(`${p(projectId)}/data-assets/${assetId}/publish`, { method: 'POST' }),

  // ── knowledge templates (cross-project) ───────────────
  listTemplates: (kind?: TemplateKind, industryL1?: string) => {
    const q = new URLSearchParams()
    if (kind) q.set('kind', kind)
    if (industryL1) q.set('industryL1', industryL1)
    const qs = q.toString()
    return req<KnowledgeTemplate[]>(`/api/templates${qs ? `?${qs}` : ''}`)
  },
  saveTemplate: (tpl: KnowledgeTemplate) =>
    req<KnowledgeTemplate>('/api/templates', { method: 'POST', body: JSON.stringify(tpl) }),
  cloneTemplate: (templateId: string, name?: string) =>
    req<KnowledgeTemplate>(`/api/templates/${templateId}/clone`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  deleteTemplate: (templateId: string) =>
    req<{ ok: boolean }>(`/api/templates/${templateId}`, { method: 'DELETE' }),

  // ── apply an industry knowledge pack into a project (factor-tree refresh) ──
  applyPack: (projectId: string, body: { industryL1: string; industryL2?: string }) =>
    req<FactorTree>(`${p(projectId)}/apply-pack`, { method: 'POST', body: JSON.stringify(body) }),
}
