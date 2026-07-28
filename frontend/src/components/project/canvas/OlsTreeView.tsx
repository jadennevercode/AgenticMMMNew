import { useMemo, useState } from 'react'
import { asOlsTree } from '../../../lib/artifact-format'
import { cn } from '../../../lib/cn'
import type {
  ArtifactInstance,
  OlsObjectSummary,
  OlsRowStatus,
  OlsSearchTrace,
  OlsSearchTrial,
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
  notMapped: { label: 'Not mapped', chip: 'bg-muted/60 text-muted-foreground/70' },
}

const SUMMARY_ORDER: { key: OlsRowStatus; label: string; countKey: keyof OlsTreeSummary }[] = [
  { key: 'inRange', label: 'In range', countKey: 'inRange' },
  { key: 'review', label: 'Flagged', countKey: 'flagged' },
  { key: 'noBenchmark', label: 'No benchmark', countKey: 'noBenchmark' },
  { key: 'notInModel', label: 'Not in model', countKey: 'notInModel' },
  { key: 'dropped', label: 'Dropped', countKey: 'dropped' },
  { key: 'notMapped', label: 'Not mapped', countKey: 'notMapped' },
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

/* ── one horizontal factor row (L1|L2|L3|L4|Indicator + fit cells) ──
 * When `channel` is set, coef/t/p/ROI/Contribution are read from that object's
 * own result (`row.results`); otherwise the aggregate row values are shown. */
interface Laid {
  row: OlsTreeRow
  firstL1: boolean
  firstL2: boolean
  firstL3: boolean
}

function IndicatorRow({ laid, channel }: { laid: Laid; channel: string }) {
  const { row, firstL1, firstL2, firstL3 } = laid
  const res = channel ? row.results.find((r) => r.object === channel) : undefined
  const inChannel = !channel || res != null
  const coef = res ? res.coef : row.coef
  const tValue = res ? res.tValue : row.tValue
  const pValue = res ? res.pValue : row.pValue
  const roi = res ? res.roi : row.roi
  const contribution = res ? res.contribution : row.contribution
  const meta = STATUS_META[!inChannel ? 'notInModel' : row.status]
  return (
    <tr
      className={cn(
        'border-b border-border/40',
        firstL1 && 'border-t border-border/70',
        (row.status === 'dropped' || !inChannel) && 'opacity-60',
        'hover:bg-accent/40',
      )}
    >
      <td className={cn('px-2 py-1.5 align-top font-semibold', !firstL1 && 'text-foreground/45')}>{row.l1 || '—'}</td>
      <td className={cn('px-2 py-1.5 align-top text-foreground/80', !firstL2 && 'text-foreground/40')}>{row.l2}</td>
      <td className={cn('px-2 py-1.5 align-top text-foreground/70', !firstL3 && 'text-foreground/40')}>{row.l3}</td>
      <td className="px-2 py-1.5 align-top text-muted-foreground">{row.l4}</td>
      <td className="px-2 py-1.5 align-top">
        <span className={cn('block leading-snug font-medium', row.status === 'dropped' && 'line-through')}>{row.indicator || '—'}</span>
        <span className="mt-0.5 flex flex-wrap items-center gap-1">
          <span className={cn('size-1.5 rounded-full', row.mapped ? 'bg-emerald-500' : 'bg-muted-foreground/40')} title={row.mapped ? 'mapped to data' : 'unmapped'} />
          <span className={cn('size-1.5 rounded-full', row.inModel ? 'bg-primary' : 'bg-muted-foreground/40')} title={row.inModel ? 'in model' : 'not in model'} />
          {row.rangeSource && (
            <span className="rounded bg-muted px-1 text-[9px] uppercase tracking-wide text-muted-foreground">
              {row.rangeSource === 'knowledge' ? 'KB' : 'ref'}
            </span>
          )}
        </span>
      </td>
      <td className="px-2 py-1.5 text-right align-top font-mono text-[11px]">{num(coef)}</td>
      <td className={cn('px-2 py-1.5 text-right align-top font-mono text-[11px]', row.significant && !channel && 'font-bold text-foreground')}>{num(tValue)}</td>
      <td className="px-2 py-1.5 text-right align-top font-mono text-[11px] text-muted-foreground">{num(pValue, 3)}</td>
      <td className="px-2 py-1.5 align-top">
        <RangeCell value={roi} band={row.roiRange} status={channel ? '' : row.roiStatus} />
        {/* An exposure metric has no spend of its own — say whose it divided by,
            or the ratio reads as a cost-per-unit it is not. */}
        {roi != null && row.roiBasis && (
          <span className="mt-0.5 block max-w-[180px] truncate text-[9px] leading-snug text-muted-foreground" title={row.roiBasis}>
            {row.roiBasis}
          </span>
        )}
      </td>
      <td className="px-2 py-1.5 align-top"><RangeCell value={contribution} band={row.contributionRange} status={channel ? '' : row.contributionStatus} isPct /></td>
      <td className="px-2 py-1.5 align-top">
        <span className={cn('inline-flex w-fit items-center rounded px-1.5 py-0.5 text-[11px] font-medium', meta.chip)}>
          {meta.label}
          {row.droppedBy && ` · ${row.droppedBy}`}
        </span>
        {row.flagReason && !channel && <p className="mt-0.5 max-w-[220px] text-[10px] leading-snug text-amber-600/90">{row.flagReason}</p>}
        {/* The AI's reading sits under the computed verdict, never instead of it:
            the chip above is the deterministic range check, this is the judgement. */}
        {row.aiRationale && !channel && (
          <p className="mt-1 max-w-[240px] text-[10px] leading-snug text-muted-foreground">
            <span className={cn('mr-1 rounded px-1 py-px text-[9px] uppercase tracking-wide',
              AI_VERDICT_CHIP[row.aiVerdict || ''] ?? 'bg-muted text-muted-foreground')}>
              {AI_VERDICT_LABEL[row.aiVerdict || ''] ?? 'AI'}
            </span>
            {row.aiRationale}
          </p>
        )}
      </td>
    </tr>
  )
}

const AI_VERDICT_LABEL: Record<string, string> = {
  consistent: 'Consistent',
  questionable: 'Questionable',
  implausible: 'Implausible',
  noBenchmark: 'No band',
}
const AI_VERDICT_CHIP: Record<string, string> = {
  consistent: 'bg-emerald-500/15 text-emerald-600',
  questionable: 'bg-amber-500/15 text-amber-700',
  implausible: 'bg-rose-500/15 text-rose-600',
  noBenchmark: 'bg-muted text-muted-foreground',
}

/**
 * What the per-L4 indicator search tried, and why the winner won.
 *
 * The search fits the model many times over — one assignment of indicators to
 * factors per fit — and every one of those fits produced a coefficient, a
 * significance and a range verdict for the factor it was testing. Those are
 * exactly the numbers a reviewer wants when asking "why this indicator and not
 * that one", so they are kept rather than discarded with the losing trial.
 */
function SearchTrace({ trace }: { trace: OlsSearchTrace }) {
  const [open, setOpen] = useState(false)
  const byFactor = new Map<string, OlsSearchTrial[]>()
  for (const t of trace.trials) {
    const k = t.l4 || '—'
    byFactor.set(k, [...(byFactor.get(k) ?? []), t])
  }

  return (
    <section aria-label="Indicator search" className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-accent/40"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Indicator search
        </span>
        <span className="text-[11px] text-muted-foreground">
          {trace.fits} trial fit{trace.fits === 1 ? '' : 's'} · {trace.candidates} candidate
          {trace.candidates === 1 ? '' : 's'} over {trace.l4Searched} factor
          {trace.l4Searched === 1 ? '' : 's'} · {trace.swaps} swap{trace.swaps === 1 ? '' : 's'}
        </span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2.5">
          <p className="mb-2 text-[11px] leading-relaxed text-muted-foreground">{trace.note}</p>
          <div className="space-y-2.5">
            {trace.perFactor.map((f) => {
              const trials = byFactor.get(f.l4) ?? []
              return (
                <div key={f.l4}>
                  <p className="text-[11px]">
                    <span className="text-muted-foreground">{f.l4 || '—'}</span>
                    {' → '}
                    <span className="font-medium">{f.chosen}</span>
                    {f.candidates.length > 1 && (
                      <span className="text-muted-foreground"> (of {f.candidates.length} candidates)</span>
                    )}
                  </p>
                  {trials.length > 0 && (
                    <ul className="mt-0.5 space-y-0.5">
                      {trials.map((t, i) => (
                        <li
                          key={i}
                          className={cn(
                            'flex flex-wrap items-baseline gap-x-2 text-[10.5px]',
                            t.indicator === f.chosen ? 'text-foreground' : 'text-muted-foreground',
                          )}
                        >
                          <span className="font-mono">{t.indicator}</span>
                          <span className="font-mono">R²={t.r2.toFixed(3)}</span>
                          <span className="font-mono">coef={num(t.coef)}</span>
                          <span className="font-mono">t={num(t.tValue)}</span>
                          {t.roi != null && <span className="font-mono">ROI={num(t.roi)}</span>}
                          {t.contribution != null && (
                            <span className="font-mono">contrib={num(t.contribution, 1)}%</span>
                          )}
                          {t.signExpected && (
                            <span className={t.signCorrect ? 'text-emerald-600' : 'text-rose-600'}>
                              {t.signCorrect ? 'sign ok' : 'wrong sign'}
                            </span>
                          )}
                          {t.roiStatus === 'out' && <span className="text-amber-600">ROI out of band</span>}
                          {t.contributionStatus === 'out' && (
                            <span className="text-amber-600">contribution out of band</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}

/* ── main view ─────────────────────────────────────────── */
export function OlsTreeView({ inst }: { inst: ArtifactInstance }) {
  const data = asOlsTree(inst.body)
  const [filter, setFilter] = useState<Set<OlsRowStatus>>(new Set())

  // Flat rows with vertical-merge flags (first-of-run per L level).
  const laidRows: Laid[] = useMemo(() => {
    if (!data) return []
    // `notMapped` rows (2.1 had no data for the factor) are upstream coverage, not
    // an OLS verdict — hide them unless the user explicitly filters to them, so a
    // sparse dataset doesn't read as "the model dropped everything".
    const rows = filter.size
      ? data.tree.filter((r) => filter.has(r.status))
      : data.tree.filter((r) => r.status !== 'notMapped')
    return rows.map((row, i, arr) => {
      const prev = arr[i - 1]
      const firstL1 = !prev || prev.l1 !== row.l1
      const firstL2 = firstL1 || prev?.l2 !== row.l2
      const firstL3 = firstL2 || prev?.l3 !== row.l3
      return { row, firstL1, firstL2, firstL3 }
    })
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
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">National total model — fast OLS pre-fit</h3>
        </div>
        <div className="flex gap-2.5 overflow-x-auto pb-1">
          {data.objects.map((o) => (
            <ObjectCard key={o.object} o={o} />
          ))}
        </div>
      </section>

      {data.search && data.search.fits > 0 && <SearchTrace trace={data.search} />}

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

      {/* factor tree results — horizontal L1|L2|L3|L4|Indicator + fit cells */}
      <section aria-label="Factor tree results" className="overflow-hidden rounded-xl border border-border">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-[12.5px]">
            <thead className="bg-muted/50">
              <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <th className="px-2 py-2 font-semibold">L1</th>
                <th className="px-2 py-2 font-medium">L2</th>
                <th className="px-2 py-2 font-medium">L3</th>
                <th className="px-2 py-2 font-medium">L4</th>
                <th className="px-2 py-2 font-medium">Indicator</th>
                <th className="px-2 py-2 text-right font-medium">Coef</th>
                <th className="px-2 py-2 text-right font-medium">t</th>
                <th className="px-2 py-2 text-right font-medium">p</th>
                <th className="px-2 py-2 font-medium">
                  ROI
                  {moneyRoi ? ' · band' : (
                    <span className="ml-1 font-normal normal-case text-muted-foreground/80" title="Y is a volume metric and no unit price is set, so ROI is volume per spend — not comparable to the industry money bands.">
                      (vol/spend)
                    </span>
                  )}
                </th>
                <th className="px-2 py-2 font-medium">Contribution · band</th>
                <th className="px-2 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {laidRows.map((laid) => (
                <IndicatorRow key={laid.row.key} laid={laid} channel="" />
              ))}
              {laidRows.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-3 py-6 text-center text-[12px] text-muted-foreground">No factors match this filter.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {data.note && <p className="px-1 text-[11px] leading-relaxed text-muted-foreground">{data.note}</p>}
    </div>
  )
}
