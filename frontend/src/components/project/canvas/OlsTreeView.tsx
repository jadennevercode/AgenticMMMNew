import { useMemo, useState } from 'react'
import { asOlsTree } from '../../../lib/artifact-format'
import { OlsFactorTreePanel } from '../ols/OlsFactorTreePanel'
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

interface ObjectCardProps {
  o: OlsObjectSummary
  selected?: boolean
  onSelect?: () => void
}

function ObjectCard({ o, selected = false, onSelect }: ObjectCardProps) {
  if (o.error) {
    return (
      <div className="min-w-[210px] shrink-0 rounded-xl border border-rose-500/30 bg-rose-500/5 p-3 text-left">
        <div className="text-[13px] font-semibold text-rose-600">{o.label || o.object}</div>
        <p className="mt-1 text-[11px] leading-snug text-rose-500/80">{o.error}</p>
      </div>
    )
  }
  const flagged = o.redFlags.length > 0
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      title={selected ? 'Showing this model — click to show every model' : 'Show only this model’s verdicts'}
      className={cn(
        'min-w-[210px] shrink-0 rounded-xl border bg-card p-3 text-left shadow-sm transition-colors',
        selected ? 'border-primary ring-1 ring-primary/40' : 'border-border hover:border-primary/40',
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[13px] font-semibold">{o.label || o.object}</span>
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
    </button>
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
      <td className="px-2 py-1.5 align-top">
        <RangeCell value={contribution} band={row.contributionRange} status={channel ? '' : row.contributionStatus} isPct />
        {contribution != null && row.contributionBasis && (
          <span className="mt-0.5 block max-w-[180px] truncate text-[9px] leading-snug text-muted-foreground" title={row.contributionBasis}>
            {row.contributionBasis}
          </span>
        )}
      </td>
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

/* ── how each model reads ──────────────────────────────
 * One panel per model object: the indicators that carry it, and the AI's account
 * of what the fit says and what qualifies it. The key-driver list is computed
 * (significant drivers ranked by contribution) — the language explains that list,
 * it does not choose it, and every number it cites comes from the fit.
 */
function ModelReadings({ objects }: { objects: OlsObjectSummary[] }) {
  const [open, setOpen] = useState(true)
  const withSummary = objects.filter((o) => o.aiSummary)
  if (withSummary.length === 0) return null

  return (
    <section aria-label="Model readings" className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-accent/40"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          What each model says
        </span>
        <span className="text-[11px] text-muted-foreground">
          {withSummary.length} model{withSummary.length === 1 ? '' : 's'}
        </span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-border px-3 py-2.5">
          {withSummary.map((o) => (
            <article key={o.object}>
              <h4 className="text-[11px] font-semibold">{o.label || o.object}</h4>
              {o.aiKeyDrivers && o.aiKeyDrivers.length > 0 && (
                <ul className="mt-1 flex flex-wrap gap-1">
                  {o.aiKeyDrivers.map((d) => (
                    <li
                      key={d}
                      className="rounded bg-accent px-1.5 py-0.5 font-mono text-[10.5px] text-foreground"
                    >
                      {d}
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{o.aiSummary}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

/* ── main view ─────────────────────────────────────────── */
export function OlsTreeView({ inst }: { inst: ArtifactInstance }) {
  const data = asOlsTree(inst.body)
  const [filter, setFilter] = useState<Set<OlsRowStatus>>(new Set())
  // Which model's verdicts the tree shows. '' = every model, one row each.
  const [model, setModel] = useState<string>('')
  // 'fits' is the read-only result table; 'verdicts' is the 2.5d review surface,
  // mounted here so the tree and the decision on it are one screen rather than
  // a result you have to go somewhere else to act on.
  const [tab, setTab] = useState<'fits' | 'verdicts'>('fits')

  // Every tree row is one factor's verdict in ONE model object, so with N×M models
  // the flat table interleaves N×M verdicts per factor. Scoping to a model is what
  // makes it readable — and it is the question a reviewer actually has ("what did
  // Ecommerce · Aurelia Pro do with this factor"), not an average across models.
  const scoped = useMemo(() => {
    if (!data) return []
    return model ? data.tree.filter((r) => r.object === model) : data.tree
  }, [data, model])

  // Counts follow the scope, or the strip would describe a different population
  // than the table below it.
  const summary: OlsTreeSummary = useMemo(() => {
    if (!data) return { total: 0, inModel: 0, inRange: 0, flagged: 0, noBenchmark: 0, notInModel: 0, dropped: 0, notMapped: 0 }
    if (!model) return data.summary
    const n = (p: (r: OlsTreeRow) => boolean) => scoped.filter(p).length
    return {
      total: scoped.length,
      inModel: n((r) => r.inModel),
      inRange: n((r) => r.status === 'inRange'),
      flagged: n((r) => r.status === 'review'),
      noBenchmark: n((r) => r.status === 'noBenchmark'),
      notInModel: n((r) => r.status === 'notInModel'),
      dropped: n((r) => r.status === 'dropped'),
      notMapped: n((r) => r.status === 'notMapped'),
    }
  }, [data, model, scoped])

  // Flat rows with vertical-merge flags (first-of-run per L level).
  const laidRows: Laid[] = useMemo(() => {
    // `notMapped` rows (2.1 had no data for the factor) are upstream coverage, not
    // an OLS verdict — hide them unless the user explicitly filters to them, so a
    // sparse dataset doesn't read as "the model dropped everything".
    const rows = filter.size
      ? scoped.filter((r) => filter.has(r.status))
      : scoped.filter((r) => r.status !== 'notMapped')
    return rows.map((row, i, arr) => {
      const prev = arr[i - 1]
      const firstL1 = !prev || prev.l1 !== row.l1
      const firstL2 = firstL1 || prev?.l2 !== row.l2
      const firstL3 = firstL2 || prev?.l3 !== row.l3
      return { row, firstL1, firstL2, firstL3 }
    })
  }, [scoped, filter])

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
  const modelLabel = data.objects.find((o) => o.object === model)?.label || model

  const toggle = (k: OlsRowStatus) =>
    setFilter((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
      <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
        {([['fits', 'Model fits'], ['verdicts', 'Factor tree · verdicts']] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              'rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors',
              tab === id ? 'bg-accent text-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent/50',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'verdicts' && <OlsFactorTreePanel />}

      {tab === 'fits' && (
      <>
      {/* fit-metric header */}
      <section aria-label="Model fit">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {data.objects.length} model{data.objects.length === 1 ? '' : 's'} — one per channel &times; product, fast OLS
          </h3>
        </div>
        <div className="flex gap-2.5 overflow-x-auto pb-1">
          {data.objects.map((o) => (
            <ObjectCard
              key={o.object}
              o={o}
              selected={model === o.object}
              onSelect={() => setModel((m) => (m === o.object ? '' : o.object))}
            />
          ))}
        </div>
      </section>

      <ModelReadings objects={data.objects} />

      {/* summary filter strip */}
      <section aria-label="Result summary" className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => setModel('')}
          className={cn(
            'rounded-md border px-2 py-0.5 text-[11px] font-medium transition-colors',
            model ? 'border-primary/50 bg-accent' : 'border-border text-muted-foreground hover:bg-accent/60',
          )}
          title={model ? 'Show every model' : 'Showing every model — pick a card above to scope the tree'}
        >
          {model ? `${modelLabel} ✕` : 'All models'}
        </button>
        <span className="mr-1 text-[11px] text-muted-foreground">
          {summary.total} factors · {summary.inModel} in model
        </span>
        {SUMMARY_ORDER.map(({ key, label, countKey }) => {
          const count = summary[countKey]
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
      </>
      )}
    </div>
  )
}
