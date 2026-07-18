import { Fragment, useMemo, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { asOlsTree } from '../../../lib/artifact-format'
import { cn } from '../../../lib/cn'
import type {
  ArtifactInstance,
  OlsObjectSummary,
  OlsRowStatus,
  OlsTreeRow,
  OlsTreeSummary,
} from '../../../lib/types'

/* ── formatting helpers ────────────────────────────────── */
const num = (v: number | null, digits = 2): string => (v === null || v === undefined ? '—' : v.toFixed(digits))
const pct = (v: number | null, digits = 1): string => (v === null || v === undefined ? '—' : `${v.toFixed(digits)}%`)

const STATUS_META: Record<OlsRowStatus, { label: string; chip: string }> = {
  inRange: { label: 'In range', chip: 'bg-emerald-500/15 text-emerald-600' },
  review: { label: 'Review', chip: 'bg-amber-500/15 text-amber-600' },
  noBenchmark: { label: 'No benchmark', chip: 'bg-slate-500/15 text-slate-500' },
  notInModel: { label: 'Not in model', chip: 'bg-muted text-muted-foreground' },
  dropped: { label: 'Dropped', chip: 'bg-rose-500/10 text-rose-500' },
}

const SUMMARY_ORDER: { key: OlsRowStatus; label: string; countKey: keyof OlsTreeSummary }[] = [
  { key: 'inRange', label: 'In range', countKey: 'inRange' },
  { key: 'review', label: 'Flagged', countKey: 'flagged' },
  { key: 'noBenchmark', label: 'No benchmark', countKey: 'noBenchmark' },
  { key: 'notInModel', label: 'Not in model', countKey: 'notInModel' },
  { key: 'dropped', label: 'Dropped', countKey: 'dropped' },
]

/* ── fit-metric header cards ───────────────────────────── */
function metricHint(value: number | null, lo: number, hi: number): string {
  if (value === null) return 'text-muted-foreground'
  return value >= lo && value <= hi ? 'text-emerald-600' : 'text-amber-600'
}

function ObjectCard({ o }: { o: OlsObjectSummary }) {
  if (o.error) {
    return (
      <div className="min-w-[210px] shrink-0 rounded-xl border border-rose-500/30 bg-rose-500/5 p-3">
        <div className="text-[13px] font-semibold text-rose-600">{o.object}</div>
        <p className="mt-1 text-[11px] leading-snug text-rose-500/80">{o.error}</p>
      </div>
    )
  }
  const flagged = o.redFlags.length > 0
  return (
    <div className="min-w-[210px] shrink-0 rounded-xl border border-border bg-card p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-semibold">{o.object}</span>
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-[10px] font-medium',
            flagged ? 'bg-amber-500/15 text-amber-600' : 'bg-emerald-500/15 text-emerald-600',
          )}
        >
          {flagged ? `${o.redFlags.length} red flag${o.redFlags.length > 1 ? 's' : ''}` : 'clean'}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">R²</dt>
          <dd className={cn('font-mono font-medium', metricHint(o.r2, 0.85, 0.95))}>{num(o.r2)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Adj R²</dt>
          <dd className="font-mono">{num(o.adjR2)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">MAPE</dt>
          <dd className={cn('font-mono font-medium', metricHint(o.mape, 5, 15))}>{pct(o.mape)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">DW</dt>
          <dd className={cn('font-mono font-medium', metricHint(o.durbinWatson, 1.5, 2.5))}>{num(o.durbinWatson)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Baseline</dt>
          <dd className="font-mono">{pct(o.baselinePct)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Obs / X</dt>
          <dd className="font-mono">{o.nObs} / {o.drivers}</dd>
        </div>
      </dl>
      {(o.yMetric || o.dfRemaining !== null) && (
        <p className="mt-1.5 truncate border-t border-border/60 pt-1.5 text-[10px] text-muted-foreground">
          {o.yMetric && <span title={`Response: ${o.yMetric}`}>Y: {o.yMetric}</span>}
          {o.dfRemaining !== null && o.dfRemaining !== undefined && <span> · {o.dfRemaining} df left</span>}
          {o.controls?.length ? <span> · {o.controls.length} controls</span> : null}
        </p>
      )}
    </div>
  )
}

/* ── range comparison cell ─────────────────────────────── */
function RangeCell({ value, band, status, isPct }: { value: number | null; band: string; status: string; isPct?: boolean }) {
  const chip =
    status === 'in' ? 'bg-emerald-500/15 text-emerald-600' : status === 'out' ? 'bg-rose-500/15 text-rose-600' : 'bg-muted text-muted-foreground'
  return (
    <div className="flex flex-col gap-0.5">
      <span className={cn('inline-flex w-fit items-center rounded px-1.5 py-0.5 font-mono text-[11px]', chip)}>
        {isPct ? pct(value) : num(value)}
      </span>
      <span className="text-[10px] text-muted-foreground">{band || '—'}</span>
    </div>
  )
}

/* ── one factor-tree indicator row (+ expandable per-object results) ── */
function IndicatorRow({ row }: { row: OlsTreeRow }) {
  const [open, setOpen] = useState(false)
  const meta = STATUS_META[row.status]
  const canExpand = row.results.length > 0
  return (
    <>
      <tr
        className={cn(
          'border-b border-border/50 last:border-0 hover:bg-accent/40',
          canExpand && 'cursor-pointer',
          row.status === 'dropped' && 'opacity-60',
        )}
        onClick={() => canExpand && setOpen((v) => !v)}
      >
        <td className="py-1.5 pl-2 pr-2 align-top">
          <div className="flex items-start gap-1.5">
            {canExpand ? (
              <ChevronRight className={cn('mt-0.5 size-3 shrink-0 text-muted-foreground transition-transform', open && 'rotate-90')} />
            ) : (
              <span className="w-3 shrink-0" />
            )}
            <div className="min-w-0">
              <span className={cn('block leading-snug', row.status === 'dropped' && 'line-through')}>{row.indicator || '—'}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-1">
                <span className={cn('size-1.5 rounded-full', row.mapped ? 'bg-emerald-500' : 'bg-muted-foreground/40')} title={row.mapped ? 'mapped to data' : 'unmapped'} />
                <span className={cn('size-1.5 rounded-full', row.inModel ? 'bg-primary' : 'bg-muted-foreground/40')} title={row.inModel ? 'in model' : 'not in model'} />
                {row.rangeSource && (
                  <span className="rounded bg-muted px-1 text-[9px] uppercase tracking-wide text-muted-foreground">
                    {row.rangeSource === 'knowledge' ? 'KB' : 'ref'}
                  </span>
                )}
              </span>
            </div>
          </div>
        </td>
        <td className="px-2 py-1.5 text-right align-top font-mono text-[11px]">{num(row.coef)}</td>
        <td className={cn('px-2 py-1.5 text-right align-top font-mono text-[11px]', row.significant && 'font-bold text-foreground')}>{num(row.tValue)}</td>
        <td className="px-2 py-1.5 text-right align-top font-mono text-[11px] text-muted-foreground">{num(row.pValue, 3)}</td>
        <td className="px-2 py-1.5 align-top"><RangeCell value={row.roi} band={row.roiRange} status={row.roiStatus} /></td>
        <td className="px-2 py-1.5 align-top"><RangeCell value={row.contribution} band={row.contributionRange} status={row.contributionStatus} isPct /></td>
        <td className="px-2 py-1.5 align-top">
          <span className={cn('inline-flex w-fit items-center rounded px-1.5 py-0.5 text-[11px] font-medium', meta.chip)}>
            {meta.label}
            {row.droppedBy && ` · ${row.droppedBy}`}
          </span>
          {row.flagReason && <p className="mt-0.5 max-w-[220px] text-[10px] leading-snug text-amber-600/90">{row.flagReason}</p>}
        </td>
      </tr>
      {open && canExpand && (
        <tr className="border-b border-border/50 bg-muted/30">
          <td colSpan={7} className="px-8 py-2">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="py-0.5 pr-4 font-medium">Object</th>
                  <th className="py-0.5 pr-4 text-right font-medium">Coef</th>
                  <th className="py-0.5 pr-4 text-right font-medium">t</th>
                  <th className="py-0.5 pr-4 text-right font-medium">p</th>
                  <th className="py-0.5 pr-4 text-right font-medium">ROI</th>
                  <th className="py-0.5 text-right font-medium">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {row.results.map((r, i) => (
                  <tr key={`${r.object}-${i}`} className="font-mono">
                    <td className="py-0.5 pr-4 font-sans">{r.object}</td>
                    <td className="py-0.5 pr-4 text-right">{num(r.coef)}</td>
                    <td className="py-0.5 pr-4 text-right">{num(r.tValue)}</td>
                    <td className="py-0.5 pr-4 text-right">{num(r.pValue, 3)}</td>
                    <td className="py-0.5 pr-4 text-right">{num(r.roi)}</td>
                    <td className="py-0.5 text-right">{pct(r.contribution)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  )
}

/* ── main view ─────────────────────────────────────────── */
export function OlsTreeView({ inst }: { inst: ArtifactInstance }) {
  const data = asOlsTree(inst.body)
  const [filter, setFilter] = useState<Set<OlsRowStatus>>(new Set())

  const groups = useMemo(() => {
    if (!data) return []
    const rows = filter.size ? data.tree.filter((r) => filter.has(r.status)) : data.tree
    const out: { path: string; rows: OlsTreeRow[] }[] = []
    for (const r of rows) {
      const path = [r.l1, r.l2, r.l3].filter(Boolean).join(' › ') || '—'
      const last = out[out.length - 1]
      if (last && last.path === path) last.rows.push(r)
      else out.push({ path, rows: [r] })
    }
    return out
  }, [data, filter])

  if (!data) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        The OLS regression test has not run yet — it fits the candidate model table and compares each indicator to its industry range.
      </div>
    )
  }

  // Setup state: 2.5 has proposed a setup but 2.5r has not fitted yet.
  if (!data.objects.length && !data.tree.length) {
    const s = data.setup
    return (
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6">
        <div className="mx-auto max-w-md rounded-xl border border-dashed border-border bg-card p-5 text-center">
          <h3 className="text-sm font-semibold">Setup proposed — not fitted yet</h3>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">
            {data.note || 'Confirm the response, the model variables and the settings in the build process to run the regression.'}
          </p>
          {s && (
            <dl className="mt-3 grid grid-cols-2 gap-2 text-left text-[11px]">
              <div className="rounded-md bg-muted/50 px-2 py-1.5">
                <dt className="text-muted-foreground">Responses</dt>
                <dd className="font-medium">{s.y.length} model object(s)</dd>
              </div>
              <div className="rounded-md bg-muted/50 px-2 py-1.5">
                <dt className="text-muted-foreground">Variables</dt>
                <dd className="font-medium">{s.selectedX} of {s.totalX} selected</dd>
              </div>
              {s.params && (
                <>
                  <div className="rounded-md bg-muted/50 px-2 py-1.5">
                    <dt className="text-muted-foreground">Transforms</dt>
                    <dd className="font-medium">adstock {s.params.adstock} · {s.params.saturation}</dd>
                  </div>
                  <div className="rounded-md bg-muted/50 px-2 py-1.5">
                    <dt className="text-muted-foreground">Controls</dt>
                    <dd className="font-medium">{s.params.trend} trend · {s.params.seasonality}</dd>
                  </div>
                </>
              )}
            </dl>
          )}
          {s?.dataSource === 'reference' && (
            <p className="mt-3 rounded-md bg-amber-500/10 px-2 py-1.5 text-[11px] leading-snug text-amber-600">
              Configured against the reference dataset — no published project data.
            </p>
          )}
        </div>
      </div>
    )
  }

  // ROI is only comparable to the Knowledge money bands when the fit produced a
  // revenue/spend ratio (money response, or volume + a unit price).
  const moneyRoi = data.setup?.roiUnit === 'revenue/spend'

  const toggle = (k: OlsRowStatus) =>
    setFilter((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
      {/* fit-metric header */}
      <section aria-label="Model fit">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Model objects — fast OLS pre-fit</h3>
        <div className="flex gap-2.5 overflow-x-auto pb-1">
          {data.objects.map((o) => (
            <ObjectCard key={o.object} o={o} />
          ))}
        </div>
      </section>

      {/* summary filter strip */}
      <section aria-label="Result summary" className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[11px] text-muted-foreground">
          {data.summary.total} factors · {data.summary.inModel} in model
        </span>
        {SUMMARY_ORDER.map(({ key, label, countKey }) => {
          const count = data.summary[countKey]
          const active = filter.has(key)
          return (
            <button
              key={key}
              type="button"
              onClick={() => toggle(key)}
              className={cn(
                'rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors',
                active ? 'border-primary/50 bg-accent' : 'border-border text-muted-foreground hover:bg-accent/60',
              )}
            >
              <span className={cn('mr-1 inline-block size-1.5 rounded-full align-middle', STATUS_META[key].chip)} />
              {label} {count}
            </button>
          )
        })}
        {filter.size > 0 && (
          <button type="button" onClick={() => setFilter(new Set())} className="text-[11px] text-primary hover:underline">
            clear
          </button>
        )}
      </section>

      {/* factor tree results */}
      <section aria-label="Factor tree results" className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-[12.5px]">
          <thead className="bg-muted/50">
            <tr className="text-left text-[11px] text-muted-foreground">
              <th className="py-2 pl-2 pr-2 font-medium">Indicator</th>
              <th className="px-2 py-2 text-right font-medium">Coef</th>
              <th className="px-2 py-2 text-right font-medium">t</th>
              <th className="px-2 py-2 text-right font-medium">p</th>
              <th className="px-2 py-2 font-medium">
                ROI
                {moneyRoi ? ' · band' : (
                  <span className="ml-1 font-normal normal-case text-muted-foreground/80" title="Y is a volume metric and no unit price is set, so ROI is volume per spend — not comparable to the industry money bands.">
                    (volume/spend — not benchmarked)
                  </span>
                )}
              </th>
              <th className="px-2 py-2 font-medium">Contribution · band</th>
              <th className="px-2 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <Fragment key={`grp-${g.path}`}>
                <tr className="bg-muted/30">
                  <td colSpan={7} className="px-2 py-1 text-[11px] font-semibold text-foreground/80">{g.path}</td>
                </tr>
                {g.rows.map((r) => (
                  <IndicatorRow key={r.key} row={r} />
                ))}
              </Fragment>
            ))}
            {groups.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-[12px] text-muted-foreground">No factors match this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {data.note && <p className="px-1 text-[11px] leading-relaxed text-muted-foreground">{data.note}</p>}
    </div>
  )
}
