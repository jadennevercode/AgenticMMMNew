import { useCallback, useEffect, useState } from 'react'
import {
  BookMarked, Check, CheckCircle2, CircleSlash, Copy, Download, FileCode, Loader2,
  Rocket, XCircle,
} from 'lucide-react'
import type { CompiledSql, DataAsset, Indicator } from '../../../lib/types'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'
import { Card } from '../../ui/card'
import { Button } from '../../ui/button'
import { cn } from '../../../lib/cn'

interface CheckRow {
  ok: boolean | null // null = unknown yet
  label: string
  detail: string
}

export function PublishPanel({ asset }: { asset: DataAsset }) {
  const pid = useSimStore((s) => s.activeProjectId)
  const busy = useSimStore((s) => s.dataAssetBusy) === asset.id
  const { dbtPublish } = useSimStore.getState()

  const [indicators, setIndicators] = useState<Indicator[]>([])
  const summary = asset.dbt ?? null
  const conf = summary?.conformance ?? null

  const load = useCallback(async () => {
    if (!pid) return
    const inds = await api.getIndicators(pid)
    setIndicators(inds.filter((i) => i.assetId === asset.id))
  }, [pid, asset.id])
  useEffect(() => { void load() }, [load, asset.updatedAt])

  const enumBad = conf?.enumViolations ?? []
  const fieldDetail = !conf?.checked
    ? 'Mart not materialised yet — run a build in the Transform step.'
    : conf.missingRequired.length > 0
      ? `Missing required columns: ${conf.missingRequired.join(', ')}`
      : conf.extra.length > 0
        ? `Extra columns not in schema: ${conf.extra.join(', ')} (dropped downstream)`
        : 'Every required column present; no stray columns.'
  const enumDetail = !conf?.checked
    ? 'Mart not materialised yet.'
    : enumBad.length > 0
      ? enumBad.map((v) => `${v.column}: ${v.values.slice(0, 6).join(', ')}`).join(' · ')
      : conf.unenforcedDimensions.length > 0
        ? `In-vocabulary. Not enforced (no standard values set): ${conf.unenforcedDimensions.join(', ')}`
        : 'All dimension values map to the schema’s standard values.'

  const checks: CheckRow[] = [
    {
      ok: summary ? summary.ok : null,
      label: 'Build & data-quality checks',
      detail: summary
        ? (summary.ok ? `${summary.passed} checks passed` : summary.error || `${summary.failed} check(s) failed`)
        : 'Not built yet — run a build in the Transform step.',
    },
    {
      ok: !conf?.checked ? null : conf.missingRequired.length === 0,
      label: 'Field mapping — target schema',
      detail: fieldDetail,
    },
    {
      ok: !conf?.checked ? null : enumBad.length === 0,
      label: 'Enum mapping — standard values',
      detail: enumDetail,
    },
    {
      ok: summary?.mart ? true : null,
      label: 'Output model',
      detail: summary?.mart ? `Publishing mart "${summary.mart}" as parquet v${asset.latestVersion + 1}.` : 'No output (marts) model.',
    },
  ]
  const publishable = summary?.ok === true && conf?.ok === true && !!summary?.mart

  async function publish() {
    await dbtPublish(asset.id)
    await load()
  }

  return (
    <div className="space-y-4">
      {/* ── checklist ── */}
      <Card className="p-0">
        <div className="border-b border-border px-4 py-2.5">
          <h3 className="text-sm font-semibold">Pre-publish checklist</h3>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            Publishing re-runs the build and is blocked unless everything below is green.
          </p>
        </div>
        <ul className="divide-y divide-border">
          {checks.map((c) => (
            <li key={c.label} className="flex items-start gap-2.5 px-4 py-2.5 text-[12px]">
              {c.ok === true ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" />
                : c.ok === false ? <XCircle className="mt-0.5 size-4 shrink-0 text-rose-500" />
                : <CircleSlash className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
              <div className="min-w-0">
                <p className="font-medium">{c.label}</p>
                <p className={cn('text-[11px]', c.ok === false ? 'text-rose-600' : 'text-muted-foreground')}>{c.detail}</p>
              </div>
            </li>
          ))}
        </ul>
        <div className="flex items-center justify-between border-t border-border px-4 py-3">
          <span className="text-[11px] text-muted-foreground">
            The published mart feeds the unified long table (S2–S5) and registers indicators below.
          </span>
          <Button onClick={() => void publish()} disabled={busy || !publishable}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}
            Publish v{asset.latestVersion + 1}
          </Button>
        </div>
      </Card>

      <CompiledSqlCard asset={asset} />

      {/* ── indicators registered by this asset ── */}
      <Card className="p-0">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2">
          <BookMarked className="size-4 text-primary" />
          <h4 className="text-[13px] font-semibold">Indicators from this asset</h4>
          <span className="ml-auto text-[11px] text-muted-foreground">{indicators.length} registered</span>
        </div>
        {indicators.length === 0 ? (
          <p className="px-4 py-5 text-center text-[12px] text-muted-foreground">
            None yet — indicators (metric × factor path) register on publish.
          </p>
        ) : (
          <table className="w-full border-collapse text-[12px]">
            <thead className="bg-muted/60 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 font-medium">Metric</th>
                <th className="px-3 py-1.5 font-medium">Role</th>
                <th className="px-3 py-1.5 font-medium">Factor path</th>
                <th className="px-3 py-1.5 font-medium">Coverage</th>
                <th className="px-3 py-1.5 text-right font-medium">Rows</th>
              </tr>
            </thead>
            <tbody>
              {indicators.map((ind) => (
                <tr key={ind.id} className="border-t border-border">
                  <td className="px-3 py-1.5 font-medium">{ind.metric}</td>
                  <td className="px-3 py-1.5">{ind.metricType}</td>
                  <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                    {[ind.l1, ind.l2, ind.l3, ind.l4].filter(Boolean).join(' › ') || '—'}
                  </td>
                  <td className="px-3 py-1.5 tabular-nums text-muted-foreground">{ind.coverageStart} → {ind.coverageEnd}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{ind.rows.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* ── version history ── */}
      {asset.versions.length > 0 && (
        <Card className="overflow-hidden p-0">
          <div className="border-b border-border px-4 py-2 text-sm font-semibold">Version history</div>
          <table className="w-full border-collapse text-[12px]">
            <thead className="bg-muted/60 text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-1.5 font-medium">Version</th>
                <th className="px-3 py-1.5 text-right font-medium">Rows</th>
                <th className="px-3 py-1.5 text-right font-medium">Columns</th>
                <th className="px-3 py-1.5 font-medium">Produced</th>
              </tr>
            </thead>
            <tbody>
              {[...asset.versions].reverse().map((v) => (
                <tr key={v.version} className="border-t border-border">
                  <td className="px-3 py-1.5">v{v.version}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{v.rowCount.toLocaleString()}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{v.columns.length}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{v.producedAt.replace('T', ' ').slice(0, 16)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

/**
 * The whole transform, as one SQL statement.
 *
 * The pipeline is a stack of typed steps because that is what a person can review
 * and change — but "what does this asset actually do to the data?" is a question
 * best answered in one place, in the language the answer is really written in. It
 * compiles from the same templates the build runs, so it cannot describe something
 * the pipeline does not do, and it exports for review outside this product.
 */
function CompiledSqlCard({ asset }: { asset: DataAsset }) {
  const pid = useSimStore((s) => s.activeProjectId)
  const [sql, setSql] = useState<CompiledSql | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const load = useCallback(async () => {
    if (!pid) return
    setLoading(true)
    try { setSql(await api.pipelineFullSql(pid, asset.id, null)) }
    catch (e) {
      setSql({ ok: false, sql: '', error: e instanceof Error ? e.message : 'Could not compile the pipeline.' })
    } finally { setLoading(false) }
  }, [pid, asset.id])
  useEffect(() => { void load() }, [load, asset.updatedAt])

  function download() {
    if (!sql?.sql) return
    const url = URL.createObjectURL(new Blob([sql.sql], { type: 'text/plain;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${asset.name.replace(/[^0-9a-zA-Z_-]+/g, '_').toLowerCase() || 'asset'}.sql`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function copy() {
    if (!sql?.sql) return
    await navigator.clipboard.writeText(sql.sql)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  const lines = sql?.sql ? sql.sql.split('\n').length : 0

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
        <FileCode className="size-4 text-primary" />
        <h4 className="text-[13px] font-semibold">Compiled SQL</h4>
        <span className="text-[11px] text-muted-foreground">
          {loading ? 'compiling…'
            : sql?.ok ? `${asset.pipeline?.steps.length ?? 0} steps → 1 statement · ${lines} lines`
              : 'not available'}
        </span>
        <div className="ml-auto flex items-center gap-1">
          {sql?.ok && (
            <>
              <Button size="sm" variant="ghost" onClick={() => void copy()}>
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copied ? 'Copied' : 'Copy'}
              </Button>
              <Button size="sm" variant="outline" onClick={download}>
                <Download className="size-3.5" />Export .sql
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}>
                {open ? 'Hide' : 'Show'}
              </Button>
            </>
          )}
        </div>
      </div>
      {sql && !sql.ok && (
        <p className="px-4 py-3 text-[11px] text-rose-700">{sql.error}</p>
      )}
      {sql?.ok && !open && (
        <p className="px-4 py-3 text-[11px] text-muted-foreground">
          Every step of the transform, compiled into one self-contained statement — the same
          compilation the build runs. The header records which file and sheet each input reads.
        </p>
      )}
      {sql?.ok && open && (
        <pre className="max-h-96 overflow-auto bg-muted/40 px-4 py-3 font-mono text-[11px] leading-relaxed">
          {sql.sql}
        </pre>
      )}
    </Card>
  )
}
