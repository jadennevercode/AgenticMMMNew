import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, BookMarked, CheckCircle2, CircleDashed, EyeOff, Loader2, RotateCcw } from 'lucide-react'
import type { FactorMap, FactorMapRow, Indicator } from '../../lib/types'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import { Card } from '../ui/card'
import { cn } from '../../lib/cn'

const ROLE_STYLE: Record<string, string> = {
  Y: 'bg-emerald-500/10 text-emerald-700',
  spending: 'bg-amber-500/10 text-amber-700',
  X: 'bg-sky-500/10 text-sky-700',
}

const STATUS_STYLE: Record<FactorMapRow['status'], string> = {
  mapped: 'bg-emerald-500/10 text-emerald-700',
  ignored: 'bg-muted text-muted-foreground',
  pending: 'bg-amber-500/10 text-amber-700',
}

function fmtPeriod(v: string): string {
  if (/^\d{6}$/.test(v)) return `${v.slice(0, 4)}-${v.slice(4)}`
  return v || '—'
}

function StatusBadge({ status }: { status: FactorMapRow['status'] }) {
  const Icon = status === 'mapped' ? CheckCircle2 : status === 'ignored' ? EyeOff : CircleDashed
  return (
    <span className={cn('inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium', STATUS_STYLE[status])}>
      <Icon className="size-3" />{status}
    </span>
  )
}

/**
 * The AI's proposal for a pending factor row: the best candidate up front with
 * its reason, alternates behind a toggle. This is the 2.1 review surface — the
 * human accepts, picks a different candidate, or ignores the row. Before it,
 * resolving a factor meant hand-hunting the whole indicator catalog.
 */
function SuggestionCell({ row, busy, onAccept }: {
  row: FactorMapRow
  busy: boolean
  onAccept: (rowId: string, indicatorId: string) => Promise<void>
}) {
  const [showAll, setShowAll] = useState(false)
  const [best, ...alts] = row.suggestions
  const tone = best.score >= 0.6 ? 'text-emerald-700'
    : best.score >= 0.45 ? 'text-amber-700' : 'text-muted-foreground'

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-baseline gap-1.5">
        <span className="rounded bg-primary/10 px-1 text-[9px] font-medium uppercase text-primary">AI proposes</span>
        <span className="font-medium text-foreground">{best.metric}</span>
        {best.unit && <span className="text-[10px] text-muted-foreground">{best.unit}</span>}
        <span className={cn('font-mono text-[10px]', tone)}>{(best.score * 100).toFixed(0)}%</span>
      </div>
      <p className="text-[11px] leading-snug">{best.reason}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" disabled={busy}
          onClick={() => void onAccept(row.rowId, best.indicatorId)}
          className="inline-flex items-center gap-1 rounded border border-primary/40 bg-primary/5 px-2 py-0.5 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50">
          {busy ? <Loader2 className="size-3 animate-spin" /> : <CheckCircle2 className="size-3" />}
          Accept
        </button>
        {alts.length > 0 && (
          <button type="button" onClick={() => setShowAll((v) => !v)}
            className="text-[11px] text-primary hover:underline">
            {showAll ? 'Hide' : `${alts.length} other candidate${alts.length > 1 ? 's' : ''}`}
          </button>
        )}
      </div>
      {showAll && (
        <ul className="space-y-1 border-l border-border pl-2">
          {alts.map((s) => (
            <li key={s.indicatorId} className="flex flex-wrap items-baseline gap-1.5">
              <button type="button" disabled={busy}
                onClick={() => void onAccept(row.rowId, s.indicatorId)}
                className="text-[11px] font-medium text-primary hover:underline disabled:opacity-50">
                {s.metric}
              </button>
              <span className="font-mono text-[10px] text-muted-foreground">{(s.score * 100).toFixed(0)}%</span>
              <span className="text-[10px] text-muted-foreground">{s.assetName}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function IndicatorCatalogPanel({ onOpenAsset }: { onOpenAsset: (assetId: string) => void }) {
  const pid = useSimStore((s) => s.activeProjectId)
  const [factorMap, setFactorMap] = useState<FactorMap | null>(null)
  const [indicators, setIndicators] = useState<Indicator[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(() => {
    if (!pid) return
    void api.getFactorMap(pid).then(setFactorMap)
    void api.getIndicators(pid).then(setIndicators)
  }, [pid])

  useEffect(() => { refresh() }, [refresh])

  const toggleIgnore = useCallback(async (row: FactorMapRow, ignored: boolean) => {
    if (!pid) return
    setBusy(row.rowId)
    try {
      setFactorMap(await api.setFactorMapIgnore(pid, row.rowId, ignored))
    } finally {
      setBusy(null)
    }
  }, [pid])

  /** Accept a proposal (indicatorId) or release the row to remap it (''). */
  const bind = useCallback(async (rowId: string, indicatorId: string) => {
    if (!pid) return
    setBusy(rowId)
    try {
      setFactorMap(await api.bindFactorMap(pid, rowId, indicatorId))
    } finally {
      setBusy(null)
    }
  }, [pid])

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-5 py-3">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <BookMarked className="size-4 text-primary" />FactorTree ↔ DataAssets mapping
        </h2>
        <p className="mt-0.5 text-[12px] text-muted-foreground">
          Data Intake starts once every factor-tree indicator is resolved — mapped to a published data asset, or explicitly ignored.
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-5">
        {!factorMap ? (
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-4 animate-spin" />Loading…</div>
        ) : factorMap.total === 0 ? (
          <Card className="p-8 text-center text-[12px] text-muted-foreground">
            No confirmed factor tree yet. Complete Business Understanding, then map its indicators to data assets here.
          </Card>
        ) : (
          <Card className="p-0">
            <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2">
              <span className="text-[13px] font-semibold">Indicator mapping</span>
              <span className="ml-auto flex items-center gap-3 text-[11px] text-muted-foreground">
                <span className="text-emerald-700">{factorMap.mapped} mapped</span>
                <span>{factorMap.ignored} ignored</span>
                <span className={factorMap.pending ? 'font-semibold text-amber-700' : ''}>{factorMap.pending} pending</span>
                {factorMap.suggested > 0 && (
                  <span className="text-primary">{factorMap.suggested} AI-proposed</span>
                )}
              </span>
              <span className={cn('rounded px-2 py-0.5 text-[10px] font-semibold',
                factorMap.complete ? 'bg-emerald-500/10 text-emerald-700' : 'bg-amber-500/10 text-amber-700')}>
                {factorMap.complete ? 'Gate ready' : `${factorMap.pending} to resolve`}
              </span>
            </div>
            <table className="w-full border-collapse text-[12px]">
              <thead className="bg-muted/50 text-left text-muted-foreground">
                <tr>
                  <th className="px-4 py-1.5 font-medium">Factor path</th>
                  <th className="px-3 py-1.5 font-medium">Indicator</th>
                  <th className="px-3 py-1.5 font-medium">Status</th>
                  <th className="px-3 py-1.5 font-medium">Data asset / note</th>
                  <th className="px-3 py-1.5 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {factorMap.rows.map((r) => (
                  <tr key={r.rowId} className="border-t border-border align-top">
                    <td className="px-4 py-1.5 font-mono text-[11px] text-muted-foreground">
                      {[r.l1, r.l2, r.l3, r.l4].filter(Boolean).join(' › ') || '—'}
                    </td>
                    <td className="px-3 py-1.5 font-medium">{r.indicator || '—'}</td>
                    <td className="px-3 py-1.5"><StatusBadge status={r.status} /></td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {r.status === 'mapped' ? (
                        <button type="button" onClick={() => onOpenAsset(r.assetId)}
                          className="inline-flex items-center gap-1 font-medium text-primary hover:underline">
                          {r.assetName}<ArrowRight className="size-3" />
                        </button>
                      ) : r.status === 'ignored' ? (
                        <span className="italic">{r.ignoreNote || 'ignored — no data source'}</span>
                      ) : r.suggestions.length > 0 ? (
                        <SuggestionCell row={r} busy={busy === r.rowId} onAccept={bind} />
                      ) : (
                        <span className="inline-flex items-center gap-1 text-amber-700"><AlertTriangle className="size-3" />no candidate found — ignore it, or publish the data</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {r.status === 'mapped' ? (
                        <button type="button" disabled={busy === r.rowId}
                          onClick={() => void bind(r.rowId, '')}
                          className="inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-accent disabled:opacity-50"
                          title="Release this row so a different indicator can be mapped to it">
                          {busy === r.rowId ? <Loader2 className="size-3 animate-spin" /> : <RotateCcw className="size-3" />}
                          Remap
                        </button>
                      ) : (
                        <button type="button" disabled={busy === r.rowId}
                          onClick={() => toggleIgnore(r, r.status !== 'ignored')}
                          className={cn('inline-flex items-center gap-1 rounded border border-border px-2 py-1 text-[11px] font-medium transition-colors hover:bg-accent disabled:opacity-50',
                            r.status === 'ignored' ? 'text-foreground' : 'text-muted-foreground')}>
                          {busy === r.rowId ? <Loader2 className="size-3 animate-spin" />
                            : r.status === 'ignored' ? <RotateCcw className="size-3" /> : <EyeOff className="size-3" />}
                          {r.status === 'ignored' ? 'Restore' : 'Ignore'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}

        {/* ── published indicators (click → asset) ── */}
        {indicators && indicators.length > 0 && (
          <Card className="overflow-hidden p-0">
            <div className="border-b border-border px-4 py-2 text-[13px] font-semibold">Published indicators</div>
            <table className="w-full border-collapse text-[12px]">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Metric</th>
                  <th className="px-3 py-2 font-medium">Role</th>
                  <th className="px-3 py-2 font-medium">Factor path</th>
                  <th className="px-3 py-2 font-medium">Coverage</th>
                  <th className="px-3 py-2 text-right font-medium">Rows</th>
                  <th className="px-3 py-2 font-medium">Source asset</th>
                </tr>
              </thead>
              <tbody>
                {indicators.map((ind) => (
                  <tr key={ind.id}
                    onClick={() => onOpenAsset(ind.assetId)}
                    className="cursor-pointer border-t border-border transition-colors hover:bg-accent">
                    <td className="px-3 py-2 font-medium">{ind.metric}</td>
                    <td className="px-3 py-2">
                      {ind.metricType && (
                        <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-medium', ROLE_STYLE[ind.metricType] ?? 'bg-muted text-muted-foreground')}>
                          {ind.metricType}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-muted-foreground">
                      {[ind.l1, ind.l2, ind.l3, ind.l4].filter(Boolean).join(' › ') || '—'}
                    </td>
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">
                      {fmtPeriod(ind.coverageStart)} → {fmtPeriod(ind.coverageEnd)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{ind.rows.toLocaleString()}</td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1 font-medium text-primary">
                        {ind.assetName}<ArrowRight className="size-3" />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}
