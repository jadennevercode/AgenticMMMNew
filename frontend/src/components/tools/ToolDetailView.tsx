import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import type { ToolDetail } from '../../lib/types'
import { TASKS } from '../../lib/scenario'
import { cn } from '../../lib/cn'
import { CATEGORY_META, formatDuration, STATUS_META } from './tool-language'

type TabId = 'overview' | 'code' | 'api' | 'trace'

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'code', label: 'Implementation' },
  { id: 'api', label: 'API' },
  { id: 'trace', label: 'Trace' },
]

function taskLabel(taskId: string): string {
  const t = TASKS.find((x) => x.id === taskId)
  return t ? `${t.id} ${t.name}` : taskId
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-7">
      <h3 className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}

function OverviewTab({ tool }: { tool: ToolDetail }) {
  return (
    <>
      <Block title="When it runs">
        <p className="max-w-3xl text-[13.5px] leading-relaxed">{tool.scenario}</p>
        <p className="mt-2 text-[12px] text-muted-foreground">
          Called by{' '}
          {tool.usedBy.map((id, i) => (
            <span key={id}>
              {i > 0 && ', '}
              <span className="font-mono text-foreground">{taskLabel(id)}</span>
            </span>
          ))}
        </p>
      </Block>

      <Block title="How it computes">
        <p className="max-w-3xl text-[13.5px] leading-relaxed">{tool.method}</p>
        <dl className="mt-3 max-w-3xl space-y-1.5 border-l-2 border-border pl-4 text-[12.5px]">
          <div className="flex gap-2">
            <dt className="w-12 shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">In</dt>
            <dd>{tool.inputSummary}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="w-12 shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Out</dt>
            <dd>{tool.outputSummary}</dd>
          </div>
        </dl>
      </Block>

      {tool.logic.length > 0 && (
        <Block title="Decision logic">
          <ol className="max-w-3xl space-y-2">
            {tool.logic.map((step, i) => (
              <li key={i} className="flex gap-3 text-[13px] leading-relaxed">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border border-border font-mono text-[10px] text-muted-foreground">
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </Block>
      )}

      {tool.params.length > 0 && (
        <Block title="Thresholds & parameters">
          <div className="max-w-3xl overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[520px] text-left text-[12.5px]">
              <thead className="border-b border-border bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Value</th>
                  <th className="px-3 py-2 font-medium">Meaning</th>
                </tr>
              </thead>
              <tbody>
                {tool.params.map((row) => (
                  <tr key={row[0]} className="border-b border-border/50 last:border-0">
                    <td className="px-3 py-2 font-mono text-[11.5px]">{row[0]}</td>
                    <td className="px-3 py-2 font-mono text-[11.5px] text-foreground">{row[1]}</td>
                    <td className="px-3 py-2 text-muted-foreground">{row[2]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Block>
      )}
    </>
  )
}

function CodeTab({ tool }: { tool: ToolDetail }) {
  const src = tool.source
  if (!src) return <p className="text-[13px] text-muted-foreground">No source available.</p>
  return (
    <>
      <Block title="Implementation">
        <p className="max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          The tool is a thin wrapper — this is the function it calls, read from the running backend, so
          it cannot drift from what actually executes.
        </p>
        <p className="mt-2 font-mono text-[11.5px]">
          <span className="text-foreground">{src.path}</span>
          <span className="text-muted-foreground">:{src.line}</span>
          <span className="text-muted-foreground"> · {src.symbol}()</span>
        </p>
      </Block>
      <pre className="overflow-x-auto rounded-lg border border-border bg-muted/30 p-4 font-mono text-[11.5px] leading-[1.6]">
        <code>{src.code}</code>
      </pre>
    </>
  )
}

function ApiTab({ tool }: { tool: ToolDetail }) {
  return (
    <>
      <Block title="How to call it">
        <p className="max-w-3xl text-[13px] leading-relaxed text-muted-foreground">
          Tools are not individually invokable over HTTP: each one is owned by the workflow step that
          runs it, so the API surface is the catalog, this page's data, the run that triggers the call,
          and the trace it leaves behind.
        </p>
      </Block>
      <div className="space-y-3">
        {tool.api.map((c) => (
          <article key={`${c.method}${c.path}`} className="rounded-lg border border-border p-4">
            <header className="flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  'rounded border px-1.5 py-0.5 font-mono text-[10px] font-medium',
                  c.method === 'GET'
                    ? 'border-sky-500/40 text-sky-600 dark:text-sky-400'
                    : 'border-amber-500/40 text-amber-600 dark:text-amber-400',
                )}
              >
                {c.method}
              </span>
              <code className="font-mono text-[12.5px]">{c.path}</code>
            </header>
            <p className="mt-2 text-[12.5px] text-muted-foreground">{c.note}</p>
            {c.example && (
              <pre className="mt-2 overflow-x-auto rounded border border-border bg-muted/30 p-2.5 font-mono text-[11px]">
                <code>{c.example}</code>
              </pre>
            )}
          </article>
        ))}
      </div>
    </>
  )
}

function TraceTab({ toolId }: { toolId: string }) {
  const all = useSimStore((s) => s.toolInvocations)
  const items = useMemo(() => all.filter((v) => v.toolId === toolId), [all, toolId])
  if (!items.length) {
    return (
      <p className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-[13px] text-muted-foreground">
        This tool has not been called yet in this project. Run the step that owns it and every call
        will be recorded here.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[680px] text-left text-[12px]">
        <thead className="border-b border-border bg-muted/40 text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-3 py-2 font-medium">Step</th>
            <th className="px-3 py-2 font-medium">Input</th>
            <th className="px-3 py-2 font-medium">Result</th>
            <th className="px-3 py-2 text-right font-medium">Duration</th>
            <th className="px-3 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((v) => {
            const status = STATUS_META[v.status]
            return (
              <tr key={v.id} className="border-b border-border/50 last:border-0 hover:bg-muted/30">
                <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">{taskLabel(v.taskId)}</td>
                <td className="px-3 py-2 text-muted-foreground">{v.argsSummary || '—'}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  {v.status === 'error' ? v.error : v.resultSummary || '—'}
                </td>
                <td className="px-3 py-2 text-right font-mono">{formatDuration(v.durationMs)}</td>
                <td className={cn('px-3 py-2', status.text)}>
                  <span className="inline-flex items-center gap-1.5">
                    <span className={cn('size-1.5 rounded-full', status.dot)} aria-hidden />
                    {status.label}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function ToolDetailView() {
  const { projectId, toolId = '' } = useParams<{ projectId: string; toolId: string }>()
  const [tool, setTool] = useState<ToolDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('overview')
  const calls = useSimStore((s) => s.toolInvocations.filter((v) => v.toolId === toolId).length)

  useEffect(() => {
    let live = true
    api
      .toolDetail(toolId)
      .then((t) => live && setTool(t))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : 'Request failed'))
    return () => {
      live = false
    }
  }, [toolId])

  // Derive staleness rather than clearing state in the effect: while a different
  // tool's page is loading, the previous tool must not render as if it were this one.
  const current = tool?.id === toolId ? tool : null

  if (error) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
      </div>
    )
  }
  if (!current) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-8">
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </p>
      </div>
    )
  }

  const meta = CATEGORY_META[current.category]

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <Link
        to={`/p/${projectId}/tools`}
        className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> All tools
      </Link>

      <header className="mt-3 border-b border-border pb-5">
        <p className={cn('font-mono text-[10px] uppercase tracking-[0.16em]', meta.accent)}>{meta.label}</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">{current.name}</h2>
        <p className="mt-2 max-w-3xl text-[13.5px] leading-relaxed text-muted-foreground">{current.description}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <code>{current.id}</code>
          <span>v{current.version}</span>
          <span>{calls === 0 ? 'no calls yet' : `${calls} call${calls === 1 ? '' : 's'} recorded`}</span>
        </div>
      </header>

      <nav className="mb-6 flex gap-1 border-b border-border" aria-label="Tool sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-[13px] transition-colors',
              tab === t.id
                ? 'border-foreground font-medium text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
            {t.id === 'trace' && calls > 0 && (
              <span className="ml-1.5 font-mono text-[10px] text-muted-foreground">{calls}</span>
            )}
          </button>
        ))}
      </nav>

      {tab === 'overview' && <OverviewTab tool={current} />}
      {tab === 'code' && <CodeTab tool={current} />}
      {tab === 'api' && <ApiTab tool={current} />}
      {tab === 'trace' && <TraceTab toolId={current.id} />}
    </div>
  )
}
