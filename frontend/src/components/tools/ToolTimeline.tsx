import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'

import { cn } from '../../lib/cn'
import type { ToolInvocation } from '../../lib/types'
import { useSimStore } from '../../store/useSimStore'
import {
  EXPECTED_TOOLS,
  STATUS_META,
  TOOL_DISPLAY_NAME,
  formatDuration,
  invocationsForTask,
} from './tool-language'

interface Line {
  key: string
  toolId: string
  toolName: string
  /** Present once the backend has recorded the call. */
  invocation?: ToolInvocation
}

/**
 * The registered tools a build step called, as an ordered timeline.
 *
 * While the step runs, tools it is expected to call are pre-rendered as queued
 * lines and light up one at a time as the 1.5s state poll brings their
 * invocations back — so the analysis reads as something being performed, not as a
 * result that appeared. Nothing here is fabricated: a queued line carries no
 * numbers, and the moment an invocation lands it replaces the placeholder.
 */
export function ToolTimeline({
  taskId,
  status,
  className,
}: {
  taskId: string
  status: string
  className?: string
}) {
  const { projectId } = useParams()
  const all = useSimStore((s) => s.toolInvocations)
  const [open, setOpen] = useState<Set<string>>(new Set())

  const lines = useMemo<Line[]>(() => {
    const done = invocationsForTask(all, taskId)
    const seen = new Set(done.map((v) => v.toolId))
    const lines: Line[] = done.map((v) => ({
      key: v.id, toolId: v.toolId, toolName: v.toolName, invocation: v,
    }))
    if (status === 'running') {
      for (const toolId of EXPECTED_TOOLS[taskId] ?? []) {
        if (seen.has(toolId)) continue
        lines.push({ key: `queued-${toolId}`, toolId, toolName: TOOL_DISPLAY_NAME[toolId] ?? toolId })
      }
    }
    return lines
  }, [all, taskId, status])

  if (!lines.length) return null

  const firstQueued = lines.find((l) => !l.invocation)?.key

  function toggle(key: string) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <section className={cn('space-y-1', className)} aria-label="Tool calls">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Tools · {lines.filter((l) => l.invocation).length}/{lines.length}
      </p>
      <ol className="space-y-0.5 border-l border-border/60 pl-2">
        {lines.map((l) => {
          const v = l.invocation
          const active = !v && l.key === firstQueued
          const expanded = open.has(l.key)
          return (
            <li key={l.key} className="text-[11px]">
              <div className="flex items-center gap-1.5">
                {v ? (
                  <button type="button" onClick={() => toggle(l.key)}
                    className="text-muted-foreground hover:text-foreground">
                    {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </button>
                ) : active ? (
                  <Loader2 className="h-3 w-3 animate-spin text-sky-500" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />
                )}
                {v ? <span className={cn('h-1.5 w-1.5 rounded-full', STATUS_META[v.status].dot)} /> : null}
                <Link to={`/p/${projectId}/tools/${encodeURIComponent(l.toolId)}`}
                  className={cn('hover:underline', !v && 'text-muted-foreground/70')}>
                  {l.toolName}
                </Link>
                {v ? (
                  <span className="ml-auto tabular-nums text-muted-foreground">
                    {formatDuration(v.durationMs)}
                  </span>
                ) : (
                  <span className="ml-auto text-muted-foreground/60">{active ? 'running' : 'queued'}</span>
                )}
              </div>
              {v && expanded && (
                <dl className="ml-6 mt-0.5 space-y-0.5 text-[10.5px] text-muted-foreground">
                  <div><dt className="inline font-medium">In · </dt><dd className="inline">{v.argsSummary || '—'}</dd></div>
                  <div><dt className="inline font-medium">Out · </dt><dd className="inline">{v.resultSummary || '—'}</dd></div>
                  {v.error && <div className="text-rose-600">{v.error}</div>}
                </dl>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
