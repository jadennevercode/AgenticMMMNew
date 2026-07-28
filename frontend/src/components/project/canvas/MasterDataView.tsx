import { useEffect, useMemo, useState } from 'react'
import { Download, Loader2, TriangleAlert } from 'lucide-react'
import { api } from '../../../api/client'
import { asMasterData } from '../../../lib/artifact-format'
import { exportMasterDataXlsx } from '../../../lib/export'
import { cn } from '../../../lib/cn'
import { useSimStore } from '../../../store/useSimStore'
import type {
  ArtifactInstance,
  MasterDataStation,
  MasterGranularityRow,
} from '../../../lib/types'

/**
 * Master Data (2.6) — the modeling feature table, and the audit trail behind it.
 *
 * Two things the old sheet view could not answer, and this one must:
 *   1. "Show me the wide table for THIS product × channel × region" — the slice
 *      is fetched live rather than baked into the artifact.
 *   2. "Where did my indicator go?" — the funnel names the layer that rejected
 *      each one, and every rejected row opens to its full chain of verdicts.
 */

/* ── 2.32 sheet 1 · Granularity Reference ──────────────── */
function GranularityTable({ rows }: { rows: MasterGranularityRow[] }) {
  const laid = useMemo(
    () => rows.map((r, i, arr) => {
      const prev = arr[i - 1]
      const f1 = !prev || prev.l1 !== r.l1
      const f2 = f1 || prev?.l2 !== r.l2
      const f3 = f2 || prev?.l3 !== r.l3
      return { r, f1, f2, f3 }
    }),
    [rows],
  )
  if (!rows.length) {
    return <p className="px-3 py-6 text-center text-[12px] text-muted-foreground">No factor rows yet.</p>
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full min-w-[820px] border-collapse text-[11.5px]">
        <thead className="bg-muted/50">
          <tr className="text-left text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            <th className="px-2 py-2 font-semibold">L1</th>
            <th className="px-2 py-2 font-medium">L2</th>
            <th className="px-2 py-2 font-medium">L3</th>
            <th className="px-2 py-2 font-medium">L4</th>
            <th className="px-2 py-2 font-medium">指标 · Indicator</th>
            <th className="px-2 py-2 font-medium">渠道 · Channel</th>
            <th className="px-2 py-2 font-medium">区域 · Region</th>
          </tr>
        </thead>
        <tbody>
          {laid.map(({ r, f1, f2, f3 }, i) => (
            <tr key={`${r.l4}|${r.indicator}|${i}`}
              className={cn('border-b border-border/40', f1 && 'border-t border-border/70',
                !r.adopted && 'opacity-45')}>
              <td className={cn('px-2 py-1.5 align-top font-semibold', !f1 && 'text-foreground/45')}>{r.l1 || '—'}</td>
              <td className={cn('px-2 py-1.5 align-top text-foreground/80', !f2 && 'text-foreground/40')}>{r.l2}</td>
              <td className={cn('px-2 py-1.5 align-top text-foreground/70', !f3 && 'text-foreground/40')}>{r.l3}</td>
              <td className="px-2 py-1.5 align-top text-muted-foreground">{r.l4}</td>
              <td className="px-2 py-1.5 align-top font-medium">{r.indicator}</td>
              <td className="px-2 py-1.5 align-top">
                {r.channelScope
                  ? <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-600">{r.channelScope}</span>
                  : <span className="text-muted-foreground/50">— not in model</span>}
              </td>
              <td className="px-2 py-1.5 align-top text-muted-foreground">{r.regionScope || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── 2.32 sheet 2 · Data Station ───────────────────────── */
function DataStationTable({ projectId }: { projectId: string }) {
  const [ds, setDs] = useState<MasterDataStation | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    setLoading(true)
    api.masterDataStation(projectId)
      .then((d) => { if (!cancelled) setDs(d) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [projectId])

  if (loading) return <p className="px-3 py-6 text-center text-[12px] text-muted-foreground">Loading data station…</p>
  if (!ds || !ds.rows.length) {
    return <p className="px-3 py-6 text-center text-[12px] text-muted-foreground">No adopted rows yet — lock the master data at 2.6.</p>
  }
  return (
    <div className="space-y-2">
      {ds.truncated && (
        <p className="flex items-start gap-1.5 rounded-md bg-amber-500/10 px-3 py-1.5 text-[10.5px] text-amber-600">
          <TriangleAlert className="mt-px size-3 shrink-0" />
          Showing the first {ds.rows.length} of {ds.rowCount} rows · Export downloads all of them.
        </p>
      )}
      <div className="max-h-[34rem] overflow-auto rounded-xl border border-border">
        <table className="w-full border-collapse text-[11px]">
          <thead className="sticky top-0 bg-muted/80 backdrop-blur">
            <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              {ds.columns.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {ds.rows.map((row, i) => (
              <tr key={i} className="border-b border-border/40">
                {row.map((cell, j) => (
                  <td key={j} className="whitespace-nowrap px-2 py-1 align-top tabular-nums text-muted-foreground">
                    {cell == null ? '' : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ── the view ──────────────────────────────────────────── */
export function MasterDataView({ inst }: { inst: ArtifactInstance }) {
  const data = asMasterData(inst.body)
  const projectId = useSimStore((s) => s.activeProjectId)
  const [tab, setTab] = useState<'reference' | 'station'>('reference')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  if (!data) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        Master Data is not assembled yet — run task 2.6.
      </div>
    )
  }

  const gref = data.granularityRef ?? []
  const adoptedCount = gref.filter((r) => r.adopted).length

  async function doExport() {
    if (!projectId) return
    setExporting(true)
    setExportError('')
    try {
      await exportMasterDataXlsx(api.masterDataExportUrl(projectId), `model-input-${projectId}.xlsx`)
    } catch (e) {
      setExportError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const tabClass = (id: 'reference' | 'station') =>
    cn(
      'rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors',
      tab === id ? 'bg-accent text-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent/50',
    )

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
      <header className="rounded-xl border border-border bg-muted/30 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold tracking-tight">
            Model Input · {adoptedCount} indicator{adoptedCount === 1 ? '' : 's'} in the national total model
          </h2>
          <button
            type="button"
            onClick={doExport}
            disabled={exporting}
            className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[11px] font-medium transition-colors hover:bg-accent disabled:opacity-50"
          >
            {exporting ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3" />}
            Export .xlsx
          </button>
        </div>
        <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
          The 2.32 model-input deliverable: each factor's model granularity (渠道 scope × 区域), and the
          adopted indicators' long-format data station. Channel is a data-lineage column — the model itself
          is one national total.
        </p>
        {exportError && <p className="mt-1.5 text-[11px] text-rose-600">{exportError}</p>}
      </header>

      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
        <button type="button" onClick={() => setTab('reference')} className={tabClass('reference')}>
          模型颗粒度参考表 · Granularity
        </button>
        <button type="button" onClick={() => setTab('station')} className={tabClass('station')}>
          D.Data Station
        </button>
      </div>

      {tab === 'reference'
        ? <GranularityTable rows={gref} />
        : projectId && <DataStationTable projectId={projectId} />}
    </div>
  )
}
