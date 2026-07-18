import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, CalendarRange, CheckCircle2, Clock, Gauge, Layers, Table2,
} from 'lucide-react'
import type { DataAsset, DbtPreview, FieldProfile, TableReview } from '../../lib/types'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { ReviewChartView } from '../project/charts/ReviewCharts'
import { cn } from '../../lib/cn'

function dtypeColor(dtype: string): string {
  if (dtype === 'datetime' || dtype === 'date') return 'text-primary'
  if (dtype === 'number' || dtype === 'integer') return 'text-emerald-600'
  if (dtype === 'empty') return 'text-muted-foreground'
  return 'text-foreground'
}

type Quality = { ok: boolean; headline: string; detail: string }

/** The four data qualities MMM depends on, judged for a SINGLE dataset. */
function assessQualities(tr: TableReview): { id: string; label: string; icon: typeof Gauge; q: Quality }[] {
  const fields = tr.fields
  const numeric = fields.filter((f) => (f.dtype === 'number' || f.dtype === 'integer') && f.cv != null)
  const timeField = fields.find((f) => f.isTimeAxis)

  const sparse = fields.filter((f) => f.nullRatio > 0.1)
  const minComplete = fields.length ? Math.min(...fields.map((f) => 1 - f.nullRatio)) : 1
  const completeness: Quality = {
    ok: sparse.length === 0,
    headline: `${(minComplete * 100).toFixed(0)}% min. field completeness`,
    detail: sparse.length ? `Sparse: ${sparse.map((f) => f.name).slice(0, 4).join(', ')}` : 'All fields well populated.',
  }
  const g = tr.timeGranularity ?? ''
  const granularity: Quality = {
    ok: ['day', 'week', 'month'].includes(g),
    headline: g ? `Time grain: ${g}` : 'No time axis detected',
    detail: ['day', 'week', 'month'].includes(g) ? 'Fine enough to model.' : 'MMM needs daily / weekly / monthly data.',
  }
  const flat = numeric.filter((f) => (f.cv ?? 0) < 0.01)
  const volatility: Quality = {
    ok: numeric.length > 0 && flat.length === 0,
    headline: flat.length ? `${flat.length} near-constant measure(s)` : numeric.length ? 'Measures vary' : 'No numeric measures',
    detail: flat.length ? `No variation in: ${flat.map((f) => f.name).slice(0, 4).join(', ')}` : numeric.length ? 'Enough variation to estimate effects.' : 'Nothing numeric to model in this table.',
  }
  const cont = timeField?.continuity ?? null
  const gaps = timeField?.gapCount ?? 0
  const consistency: Quality = {
    ok: cont == null || cont >= 0.99,
    headline: cont != null ? `${(cont * 100).toFixed(0)}% period coverage` : 'Continuity not measured',
    detail: cont != null && cont < 0.99 ? `${gaps} missing period(s) — years may not be comparable.` : 'Continuous periods; comparable across years.',
  }
  return [
    { id: 'completeness', label: 'Completeness', icon: Layers, q: completeness },
    { id: 'granularity', label: 'Granularity', icon: Gauge, q: granularity },
    { id: 'volatility', label: 'Volatility', icon: Activity, q: volatility },
    { id: 'consistency', label: 'Consistency', icon: CalendarRange, q: consistency },
  ]
}

function QualityCard({ label, icon: Icon, q }: { label: string; icon: typeof Gauge; q: Quality }) {
  return (
    <Card className={cn('space-y-1.5 p-3.5', q.ok ? 'border-emerald-500/25' : 'border-amber-500/40 bg-amber-500/5')}>
      <div className="flex items-center gap-2">
        <Icon className={cn('size-4', q.ok ? 'text-emerald-600' : 'text-amber-600')} />
        <span className="text-[13px] font-semibold">{label}</span>
        {q.ok ? <CheckCircle2 className="ml-auto size-4 text-emerald-500" /> : <AlertTriangle className="ml-auto size-4 text-amber-500" />}
      </div>
      <p className="text-[12px] font-medium">{q.headline}</p>
      <p className="text-[11px] leading-snug text-muted-foreground">{q.detail}</p>
    </Card>
  )
}

function FieldRow({ f }: { f: FieldProfile }) {
  return (
    <tr className="border-t border-border align-top">
      <td className="px-2 py-1.5 font-medium">
        {f.isTimeAxis && <Clock className="mr-1 inline size-3 text-primary" />}{f.name}
      </td>
      <td className={cn('px-2 py-1.5 font-mono text-[11px] uppercase', dtypeColor(f.dtype))}>{f.dtype}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{(100 - f.nullRatio * 100).toFixed(0)}%</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{f.distinct}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{f.cv != null ? f.cv.toFixed(2) : '—'}</td>
      <td className="px-2 py-1.5">
        {f.enumValues.length > 0 ? (
          <span className="flex flex-wrap gap-1">
            {f.enumValues.map((v) => (
              <span key={v} className="rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px]">{v}</span>
            ))}
          </span>
        ) : (
          <span className="text-muted-foreground">{f.sampleValues.slice(0, 3).join(' · ')}</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-muted-foreground">{f.note}</td>
    </tr>
  )
}

export function ReviewPanel({ asset }: { asset: DataAsset }) {
  const pid = useSimStore((s) => s.activeProjectId)
  const review = asset.review
  const tableReviews = review?.tableReviews ?? []
  const [active, setActive] = useState<string | null>(null)
  const activeName = active && tableReviews.some((t) => t.name === active) ? active : tableReviews[0]?.name ?? null
  const tr = tableReviews.find((t) => t.name === activeName) ?? null
  const qualities = useMemo(() => (tr ? assessQualities(tr) : []), [tr])

  const [preview, setPreview] = useState<{ table: string; data: DbtPreview } | null>(null)
  const loadPreview = useCallback(async (table: string) => {
    if (!pid) return
    try { setPreview({ table, data: await api.rawPreview(pid, asset.id, table) }) } catch { setPreview(null) }
  }, [pid, asset.id])
  useEffect(() => { if (activeName) void loadPreview(activeName) }, [activeName, loadPreview])

  if (!review) {
    return (
      <Card className="p-6 text-center text-sm text-muted-foreground">
        No review yet. Click "Run review" to profile each dataset against the four
        qualities MMM depends on: completeness, granularity, volatility, and consistency.
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* dataset tabs — the review is scoped to one dataset at a time */}
      <div className="flex flex-wrap items-center gap-1.5">
        {tableReviews.map((t) => (
          <button key={t.name} type="button" onClick={() => setActive(t.name)}
            className={cn('rounded-md border px-2.5 py-1 font-mono text-[11px] font-medium transition-colors',
              t.name === activeName ? 'border-primary/50 bg-primary/5 text-primary' : 'border-border text-muted-foreground hover:bg-accent')}>
            {t.name}
            <span className="ml-1.5 text-[10px] opacity-60">{t.rowCount.toLocaleString()} rows</span>
          </button>
        ))}
        {tr && <Badge>{tr.columnCount} fields</Badge>}
      </div>

      {tr && (
        <>
          {/* four qualities for THIS dataset */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {qualities.map((x) => <QualityCard key={x.id} label={x.label} icon={x.icon} q={x.q} />)}
          </div>

          {tr.warnings.length > 0 && (
            <Card className="space-y-1 border-warning/40 bg-warning/5 p-3">
              {tr.warnings.map((w, i) => (
                <p key={i} className="flex items-start gap-1.5 text-[12px] text-foreground">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />{w}
                </p>
              ))}
            </Card>
          )}

          {/* field profiles for THIS dataset */}
          <Card className="overflow-hidden p-0">
            <div className="max-h-[24rem] overflow-auto">
              <table className="w-full border-collapse text-[12px]">
                <thead className="sticky top-0 bg-muted/60">
                  <tr className="text-left text-muted-foreground">
                    <th className="px-2 py-1.5 font-medium">Field</th>
                    <th className="px-2 py-1.5 font-medium">Type</th>
                    <th className="px-2 py-1.5 text-right font-medium">Complete</th>
                    <th className="px-2 py-1.5 text-right font-medium">Distinct</th>
                    <th className="px-2 py-1.5 text-right font-medium">CV</th>
                    <th className="px-2 py-1.5 font-medium">Values</th>
                    <th className="px-2 py-1.5 font-medium">Note</th>
                  </tr>
                </thead>
                <tbody>
                  {tr.fields.map((f) => <FieldRow key={f.name} f={f} />)}
                </tbody>
              </table>
            </div>
          </Card>

          {/* charts for THIS dataset only */}
          {tr.charts.length > 0 && (
            <div className="grid gap-4 lg:grid-cols-2">
              {tr.charts.map((chart) => (
                <Card key={chart.id} className="space-y-2 p-4">
                  <h4 className="text-sm font-semibold">{chart.title}</h4>
                  <ReviewChartView chart={chart} />
                  {chart.interpretation && <p className="text-[11px] text-muted-foreground">{chart.interpretation}</p>}
                </Card>
              ))}
            </div>
          )}

          {/* data preview for THIS dataset */}
          {preview && preview.table === activeName && (
            <Card className="overflow-hidden p-0">
              <div className="flex items-center gap-1.5 border-b border-border px-4 py-2">
                <Table2 className="size-3.5 text-muted-foreground" />
                <h4 className="text-[13px] font-semibold">Data preview</h4>
                <span className="ml-auto text-[11px] text-muted-foreground">{preview.data.rowCount.toLocaleString()} rows</span>
              </div>
              <div className="max-h-72 overflow-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead className="sticky top-0 bg-muted/80 text-left text-muted-foreground backdrop-blur">
                    <tr>{preview.data.columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-1.5 font-medium">{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {preview.data.rows.map((row, ri) => (
                      <tr key={ri} className="border-t border-border">
                        {row.map((cell, ci) => <td key={ci} className="whitespace-nowrap px-3 py-1">{cell}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
