import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronRight, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import type { ToolSpec } from '../../lib/types'
import { SectionHeader } from '../ui/primitives'
import { cn } from '../../lib/cn'
import { CATEGORY_META } from './tool-language'

function ToolRow({ spec, calls, to }: { spec: ToolSpec; calls: number; to: string }) {
  const meta = CATEGORY_META[spec.category]
  return (
    <Link
      to={to}
      className={cn(
        'group flex items-start gap-4 border-b border-border/60 px-4 py-4 last:border-0',
        'transition-colors hover:bg-muted/40',
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-[14px] font-semibold tracking-tight">{spec.name}</h3>
          <code className="font-mono text-[10px] text-muted-foreground">{spec.id}</code>
          <span className={cn('font-mono text-[10px] uppercase tracking-[0.12em]', meta.accent)}>
            {meta.label}
          </span>
        </div>
        <p className="mt-1.5 line-clamp-2 max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          {spec.description}
        </p>
      </div>

      <div className="hidden w-44 shrink-0 pt-0.5 text-right text-[11px] text-muted-foreground sm:block">
        <p>
          Used by{' '}
          {spec.usedBy.map((id, i) => (
            <span key={id}>
              {i > 0 && ', '}
              <span className="font-mono text-foreground">{id}</span>
            </span>
          ))}
        </p>
        <p className="mt-0.5">{calls === 0 ? 'No calls yet' : `${calls} call${calls === 1 ? '' : 's'}`}</p>
      </div>

      <ChevronRight className="mt-1 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}

/** The Tools module — a flat registry of every tool the workflow can call. */
export default function ToolsView() {
  const { projectId } = useParams<{ projectId: string }>()
  const [specs, setSpecs] = useState<ToolSpec[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const invocations = useSimStore((s) => s.toolInvocations)

  useEffect(() => {
    let live = true
    api
      .listTools()
      .then((t) => live && setSpecs(t))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : 'Request failed'))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [])

  const callsByTool = useMemo(() => {
    const out: Record<string, number> = {}
    for (const v of invocations) out[v.toolId] = (out[v.toolId] ?? 0) + 1
    return out
  }, [invocations])

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <SectionHeader
        kicker="Analysis tools"
        title="Tools"
        right={
          <p className="max-w-xs text-right text-[12px] leading-relaxed text-muted-foreground">
            Every quality check, statistical test and regression the workflow runs is a registered tool —
            called explicitly, and traced per call.
          </p>
        }
      />

      {loading && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading the registry…
        </p>
      )}
      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      {specs.length > 0 && (
        <div className="rounded-lg border border-border bg-card">
          {specs.map((s) => (
            <ToolRow
              key={s.id}
              spec={s}
              calls={callsByTool[s.id] ?? 0}
              to={`/p/${projectId}/tools/${encodeURIComponent(s.id)}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
