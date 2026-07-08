import { TASKS } from './scenario'
import { ARTIFACTS, ARTIFACT_MAP } from './artifacts-data'
import type { ArtifactState, DeliverableState, TaskBlueprint, TaskRuntime } from './types'

/**
 * Artifact-driven derivation layer.
 *
 * The product is organised as Stage → Artifact → the process steps that
 * build that artifact. This module derives, for any artifact, the ordered
 * chain of tasks that produce and finalise it, plus a board-level state —
 * all from existing blueprints (scenario.ts / artifacts-data.ts). No flow
 * definition is duplicated here.
 */

const chainCache = new Map<string, TaskBlueprint[]>()

/**
 * Tasks that build an artifact, in run order. Starts at the producer (the task
 * whose `produces` includes it) and walks forward along the dependency chain,
 * pulling in every following step that either produces nothing (confirm /
 * sign-off / export) or re-produces this same artifact (refines another sheet).
 * It stops when a step branches off to a different deliverable. This lets one
 * workbook (e.g. Factor Tree & Data Request) carry a multi-step build process.
 */
export function buildChain(artifactId: string): TaskBlueprint[] {
  const cached = chainCache.get(artifactId)
  if (cached) return cached

  const producer =
    TASKS.find((t) => t.produces.includes(artifactId)) ??
    TASKS.find((t) => t.id === ARTIFACT_MAP.get(artifactId)?.taskRef)

  const chain: TaskBlueprint[] = []
  if (producer) {
    // Backward: absorb input-gathering steps — tasks that produce only internal
    // inputs (SOW upload, reports upload, knowledge assembly) — as the first
    // build steps of this deliverable, so their human touchpoints live here.
    const producesOnlyInternal = (t: TaskBlueprint) =>
      t.produces.length > 0 && t.produces.every((pid) => ARTIFACT_MAP.get(pid)?.internal)
    const pre: TaskBlueprint[] = []
    let cursor: TaskBlueprint | undefined = producer
    while (cursor) {
      const dep: TaskBlueprint | undefined = cursor.dependsOn
        .map((id) => TASKS.find((t) => t.id === id))
        .find((d): d is TaskBlueprint => !!d && producesOnlyInternal(d) && !pre.some((p) => p.id === d.id))
      if (!dep) break
      pre.unshift(dep)
      cursor = dep
    }
    chain.push(...pre, producer)

    // Forward: confirm / sign-off / export steps and same-artifact refinements.
    let advanced = true
    while (advanced) {
      advanced = false
      const last = chain[chain.length - 1]
      for (const t of TASKS) {
        if (chain.some((c) => c.id === t.id)) continue
        if (!t.dependsOn.includes(last.id)) continue
        if (t.produces.length > 0 && !t.produces.includes(artifactId)) continue
        chain.push(t)
        advanced = true
        break
      }
    }
  }
  chainCache.set(artifactId, chain)
  return chain
}

/** The artifact this task contributes to (for cross-navigation from the canvas) */
export function artifactForTask(taskId: string): string | null {
  for (const a of ARTIFACTS) {
    if (buildChain(a.id).some((t) => t.id === taskId)) return a.id
  }
  return null
}

/** Upstream artifacts this one draws on */
export function drawsOn(artifactId: string): string[] {
  return ARTIFACT_MAP.get(artifactId)?.lineage ?? []
}

/** Artifacts that consume this one */
export function feedsInto(artifactId: string): string[] {
  return ARTIFACTS.filter((a) => a.lineage.includes(artifactId)).map((a) => a.id)
}

/** Board-level state from the build chain + the produced instance (if any) */
export function deliverableState(
  artifactId: string,
  tasks: Record<string, TaskRuntime>,
  instanceState?: ArtifactState,
): DeliverableState {
  const chain = buildChain(artifactId)
  if (!chain.length) return instanceState ? 'ready' : 'locked'

  const statuses = chain.map((t) => tasks[t.id]?.status ?? 'pending')
  if (statuses.includes('awaiting_human')) return 'needs-you'
  if (statuses.includes('running')) return 'building'

  const allDone = statuses.every((s) => s === 'done')
  if (allDone) return instanceState === 'confirmed' || instanceState === 'frozen' ? 'confirmed' : 'ready'

  if (statuses.some((s) => s === 'done')) return 'building'
  if (statuses[0] === 'ready') return 'queued'
  return 'locked'
}

/** Completed steps / total — for the column progress hint */
export function chainProgress(artifactId: string, tasks: Record<string, TaskRuntime>): { done: number; total: number } {
  const chain = buildChain(artifactId)
  const done = chain.filter((t) => tasks[t.id]?.status === 'done').length
  return { done, total: chain.length }
}
