import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useSimStore } from '../../store/useSimStore'
import type { ToolInvocation } from '../../lib/types'
import { cn } from '../../lib/cn'
import { Tooltip } from '../ui/misc'
import { formatDuration, invocationsForTask, STATUS_META } from './tool-language'

function Chip({ v }: { v: ToolInvocation }) {
  const { projectId } = useParams<{ projectId: string }>()
  const status = STATUS_META[v.status]
  return (
    <Tooltip
      content={
        <span className="block max-w-xs space-y-0.5">
          <span className="block font-medium">{v.toolName}</span>
          <span className="block text-muted-foreground">In · {v.argsSummary || '—'}</span>
          <span className="block text-muted-foreground">
            Out · {v.status === 'error' ? v.error : v.resultSummary || '—'}
          </span>
        </span>
      }
    >
      <Link
        to={`/p/${projectId}/tools/${encodeURIComponent(v.toolId)}`}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-muted/40 py-1 pl-2 pr-2.5',
          'text-[11px] transition-colors hover:border-border hover:bg-muted',
        )}
      >
        <span className={cn('size-1.5 shrink-0 rounded-full', status.dot)} aria-hidden />
        <span className="font-medium">{v.toolName}</span>
        <span className="font-mono text-[10px] text-muted-foreground">{formatDuration(v.durationMs)}</span>
      </Link>
    </Tooltip>
  )
}

/**
 * The explicit tool-call trace for one task — which checks ran, on what, how
 * long they took. Renders nothing when the task called no registered tool.
 */
export function ToolTrace({ taskId, className }: { taskId: string; className?: string }) {
  const all = useSimStore((s) => s.toolInvocations)
  const items = useMemo(() => invocationsForTask(all, taskId), [all, taskId])
  if (!items.length) return null
  return (
    <section className={cn('space-y-2', className)} aria-label="Tool calls">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Tools called · {items.length}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {items.map((v) => (
          <Chip key={v.id} v={v} />
        ))}
      </div>
    </section>
  )
}
