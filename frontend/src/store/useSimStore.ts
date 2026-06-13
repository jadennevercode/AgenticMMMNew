import { create } from 'zustand'
import type {
  ArtifactInstance,
  ArtifactState,
  AssignmentRuntime,
  AssistantTurn,
  DecisionRuntime,
  InsightRuntime,
  ProposalRuntime,
  SimEvent,
  StageId,
  TaskRuntime,
} from '../lib/types'
import { TASKS, TASK_MAP, downstreamOf } from '../lib/scenario'
import { ARTIFACT_MAP } from '../lib/artifacts-data'
import { ASSISTANT_FALLBACK, ASSISTANT_SCRIPT, INSIGHTS, PROPOSALS } from '../lib/collab-data'
import { PROPOSAL_LEDGER, SEED_LEDGER, type LedgerEntry } from '../lib/knowledge-data'
import { AGENTS, STAGE_ORDER } from '../lib/profiles'

interface SimStore {
  tick: number
  playing: boolean
  tasks: Record<string, TaskRuntime>
  decisions: Record<string, DecisionRuntime>
  assignments: Record<string, AssignmentRuntime>
  proposals: Record<string, ProposalRuntime>
  insights: Record<string, InsightRuntime>
  artifacts: ArtifactInstance[]
  events: SimEvent[]
  assistant: AssistantTurn[]
  ledger: LedgerEntry[]
  selectedTaskId: string | null
  /** asset shown in the right-hand panel */
  selectedAssetId: string | null
  /** sidebar stage override; null = follow current running stage */
  viewedStageId: StageId | null
  /** bottom-right floating panels */
  panels: { activity: boolean; assistant: boolean }
  play: () => void
  pause: () => void
  reset: () => void
  stepTick: () => void
  resolveDecision: (decisionId: string, optionId: string, note: string) => void
  submitAssignment: (taskId: string, note: string) => void
  resolveProposal: (proposalId: string, accept: boolean) => void
  resolveInsight: (insightId: string, actioned: boolean) => void
  askAssistant: (text: string) => void
  selectTask: (id: string | null) => void
  selectAsset: (id: string | null) => void
  setViewedStage: (id: StageId | null) => void
  togglePanel: (which: 'activity' | 'assistant', open?: boolean) => void
}

/** Initial lifecycle per producing class: rule output is final, AI output needs eyes */
const INITIAL_STATE_BY_CLASS: Record<string, ArtifactState> = {
  M: 'confirmed',
  A: 'draft',
  C: 'proposed',
  H: 'confirmed',
}

function initialTasks(): Record<string, TaskRuntime> {
  return Object.fromEntries(TASKS.map((t) => [t.id, { status: 'pending', progress: 0, runs: 1 } as TaskRuntime]))
}
function initialDecisions(): Record<string, DecisionRuntime> {
  return Object.fromEntries(TASKS.filter((t) => t.decision).map((t) => [t.decision!.id, { status: 'idle' } as DecisionRuntime]))
}
function initialAssignments(): Record<string, AssignmentRuntime> {
  return Object.fromEntries(TASKS.filter((t) => t.assignment).map((t) => [t.assignment!.id, { status: 'idle' } as AssignmentRuntime]))
}
function initialProposals(): Record<string, ProposalRuntime> {
  return Object.fromEntries(PROPOSALS.map((p) => [p.id, { status: 'open' } as ProposalRuntime]))
}
function initialInsights(): Record<string, InsightRuntime> {
  return Object.fromEntries(INSIGHTS.map((i) => [i.id, { status: 'new' } as InsightRuntime]))
}

const WELCOME: AssistantTurn = {
  role: 'assistant',
  text: 'Hi — I can answer questions about this project: where a number comes from, why a variable was dropped, what the client said. Try “why was 批发 merged into TT?”',
}

let eventSeq = 0
function makeEvent(tick: number, partial: Omit<SimEvent, 'id' | 'tick'>): SimEvent {
  eventSeq += 1
  return { id: eventSeq, tick, ...partial }
}

const FRESH = {
  tick: 0,
  playing: false,
  tasks: initialTasks(),
  decisions: initialDecisions(),
  assignments: initialAssignments(),
  proposals: initialProposals(),
  insights: initialInsights(),
  artifacts: [] as ArtifactInstance[],
  events: [] as SimEvent[],
  assistant: [WELCOME],
  ledger: SEED_LEDGER,
  selectedTaskId: null,
  selectedAssetId: null,
  viewedStageId: null,
  panels: { activity: false, assistant: false },
}

export const useSimStore = create<SimStore>((set, get) => ({
  ...FRESH,

  play: () => set({ playing: true }),
  pause: () => set({ playing: false }),
  selectTask: (id) => set({ selectedTaskId: id }),
  selectAsset: (id) => set({ selectedAssetId: id }),
  setViewedStage: (id) => set({ viewedStageId: id }),
  togglePanel: (which, open) =>
    set((s) => ({ panels: { ...s.panels, [which]: open ?? !s.panels[which] } })),

  reset: () => set({ ...FRESH, tasks: initialTasks(), decisions: initialDecisions(), assignments: initialAssignments(), proposals: initialProposals(), insights: initialInsights(), artifacts: [], events: [], assistant: [WELCOME] }),

  stepTick: () => {
    const state = get()
    const tick = state.tick + 1
    const tasks = { ...state.tasks }
    const decisions = { ...state.decisions }
    const assignments = { ...state.assignments }
    const insights = { ...state.insights }
    const newArtifacts: ArtifactInstance[] = []
    const newEvents: SimEvent[] = []

    const isDone = (id: string) => tasks[id]?.status === 'done'

    const surfaceAfter = (taskId: string) => {
      for (const p of PROPOSALS) {
        if (p.afterTask === taskId && state.proposals[p.id]?.status === 'open') {
          newEvents.push(makeEvent(tick, { agent: p.sourceAgent, taskId, type: 'suggestion', message: `Suggested change ready for review: ${p.title}` }))
        }
      }
      for (const ib of INSIGHTS) {
        if (ib.afterTask === taskId && insights[ib.id]?.status === 'new' && !insights[ib.id]?.surfacedAtTick) {
          insights[ib.id] = { ...insights[ib.id], surfacedAtTick: tick }
          newEvents.push(makeEvent(tick, { agent: 'control', taskId, type: 'finding', message: `AI noticed something: ${ib.title}` }))
        }
      }
    }

    for (const bp of TASKS) {
      const rt = tasks[bp.id]
      if (rt.status === 'pending') {
        if (bp.dependsOn.every(isDone)) tasks[bp.id] = { ...rt, status: 'ready' }
      } else if (rt.status === 'ready') {
        if (bp.assignment) {
          tasks[bp.id] = { ...rt, status: 'awaiting_human', startedTick: tick }
          assignments[bp.assignment.id] = { ...assignments[bp.assignment.id], status: 'open' }
          newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'decision_open', message: `Needs your input: ${bp.assignment.title}` }))
        } else if (bp.decision) {
          tasks[bp.id] = { ...rt, status: 'awaiting_human', startedTick: tick }
          decisions[bp.decision.id] = { ...decisions[bp.decision.id], status: 'open', openedAtTick: tick }
          // Drafts under review must exist before the decision can be made
          for (const aid of bp.produces) {
            const blueprint = ARTIFACT_MAP.get(aid)
            const exists = state.artifacts.some((a) => a.id === aid) || newArtifacts.some((a) => a.id === aid)
            if (!blueprint || exists) continue
            newArtifacts.push({ ...blueprint, version: rt.runs, state: 'draft', producedByAgent: bp.agent, producedAtTick: tick })
            newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'artifact', message: `Draft ready for review: ${blueprint.name} v${rt.runs}` }))
          }
          newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'decision_open', message: `Needs your decision: ${bp.decision.title}` }))
        } else {
          tasks[bp.id] = { ...rt, status: 'running', startedTick: tick }
          newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'task_start', message: `${AGENTS[bp.agent].name} started ${bp.id} ${bp.name}` }))
        }
      } else if (rt.status === 'running') {
        const progress = Math.min(100, rt.progress + 100 / bp.duration)
        if (progress >= 100) {
          for (const aid of bp.produces) {
            const blueprint = ARTIFACT_MAP.get(aid)
            if (!blueprint) continue
            newArtifacts.push({ ...blueprint, version: rt.runs, state: bp.decision ? 'draft' : INITIAL_STATE_BY_CLASS[bp.class], producedByAgent: bp.agent, producedAtTick: tick })
            newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'artifact', message: `New asset: ${blueprint.name} v${rt.runs}` }))
          }
          if (bp.decision) {
            tasks[bp.id] = { ...rt, status: 'awaiting_human', progress: 100 }
            decisions[bp.decision.id] = { ...decisions[bp.decision.id], status: 'open', openedAtTick: tick }
            newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'decision_open', message: `Back for your decision: ${bp.decision.title}` }))
          } else {
            tasks[bp.id] = { ...rt, status: 'done', progress: 100, finishedTick: tick }
            newEvents.push(makeEvent(tick, { agent: bp.agent, taskId: bp.id, type: 'task_done', message: `${bp.id} ${bp.name} — done` }))
            surfaceAfter(bp.id)
          }
        } else {
          tasks[bp.id] = { ...rt, progress }
        }
      }
    }

    const allDone = TASKS.every((t) => tasks[t.id].status === 'done')
    if (allDone) {
      newEvents.push(makeEvent(tick, { agent: 'control', type: 'info', message: 'All steps complete — project delivered. Knowledge capture review is next.' }))
    }

    let artifacts = state.artifacts
    if (newArtifacts.length) {
      const replaced = new Set(newArtifacts.map((a) => a.id))
      artifacts = [...state.artifacts.filter((a) => !replaced.has(a.id)), ...newArtifacts]
    }

    set({
      tick,
      playing: allDone ? false : state.playing,
      tasks,
      decisions,
      assignments,
      insights,
      artifacts,
      events: newEvents.length ? [...newEvents.reverse(), ...state.events].slice(0, 400) : state.events,
    })
  },

  submitAssignment: (taskId, note) => {
    const state = get()
    const task = TASKS.find((t) => t.id === taskId)
    if (!task?.assignment) return
    const tick = state.tick
    const tasks = { ...state.tasks }
    const assignments = { ...state.assignments }
    const newArtifacts: ArtifactInstance[] = []

    tasks[taskId] = { ...tasks[taskId], status: 'done', progress: 100, finishedTick: tick }
    assignments[task.assignment.id] = { status: 'submitted', submittedAtTick: tick, note }

    for (const aid of task.produces) {
      const blueprint = ARTIFACT_MAP.get(aid)
      if (!blueprint || state.artifacts.some((a) => a.id === aid)) continue
      // Human-provided material lands confirmed
      newArtifacts.push({ ...blueprint, version: 1, state: 'confirmed', producedByAgent: task.agent, producedAtTick: tick })
    }

    set({
      tasks,
      assignments,
      artifacts: [...state.artifacts, ...newArtifacts],
      events: [
        makeEvent(tick, { agent: task.agent, taskId, type: 'decision_resolved', message: `Provided: ${task.assignment.title}${note ? ` — ${note}` : ''}` }),
        ...newArtifacts.map((a) => makeEvent(tick, { agent: task.agent, taskId, type: 'artifact', message: `New asset: ${a.name} v${a.version}` })),
        ...state.events,
      ].slice(0, 400),
    })
  },

  resolveDecision: (decisionId, optionId, note) => {
    const state = get()
    const task = TASKS.find((t) => t.decision?.id === decisionId)
    if (!task?.decision) return
    const decision = task.decision
    const tick = state.tick
    const tasks = { ...state.tasks }
    const decisions = { ...state.decisions }
    let artifacts = state.artifacts
    const newEvents: SimEvent[] = []
    const option = decision.options.find((o) => o.id === optionId)

    const isRework = decision.reworkOptionId === optionId && decision.reworkTaskId
    if (isRework) {
      const reworkId = decision.reworkTaskId!
      const affected = downstreamOf(reworkId)
      tasks[reworkId] = { status: 'running', progress: 0, runs: tasks[reworkId].runs + 1, startedTick: tick }
      if (reworkId !== task.id) tasks[task.id] = { ...tasks[task.id], status: 'pending', progress: 0 }
      for (const id of affected) tasks[id] = { ...tasks[id], status: 'pending', progress: 0 }
      decisions[decisionId] = { status: 'idle', resolution: { optionId, note, decidedAtTick: tick } }
      const reworkName = TASK_MAP.get(reworkId)?.name ?? reworkId
      newEvents.push(makeEvent(tick, { agent: 'control', taskId: task.id, type: 'decision_resolved', message: `Sent back: ${decision.title} → redoing ${reworkName}${note ? ` — ${note}` : ''}` }))
    } else {
      tasks[task.id] = { ...tasks[task.id], status: 'done', progress: 100, finishedTick: tick }
      decisions[decisionId] = { ...decisions[decisionId], status: 'resolved', resolution: { optionId, note, decidedAtTick: tick } }
      const evidenceIds = new Set(decision.evidence.map((e) => e.artifactId))
      artifacts = state.artifacts.map((a) => (evidenceIds.has(a.id) && a.state !== 'confirmed' ? { ...a, state: 'confirmed' as ArtifactState } : a))
      newEvents.push(makeEvent(tick, { agent: 'control', taskId: task.id, type: 'decision_resolved', message: `Decided: ${decision.title} → ${option?.label ?? optionId}${note ? ` — ${note}` : ''}` }))
    }

    set({ tasks, decisions, artifacts, events: [...newEvents, ...state.events].slice(0, 400) })
  },

  resolveProposal: (proposalId, accept) => {
    const state = get()
    const bp = PROPOSALS.find((p) => p.id === proposalId)
    if (!bp || state.proposals[proposalId]?.status !== 'open') return
    const tick = state.tick
    let artifacts = state.artifacts
    let ledger = state.ledger
    if (accept) {
      artifacts = state.artifacts.map((a) => (a.id === bp.targetArtifactId ? { ...a, version: a.version + 1, state: 'confirmed' as ArtifactState } : a))
      const entry = PROPOSAL_LEDGER[proposalId]
      if (entry && !ledger.some((l) => l.id === `l-${proposalId}`)) {
        ledger = [{ ...entry, id: `l-${proposalId}`, day: tick }, ...ledger]
      }
    }
    set({
      proposals: { ...state.proposals, [proposalId]: { status: accept ? 'accepted' : 'dismissed', decidedAtTick: tick } },
      artifacts,
      ledger,
      events: [makeEvent(tick, { agent: bp.sourceAgent, type: 'suggestion', message: accept ? `Change applied: ${bp.title}` : `Change set aside: ${bp.title}` }), ...state.events].slice(0, 400),
    })
  },

  resolveInsight: (insightId, actioned) => {
    const state = get()
    set({ insights: { ...state.insights, [insightId]: { ...state.insights[insightId], status: actioned ? 'actioned' : 'dismissed' } } })
  },

  askAssistant: (text) => {
    const state = get()
    const lower = text.toLowerCase()
    const hit = ASSISTANT_SCRIPT.find((e) => e.match.some((m) => lower.includes(m.toLowerCase())))
    const reply: AssistantTurn = hit ? { role: 'assistant', text: hit.answer, evidence: hit.evidence } : { role: 'assistant', text: ASSISTANT_FALLBACK }
    set({ assistant: [...state.assistant, { role: 'user', text }, reply] })
  },
}))

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
