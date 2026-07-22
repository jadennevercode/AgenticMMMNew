import type { ToolCategory, ToolInvocation, ToolStatus } from '../../lib/types'

export const CATEGORY_META: Record<ToolCategory, { label: string; accent: string }> = {
  quality: {
    label: 'Data Quality',
    accent: 'text-sky-600 dark:text-sky-400',
  },
  statistical: {
    label: 'Statistical Screening',
    accent: 'text-violet-600 dark:text-violet-400',
  },
  model: {
    label: 'Modeling',
    accent: 'text-amber-600 dark:text-amber-400',
  },
}

export const STATUS_META: Record<ToolStatus, { label: string; dot: string; text: string }> = {
  running: { label: 'Running', dot: 'bg-sky-500 animate-pulse', text: 'text-sky-600 dark:text-sky-400' },
  ok: { label: 'Completed', dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400' },
  error: { label: 'Failed', dot: 'bg-rose-500', text: 'text-rose-600 dark:text-rose-400' },
}

/** '<1ms' / '412ms' / '1.4s' — durations read as a metric, so keep them terse. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1) return '<1ms'
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`
}

/** Newest-first invocations for one task (the trace shown beside its artifact). */
export function invocationsForTask(all: ToolInvocation[], taskId: string): ToolInvocation[] {
  return all.filter((v) => v.taskId === taskId)
}
