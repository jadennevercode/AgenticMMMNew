import type { TaskFinding, TaskStep } from './types'

/**
 * Per-task transparency data (process trace + grounded findings) is now
 * produced at runtime by the backend and arrives via /api/state →
 * store.findings. Components read findings from the store; the run trace is
 * derived from the event stream filtered by task id.
 *
 * These maps are kept as EMPTY stubs only for type compatibility — no mock
 * content is shipped as a runtime data source.
 */

export const TASK_TRACE: Record<string, TaskStep[]> = {}

export const TASK_FINDINGS: Record<string, TaskFinding[]> = {}
