import { create } from 'zustand'
import type {
  ArtifactBody,
  ArtifactEditProposal,
  ArtifactInstance,
  AssistantTurn,
  DataAsset,
  TransformPipeline,
  DbtPreview,
  DbtWorkspaceInfo,
  DataRequestManifest,
  FactorTree,
  FileCategory,
  GlobalModelConfig,
  AnomalyReview,
  OlsConfig,
  ProjectFile,
  ProjectListItem,
  ProjectMeta,
  ProjectProfile,
  QualityScorecard,
  SimEvent,
  StageId,
  StatScorecard,
  TaskFinding,
  TaskRuntime,
} from '../lib/types'
import { TASKS } from '../lib/scenario'
import { bodyToMarkdown } from '../lib/artifact-format'
import type { LedgerEntry } from '../lib/types'
import { STAGE_ORDER } from '../lib/profiles'
import { api, type CreateProjectBody } from '../api/client'

/* ────────────────────────────────────────────────────────────
 * Backend-driven, multi-project store.
 *
 * The landing page loads the project registry (`loadProjects`). Entering a
 * workspace calls `loadProject(id)`, which sets `activeProjectId` and hydrates
 * that project's state from `/api/projects/{id}/state`. All runtime mutations
 * are scoped to the active project. There is no in-browser mock engine.
 * ──────────────────────────────────────────────────────────── */

/** Full decision object as returned by the backend (blueprint + runtime merged). */
export interface BackendDecision {
  id: string
  kind: string
  title: string
  question: string
  evidence: { artifactId: string; note?: string }[]
  recommendation: string
  options: { id: string; label: string; detail: string; consequence: string; recommended?: boolean }[]
  reworkTaskId?: string
  reworkOptionId?: string
  status: 'idle' | 'open' | 'resolved'
  openedAtTick?: number
  resolution?: { optionId: string; note: string; decidedAtTick: number }
}

/** Full assignment object as returned by the backend. */
export interface BackendAssignment {
  id: string
  kind: string
  title: string
  prompt: string
  items: string[]
  submitLabel: string
  status: 'idle' | 'open' | 'submitted'
  submittedAtTick?: number
  note?: string
  /** Project-Folder category this upload feeds (S1 upload gates). */
  category?: FileCategory
  /** When true, real parsed files must exist in `category` before submit. */
  requiresUpload?: boolean
  /** Optional source-choice gate (e.g. 1.1a factor-tree origin). */
  choicePrompt?: string
  choiceOptions?: Array<{ id: string; label: string; detail?: string; recommended?: boolean }>
  choiceUploadCategory?: FileCategory
  /** The picked source-choice option id (runtime). */
  chosenSource?: string
}

/** Full AI option-set object as returned by the backend. */
export interface BackendAiChoice {
  id: string
  prompt: string
  options: { id: string; label: string; rationale: string; tradeoff: string; recommended?: boolean }[]
  chosenId?: string
}

/** Full proposal object as returned by the backend. */
export interface BackendProposal {
  id: string
  targetArtifactId: string
  title: string
  summary: string
  diff: { kind: 'add' | 'remove' | 'keep'; text: string }[]
  evidence: { artifactId: string; note?: string }[]
  confidence: number
  sourceAgent: string
  sourceMode: string
  afterTask: string
  status: 'open' | 'accepted' | 'dismissed'
}

/** Full insight object as returned by the backend. */
export interface BackendInsight {
  id: string
  kind: string
  title: string
  finding: string
  evidence: { artifactId: string; note?: string }[]
  confidence: number
  actions: { kind: string; label: string; artifactId?: string }[]
  afterTask: string
  status: 'new' | 'actioned' | 'dismissed'
  surfacedAtTick?: number
}

/** Backend /api/projects/{id}/state envelope (camelCase, mirrors lib/types). */
interface BackendState {
  project_id?: string
  meta?: ProjectMeta
  profile?: ProjectProfile | null
  factor_tree?: FactorTree | null
  quality_scorecard?: QualityScorecard | null
  stat_scorecard?: StatScorecard | null
  ols_config?: OlsConfig | null
  anomaly_review?: AnomalyReview | null
  tick?: number
  tasks?: Record<string, Partial<TaskRuntime> & Record<string, unknown>>
  decisions?: Record<string, BackendDecision>
  assignments?: Record<string, BackendAssignment>
  ai_choices?: Record<string, BackendAiChoice>
  artifacts?: ArtifactInstance[]
  proposals?: BackendProposal[]
  insights?: BackendInsight[]
  events?: SimEvent[]
  ledger?: LedgerEntry[]
  assistant?: AssistantTurn[]
  artifactChats?: Record<string, AssistantTurn[]>
  findings?: Record<string, TaskFinding[]>
  analysis?: unknown
  dataAssets?: DataAsset[]
}

const POLL_INTERVAL_MS = 1500

interface SimStore {
  // ── project registry ──
  projects: ProjectListItem[]
  projectsLoading: boolean
  activeProjectId: string | null
  activeMeta: ProjectMeta | null

  tick: number
  playing: boolean
  /** true while a backend run loop is active */
  running: boolean
  /** When true, the run loop auto-satisfies HITL gates (uploads + decisions) to
   *  drive the whole case end-to-end. Default false: the run stops at every
   *  upload and decision node for genuine human-in-the-loop action. */
  autopilot: boolean
  /** hydration / request state */
  loading: boolean
  error: string | null
  tasks: Record<string, TaskRuntime>
  decisions: Record<string, BackendDecision>
  assignments: Record<string, BackendAssignment>
  aiChoices: Record<string, BackendAiChoice>
  proposals: BackendProposal[]
  insights: BackendInsight[]
  artifacts: ArtifactInstance[]
  /** Per-artifact "edit with AI" chat threads (backend-persisted + optimistic). */
  artifactChats: Record<string, AssistantTurn[]>
  /** Pending (drafted, not-yet-applied) chat edits, keyed by artifact id. */
  artifactProposals: Record<string, ArtifactEditProposal>
  /** Artifact id currently awaiting a draft reply (drives the chat spinner). */
  artifactDrafting: string | null
  /** Per-task grounded findings, keyed by task id (from backend) */
  findings: Record<string, TaskFinding[]>
  events: SimEvent[]
  assistant: AssistantTurn[]
  ledger: LedgerEntry[]
  selectedTaskId: string | null
  selectedAssetId: string | null
  viewedStageId: StageId | null
  panels: { activity: boolean; assistant: boolean; folder: boolean }

  /** Uploaded project-folder files (real backend storage). */
  files: ProjectFile[]
  filesLoading: boolean
  /** Parsed + editable project profile (granularity + model scope). */
  profile: ProjectProfile | null
  /** Global LLM + ASR model-service config (one for all projects; null = unloaded). */
  modelConfig: GlobalModelConfig | null
  /** Structured factor tree with per-node confirm state. */
  factorTree: FactorTree | null
  /** S2 data quality scorecard with per-metric human disposition. */
  qualityScorecard: QualityScorecard | null
  /** S2 (2.4) statistical score with per-indicator human disposition. */
  statScorecard: StatScorecard | null
  olsConfig: OlsConfig | null
  /** S2 (2.3a) anomaly hypotheses with the human's per-anomaly ruling. */
  anomalyReview: AnomalyReview | null

  /** Data Engine: project-scoped data assets (raw → review → clean → publish). */
  dataAssets: DataAsset[]
  dataAssetsLoading: boolean
  /** Asset id of the currently-selected asset in the data-engine workbench. */
  selectedDataAssetId: string | null
  /** Asset id currently running an async op (review/sql/publish) — drives spinners. */
  dataAssetBusy: string | null

  /** Load the project registry for the landing page. */
  loadProjects: () => Promise<void>
  /** Create a new project; returns its id on success. */
  createProject: (body: CreateProjectBody) => Promise<string>
  /** Delete a project from the registry. */
  deleteProject: (projectId: string) => Promise<void>
  /** Enter a project workspace: set active id + hydrate its state. */
  loadProject: (projectId: string) => Promise<void>
  /** Pull a fresh state for the active project and merge it into the store. */
  refresh: () => Promise<void>
  /** Start the active project's run loop and poll until it completes. */
  run: () => Promise<void>
  play: () => void
  pause: () => void
  /** Toggle autopilot (auto-satisfy HITL gates) vs interactive HITL. */
  setAutopilot: (value: boolean) => void
  reset: () => Promise<void>

  resolveDecision: (decisionId: string, optionId: string, note: string) => Promise<void>
  submitAssignment: (taskId: string, note: string, choice?: string) => Promise<void>
  resolveProposal: (proposalId: string, accept: boolean) => Promise<void>
  resolveInsight: (insightId: string, actioned: boolean) => Promise<void>
  askAssistant: (text: string) => Promise<void>
  chooseAiOption: (setId: string, optionId: string) => Promise<void>

  /** Local-only optimistic artifact edits (manual canvas edits). */
  editArtifact: (artifactId: string, patch: { content?: string; body?: ArtifactBody }) => void
  /** Ask the AI to change a document; drafts a proposal (preview-then-confirm). */
  sendArtifactEdit: (artifactId: string, text: string) => Promise<void>
  /** Apply a pending drafted proposal to the artifact (persists server-side). */
  applyArtifactProposal: (artifactId: string) => Promise<void>
  /** Discard a pending drafted proposal without applying it. */
  discardArtifactProposal: (artifactId: string) => void

  /** Project folder: list, upload, delete. */
  loadFiles: () => Promise<void>
  uploadFile: (category: FileCategory, file: File) => Promise<void>
  deleteFile: (fileId: string) => Promise<void>
  /** Persist edits to the project profile (granularity + scope). */
  updateProfile: (profile: ProjectProfile) => Promise<void>
  /** Load the global LLM + ASR model-service config (once, on app start). */
  loadModelConfig: () => Promise<void>
  /** Persist the global LLM + ASR model-service config (shared by all projects). */
  updateModelConfig: (config: GlobalModelConfig) => Promise<void>
  /** Persist edits to the factor tree (accept/reject/edit nodes). */
  updateFactorTree: (tree: FactorTree) => Promise<void>
  /** Persist edits to the data quality scorecard (per-metric disposition). */
  updateQualityScorecard: (card: QualityScorecard) => Promise<void>
  /** Persist edits to the statistical score (per-indicator disposition). */
  updateStatScorecard: (card: StatScorecard) => Promise<void>
  updateOlsConfig: (cfg: OlsConfig) => Promise<void>
  /** Persist the 2.3a anomaly rulings; accepted handlings reach the fit. */
  updateAnomalyReview: (review: AnomalyReview) => Promise<void>

  /** Data Engine actions. */
  loadDataAssets: () => Promise<void>
  createDataAsset: (name: string, description?: string, sourceFileIds?: string[]) => Promise<string | null>
  updateDataAsset: (id: string, patch: { name?: string; description?: string; sourceFileIds?: string[] }) => Promise<void>
  deleteDataAsset: (id: string) => Promise<void>
  reviewDataAsset: (id: string) => Promise<void>
  dbtBuild: (id: string) => Promise<void>
  dbtGenerate: (id: string, instruction?: string) => Promise<void>
  dbtPublish: (id: string) => Promise<void>
  dbtStatus: (id: string) => Promise<DbtWorkspaceInfo | null>
  dbtPreview: (id: string, model: string) => Promise<DbtPreview | null>
  /** Persist a transform pipeline and keep the store asset's pipeline in sync. */
  putPipeline: (id: string, pipe: TransformPipeline) => Promise<TransformPipeline | null>
  /** Upload a raw source file (category raw_data) and attach it to an asset. */
  uploadRawForAsset: (assetId: string, file: File) => Promise<void>
  selectDataAsset: (id: string | null) => void

  /** BU-derived data-request upload manifest (L3 slots + coverage). */
  dataManifest: DataRequestManifest | null
  /** Fetch the data-request manifest for the active project. */
  loadDataManifest: () => Promise<void>
  /** Upload a workbook bound to a specific L3 data-request slot. */
  uploadToSlot: (slot: string, file: File) => Promise<void>

  selectTask: (id: string | null) => void
  selectAsset: (id: string | null) => void
  setViewedStage: (id: StageId | null) => void
  togglePanel: (which: 'activity' | 'assistant' | 'folder', open?: boolean) => void
}

const WELCOME: AssistantTurn = {
  role: 'assistant',
  text: 'Hi — I can answer questions about this project: where a number comes from, why a variable was dropped, what the client said. Run the project, then ask away.',
}

/** Empty runtime task map derived from the blueprint DAG (until the backend responds). */
function emptyTasks(): Record<string, TaskRuntime> {
  return Object.fromEntries(
    TASKS.map((t) => [t.id, { status: 'pending', progress: 0, runs: 1 } as TaskRuntime]),
  )
}

/** Normalise a backend task record into the TaskRuntime shape components expect. */
function toTaskRuntime(raw: Partial<TaskRuntime> & Record<string, unknown>): TaskRuntime {
  return {
    status: (raw.status as TaskRuntime['status']) ?? 'pending',
    progress: typeof raw.progress === 'number' ? raw.progress : 0,
    startedTick: typeof raw.startedTick === 'number' ? raw.startedTick : undefined,
    finishedTick: typeof raw.finishedTick === 'number' ? raw.finishedTick : undefined,
    runs: typeof raw.runs === 'number' ? raw.runs : 1,
  }
}

/** Map a raw state payload onto the store fields. */
/** Merge backend-persisted artifact chats with local optimistic threads.
 * A poll may race ahead of an in-flight draft's save, so keep whichever thread
 * is longer per artifact — never let a stale poll drop an optimistic turn. */
function mergeChats(
  backend: Record<string, AssistantTurn[]> | undefined,
  local: Record<string, AssistantTurn[]>,
): Record<string, AssistantTurn[]> {
  if (!backend) return local
  const out: Record<string, AssistantTurn[]> = { ...local }
  for (const [id, thread] of Object.entries(backend)) {
    const cur = local[id] ?? []
    out[id] = thread.length >= cur.length ? thread : cur
  }
  return out
}

function mapState(s: BackendState, currentChats: Record<string, AssistantTurn[]> = {}): Partial<SimStore> {
  const patch: Partial<SimStore> = {}
  patch.artifactChats = mergeChats(s.artifactChats, currentChats)
  if (typeof s.tick === 'number') patch.tick = s.tick
  if (s.meta) patch.activeMeta = s.meta
  if (s.profile !== undefined) patch.profile = s.profile ?? null
  if (s.factor_tree !== undefined) patch.factorTree = s.factor_tree ?? null
  if (s.quality_scorecard !== undefined) patch.qualityScorecard = s.quality_scorecard ?? null
  if (s.stat_scorecard !== undefined) patch.statScorecard = s.stat_scorecard ?? null
  if (s.ols_config !== undefined) patch.olsConfig = s.ols_config ?? null
  if (s.anomaly_review !== undefined) patch.anomalyReview = s.anomaly_review ?? null
  if (s.tasks) {
    patch.tasks = Object.fromEntries(
      Object.entries(s.tasks).map(([id, raw]) => [id, toTaskRuntime(raw)]),
    )
  }
  if (s.decisions) patch.decisions = s.decisions
  if (s.assignments) patch.assignments = s.assignments
  if (s.ai_choices) patch.aiChoices = s.ai_choices
  if (Array.isArray(s.proposals)) patch.proposals = s.proposals
  if (Array.isArray(s.insights)) patch.insights = s.insights
  if (Array.isArray(s.artifacts)) patch.artifacts = s.artifacts
  if (Array.isArray(s.events)) patch.events = s.events
  if (Array.isArray(s.ledger)) patch.ledger = s.ledger
  if (Array.isArray(s.assistant)) patch.assistant = s.assistant.length ? s.assistant : [WELCOME]
  if (s.findings) patch.findings = s.findings
  if (Array.isArray(s.dataAssets)) patch.dataAssets = s.dataAssets
  return patch
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : 'Request failed'
}

/** Reset all per-project runtime fields (used when switching projects). */
function blankRuntime(): Partial<SimStore> {
  return {
    tick: 0,
    playing: false,
    running: false,
    tasks: emptyTasks(),
    decisions: {},
    assignments: {},
    aiChoices: {},
    proposals: [],
    insights: [],
    artifacts: [],
    artifactChats: {},
    artifactProposals: {},
    artifactDrafting: null,
    findings: {},
    events: [],
    assistant: [WELCOME],
    ledger: [],
    files: [],
    filesLoading: false,
    dataManifest: null,
    profile: null,
    modelConfig: null,
    factorTree: null,
    qualityScorecard: null,
    statScorecard: null,
    olsConfig: null,
    anomalyReview: null,
    dataAssets: [],
    dataAssetsLoading: false,
    selectedDataAssetId: null,
    dataAssetBusy: null,
    selectedTaskId: null,
    selectedAssetId: null,
    viewedStageId: null,
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null

export const useSimStore = create<SimStore>((set, get) => {
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function pollOnce() {
    const pid = get().activeProjectId
    if (!pid) {
      stopPolling()
      return
    }
    try {
      const [state, status] = await Promise.all([api.state(pid), api.runStatus(pid)])
      set({ ...mapState(state as BackendState, get().artifactChats), running: status.running })
      if (!status.running) {
        stopPolling()
        set({ playing: false })
      }
    } catch (e) {
      set({ error: errorMessage(e) })
    }
  }

  function startPolling() {
    if (pollTimer) return
    pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS)
  }

  return {
    projects: [],
    projectsLoading: false,
    activeProjectId: null,
    activeMeta: null,

    tick: 0,
    playing: false,
    running: false,
    autopilot: false,
    loading: false,
    error: null,
    tasks: emptyTasks(),
    decisions: {},
    assignments: {},
    aiChoices: {},
    proposals: [],
    insights: [],
    artifacts: [],
    artifactChats: {},
    artifactProposals: {},
    artifactDrafting: null,
    findings: {},
    events: [],
    assistant: [WELCOME],
    ledger: [],
    files: [],
    filesLoading: false,
    dataManifest: null,
    profile: null,
    modelConfig: null,
    factorTree: null,
    qualityScorecard: null,
    statScorecard: null,
    olsConfig: null,
    anomalyReview: null,
    dataAssets: [],
    dataAssetsLoading: false,
    selectedDataAssetId: null,
    dataAssetBusy: null,
    selectedTaskId: null,
    selectedAssetId: null,
    viewedStageId: null,
    panels: { activity: false, assistant: false, folder: false },

    loadProjects: async () => {
      set({ projectsLoading: true, error: null })
      try {
        const projects = await api.listProjects()
        set({ projects, projectsLoading: false })
      } catch (e) {
        set({ projectsLoading: false, error: errorMessage(e) })
      }
    },

    createProject: async (body) => {
      const meta = await api.createProject(body)
      // Refresh the registry so the new card appears.
      await get().loadProjects()
      return meta.id
    },

    deleteProject: async (projectId) => {
      try {
        await api.deleteProject(projectId)
        await get().loadProjects()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    loadProject: async (projectId) => {
      // Switching projects: stop any poll and clear prior runtime first.
      if (get().activeProjectId !== projectId) {
        stopPolling()
        set({ ...blankRuntime(), activeProjectId: projectId, activeMeta: null })
      }
      set({ loading: true, error: null })
      try {
        const [state, status] = await Promise.all([api.state(projectId), api.runStatus(projectId)])
        set({ ...mapState(state as BackendState, get().artifactChats), running: status.running, loading: false })
        if (status.running) startPolling()
        void get().loadFiles()
      } catch (e) {
        set({ loading: false, error: errorMessage(e) })
      }
    },

    refresh: async () => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        const state = await api.state(pid)
        set(mapState(state as BackendState, get().artifactChats))
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    run: async () => {
      const pid = get().activeProjectId
      if (!pid) return
      set({ error: null, playing: true })
      try {
        await api.run(pid, get().autopilot)
        set({ running: true })
        await pollOnce()
        startPolling()
      } catch (e) {
        set({ error: errorMessage(e), playing: false, running: false })
      }
    },

    play: () => {
      void get().run()
    },

    pause: () => {
      stopPolling()
      set({ playing: false })
    },

    setAutopilot: (value) => set({ autopilot: value }),

    reset: async () => {
      const pid = get().activeProjectId
      if (!pid) return
      stopPolling()
      set({ playing: false, running: false })
      try {
        await api.reset(pid)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    resolveDecision: async (decisionId, optionId, note) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        await api.resolveDecision(pid, decisionId, optionId, note)
        // Auto-advance: run the automated tasks up to the next HITL gate.
        await get().run()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    submitAssignment: async (taskId, note, choice) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Components pass the *task* id; resolve to the assignment id on the task.
      const task = TASKS.find((t) => t.id === taskId)
      const assignmentId = task?.assignment?.id ?? taskId
      try {
        await api.submitAssignment(pid, assignmentId, note, choice)
        // Auto-advance: run the automated tasks up to the next HITL gate.
        await get().run()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    resolveProposal: async (proposalId, accept) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        await api.resolveProposal(pid, proposalId, accept)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    resolveInsight: async (insightId, actioned) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        await api.resolveInsight(pid, insightId, actioned)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    chooseAiOption: async (setId, optionId) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        await api.chooseAiOption(pid, setId, optionId)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    askAssistant: async (text) => {
      if (!text.trim()) return
      const pid = get().activeProjectId
      if (!pid) return
      const state = get()
      // optimistic: show the user's turn immediately
      set({ assistant: [...state.assistant, { role: 'user', text }] })
      try {
        const reply = await api.askAssistant(pid, text)
        set((s) => ({ assistant: [...s.assistant, { role: 'assistant', text: reply.text }] }))
      } catch (e) {
        set((s) => ({
          assistant: [...s.assistant, { role: 'assistant', text: `Sorry — I could not reach the project service. (${errorMessage(e)})` }],
          error: errorMessage(e),
        }))
      }
    },

    editArtifact: (artifactId, patch) => {
      const state = get()
      if (!state.artifacts.some((a) => a.id === artifactId)) return
      set({
        artifacts: state.artifacts.map((a) => {
          if (a.id !== artifactId) return a
          if (patch.body) return { ...a, body: patch.body, content: bodyToMarkdown(a.format, patch.body, a.content), editedAtTick: state.tick }
          if (patch.content !== undefined) return { ...a, content: patch.content, editedAtTick: state.tick }
          return a
        }),
      })
    },

    sendArtifactEdit: async (artifactId, text) => {
      const state = get()
      const pid = state.activeProjectId
      if (!pid || !text.trim()) return
      const inst = state.artifacts.find((a) => a.id === artifactId)
      const prev = state.artifactChats[artifactId] ?? []
      const user: AssistantTurn = { role: 'user', text }
      if (!inst) {
        const reply: AssistantTurn = {
          role: 'assistant',
          text: 'This deliverable hasn’t been produced yet — run its steps first and I can help you edit it.',
        }
        set({ artifactChats: { ...state.artifactChats, [artifactId]: [...prev, user, reply] } })
        return
      }
      // Optimistic: show the user's turn immediately and spin while drafting.
      set({ artifactChats: { ...state.artifactChats, [artifactId]: [...prev, user] }, artifactDrafting: artifactId })
      try {
        const { reply, proposal } = await api.draftArtifactEdit(pid, artifactId, text)
        set((s) => {
          const thread = s.artifactChats[artifactId] ?? []
          const proposals = { ...s.artifactProposals }
          if (proposal) proposals[artifactId] = proposal
          return {
            artifactChats: { ...s.artifactChats, [artifactId]: [...thread, { role: 'assistant', text: reply.text }] },
            artifactProposals: proposals,
            artifactDrafting: null,
          }
        })
      } catch (e) {
        set((s) => {
          const thread = s.artifactChats[artifactId] ?? []
          return {
            artifactChats: {
              ...s.artifactChats,
              [artifactId]: [...thread, { role: 'assistant', text: `Sorry — the edit service is unavailable. (${errorMessage(e)})` }],
            },
            artifactDrafting: null,
            error: errorMessage(e),
          }
        })
      }
    },

    applyArtifactProposal: async (artifactId) => {
      const state = get()
      const pid = state.activeProjectId
      const proposal = state.artifactProposals[artifactId]
      if (!pid || !proposal) return
      try {
        const updated = await api.applyArtifactEdit(pid, artifactId, proposal)
        set((s) => {
          const proposals = { ...s.artifactProposals }
          delete proposals[artifactId]
          const thread = s.artifactChats[artifactId] ?? []
          return {
            artifacts: s.artifacts.map((a) => (a.id === artifactId ? updated : a)),
            artifactProposals: proposals,
            artifactChats: {
              ...s.artifactChats,
              [artifactId]: [...thread, { role: 'assistant', text: `✓ Applied. “${updated.name}” is now at v${updated.version}.` }],
            },
          }
        })
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    discardArtifactProposal: (artifactId) => {
      set((s) => {
        const proposals = { ...s.artifactProposals }
        delete proposals[artifactId]
        const thread = s.artifactChats[artifactId] ?? []
        return {
          artifactProposals: proposals,
          artifactChats: {
            ...s.artifactChats,
            [artifactId]: [...thread, { role: 'assistant', text: 'Discarded — the document is unchanged.' }],
          },
        }
      })
    },

    loadFiles: async () => {
      const pid = get().activeProjectId
      if (!pid) return
      set({ filesLoading: true })
      try {
        const files = await api.listFiles(pid)
        set({ files, filesLoading: false })
      } catch (e) {
        set({ filesLoading: false, error: errorMessage(e) })
      }
    },

    uploadFile: async (category, file) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        const record = await api.uploadFile(pid, category, file)
        set((s) => ({ files: [...s.files.filter((f) => f.id !== record.id), record] }))
      } catch (e) {
        set({ error: errorMessage(e) })
        throw e
      }
    },

    loadDataManifest: async () => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        const dataManifest = await api.dataManifest(pid)
        set({ dataManifest })
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    uploadToSlot: async (slot, file) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        const record = await api.uploadFile(pid, 'data', file, slot)
        set((s) => ({ files: [...s.files.filter((f) => f.id !== record.id), record] }))
        await get().loadDataManifest()
        await get().loadFiles()
      } catch (e) {
        set({ error: errorMessage(e) })
        throw e
      }
    },

    deleteFile: async (fileId) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        await api.deleteFile(pid, fileId)
        set((s) => ({ files: s.files.filter((f) => f.id !== fileId) }))
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateProfile: async (profile) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Optimistic; refresh re-syncs the re-rendered a-scope artifact.
      set({ profile })
      try {
        await api.updateProfile(pid, profile)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    loadModelConfig: async () => {
      try {
        const config = await api.getModelConfig()
        set({ modelConfig: config })
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateModelConfig: async (config) => {
      set({ modelConfig: config })
      try {
        await api.updateModelConfig(config)
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateFactorTree: async (tree) => {
      const pid = get().activeProjectId
      if (!pid) return
      set({ factorTree: tree })
      try {
        await api.updateFactorTree(pid, tree)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateQualityScorecard: async (card) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Optimistic; refresh re-syncs the re-rendered a-quality-scorecard artifact.
      set({ qualityScorecard: card })
      try {
        await api.updateQualityScorecard(pid, card)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateStatScorecard: async (card) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Optimistic; refresh re-syncs the re-rendered a-stat-tests artifact.
      set({ statScorecard: card })
      try {
        await api.updateStatScorecard(pid, card)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateAnomalyReview: async (review) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Optimistic; the accepted handlings are read back at fit time, so this
      // is what decides whether an event dummy or a cap reaches the model.
      set({ anomalyReview: review })
      try {
        await api.updateAnomalyReview(pid, review)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    updateOlsConfig: async (cfg) => {
      const pid = get().activeProjectId
      if (!pid) return
      // Optimistic; the PUT re-fits the OLS and refresh re-syncs a-ols-test.
      set({ olsConfig: cfg })
      try {
        await api.updateOlsConfig(pid, cfg)
        await get().refresh()
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    // ── Data Engine ───────────────────────────────────────
    loadDataAssets: async () => {
      const pid = get().activeProjectId
      if (!pid) return
      set({ dataAssetsLoading: true })
      try {
        const dataAssets = await api.listDataAssets(pid)
        set({ dataAssets, dataAssetsLoading: false })
      } catch (e) {
        set({ dataAssetsLoading: false, error: errorMessage(e) })
      }
    },

    createDataAsset: async (name, description = '', sourceFileIds = []) => {
      const pid = get().activeProjectId
      if (!pid) return null
      try {
        const asset = await api.createDataAsset(pid, { name, description, sourceFileIds })
        set((s) => ({ dataAssets: [...s.dataAssets, asset], selectedDataAssetId: asset.id }))
        return asset.id
      } catch (e) {
        set({ error: errorMessage(e) })
        return null
      }
    },

    updateDataAsset: async (id, patch) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        const updated = await api.updateDataAsset(pid, id, patch)
        set((s) => ({ dataAssets: s.dataAssets.map((a) => (a.id === id ? updated : a)) }))
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    deleteDataAsset: async (id) => {
      const pid = get().activeProjectId
      if (!pid) return
      try {
        await api.deleteDataAsset(pid, id)
        set((s) => ({
          dataAssets: s.dataAssets.filter((a) => a.id !== id),
          selectedDataAssetId: s.selectedDataAssetId === id ? null : s.selectedDataAssetId,
        }))
      } catch (e) {
        set({ error: errorMessage(e) })
      }
    },

    reviewDataAsset: async (id) => {
      await runAssetOp(id, () => api.reviewDataAsset(get().activeProjectId!, id))
    },

    dbtBuild: async (id) => {
      await runAssetOp(id, () => api.dbtBuild(get().activeProjectId!, id))
    },

    dbtGenerate: async (id, instruction = '') => {
      await runAssetOp(id, () => api.dbtGenerate(get().activeProjectId!, id, instruction))
    },

    dbtPublish: async (id) => {
      await runAssetOp(id, () => api.dbtPublish(get().activeProjectId!, id))
    },

    dbtStatus: async (id) => {
      const pid = get().activeProjectId
      if (!pid) return null
      try {
        return await api.dbtStatus(pid, id)
      } catch (e) {
        set({ error: errorMessage(e) })
        return null
      }
    },

    putPipeline: async (id, pipe) => {
      const pid = get().activeProjectId
      if (!pid) return null
      try {
        const saved = await api.putPipeline(pid, id, pipe)
        // Keep the store asset's pipeline in sync so the editor's reconcile logic
        // sees its own save echoed back (never a stale server copy after saving).
        set((s) => ({
          dataAssets: s.dataAssets.map((a) => (a.id === id ? { ...a, pipeline: saved } : a)),
        }))
        return saved
      } catch (e) {
        set({ error: errorMessage(e) })
        return null
      }
    },

    dbtPreview: async (id, model) => {
      const pid = get().activeProjectId
      if (!pid) return null
      try {
        return await api.dbtPreview(pid, id, model)
      } catch (e) {
        set({ error: errorMessage(e) })
        return null
      }
    },

    uploadRawForAsset: async (assetId, file) => {
      const pid = get().activeProjectId
      if (!pid) return
      set({ dataAssetBusy: assetId, error: null })
      try {
        const record = await api.uploadFile(pid, 'raw_data', file)
        set((s) => ({ files: [...s.files.filter((f) => f.id !== record.id), record] }))
        const asset = get().dataAssets.find((a) => a.id === assetId)
        const sourceFileIds = [...(asset?.sourceFileIds ?? []), record.id]
        const updated = await api.updateDataAsset(pid, assetId, { sourceFileIds })
        set((s) => ({
          dataAssets: s.dataAssets.map((a) => (a.id === assetId ? updated : a)),
          dataAssetBusy: null,
        }))
      } catch (e) {
        set({ dataAssetBusy: null, error: errorMessage(e) })
      }
    },

    selectDataAsset: (id) => set({ selectedDataAssetId: id }),

    selectTask: (id) => set({ selectedTaskId: id }),
    selectAsset: (id) => set({ selectedAssetId: id }),
    setViewedStage: (id) => set({ viewedStageId: id }),
    togglePanel: (which, open) =>
      set((s) => ({ panels: { ...s.panels, [which]: open ?? !s.panels[which] } })),
  }

  /** Run an async asset op that returns the updated asset; manage busy + error + merge. */
  async function runAssetOp(id: string, op: () => Promise<DataAsset>): Promise<void> {
    const pid = get().activeProjectId
    if (!pid) return
    set({ dataAssetBusy: id, error: null })
    try {
      const updated = await op()
      set((s) => ({
        dataAssets: s.dataAssets.map((a) => (a.id === id ? updated : a)),
        dataAssetBusy: null,
      }))
    } catch (e) {
      set({ dataAssetBusy: null, error: errorMessage(e) })
    }
  }
})

// Dev-only handle for debugging / e2e (e.g. simulating a poll's dataAssets churn).
if (import.meta.env.DEV && typeof window !== 'undefined') {
  ;(window as unknown as { __sim?: typeof useSimStore }).__sim = useSimStore
}

/** Stage completion 0–100 */
export function stageProgress(tasks: Record<string, TaskRuntime>, stageId: string): number {
  const stageTasks = TASKS.filter((t) => t.stage === stageId)
  if (!stageTasks.length) return 0
  const sum = stageTasks.reduce((acc, t) => acc + (tasks[t.id]?.status === 'done' ? 100 : (tasks[t.id]?.progress ?? 0)), 0)
  return Math.round(sum / stageTasks.length)
}

/** First stage that isn't fully done — the one currently in flight */
export function currentStage(tasks: Record<string, TaskRuntime>): StageId {
  for (const sid of STAGE_ORDER) {
    const stageTasks = TASKS.filter((t) => t.stage === sid)
    if (stageTasks.some((t) => tasks[t.id]?.status !== 'done')) return sid
  }
  return STAGE_ORDER[STAGE_ORDER.length - 1]
}
