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

/** This task's invocations, in the order they were recorded (oldest-first) —
 *  filtering never reorders `tool_invocations`, which is already append order. */
export function invocationsForTask(all: ToolInvocation[], taskId: string): ToolInvocation[] {
  return all.filter((v) => v.taskId === taskId)
}

/**
 * The registered tools each step is expected to call, in call order.
 *
 * Used only to seed queued placeholders while a task runs — the real timeline is
 * whatever `tool_invocations` reports, so a step that calls something not listed
 * here still renders it, and a step that skips a listed tool just leaves it
 * queued until the run ends.
 *
 * `2.5` proposes the setup only (`build_ols_review(st, fit=False)`, no engine/task
 * id) — `model.ols` is never traced there, only at `2.5r` which actually fits.
 * Listing it under `2.5` would show a permanently queued/spinning "OLS MMM Fit"
 * for the whole step, which is exactly the fabricated state this map exists to
 * avoid.
 */
export const EXPECTED_TOOLS: Record<string, string[]> = {
  '2.2': ['quality.consistency', 'quality.accuracy', 'quality.completeness', 'quality.granularity'],
  '2.4': ['stat.cv', 'stat.pearson', 'stat.vif'],
  '2.5r': ['model.ols'],
}

/** Display name for a tool id we have not seen an invocation for yet. */
export const TOOL_DISPLAY_NAME: Record<string, string> = {
  'quality.consistency': 'Consistency Check',
  'quality.accuracy': 'Accuracy Check',
  'quality.completeness': 'Completeness Check',
  'quality.granularity': 'Granularity Check',
  'stat.cv': 'CV (Volatility)',
  'stat.pearson': 'Pearson Correlation',
  'stat.vif': 'VIF (Collinearity)',
  'model.ols': 'OLS MMM Fit',
}
