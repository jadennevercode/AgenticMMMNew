import { useCallback, useEffect, useRef, useState } from 'react'
import { MessageSquare, Sparkles } from 'lucide-react'

import type {
  ValidationChartAnalysis,
  ValidationGroup,
  ValidationReviewData,
  ValidationSeriesRequest,
  ValidationSeriesResponse,
} from '../../../lib/types'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { ValidationChart } from './ValidationChart'
import { groupVerdict, pairVerdict } from './signoff'

/** The yearly table's YoY basis: a full year, or one calendar month across years. */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December']

// DATA-005: the period grains the view can bucket on.
const GRAIN_LABELS: Record<string, string> = {
  year: 'Year', half_year: 'Half-year', quarter: 'Quarter', month: 'Month',
}
const ALL_GRAINS = ['year', 'half_year', 'quarter', 'month']

// DATA-004: the L4–L8 drilldown levels, in cascade order, with their filter labels.
const DRILL_LEVELS = ['l4', 'l5', 'l6', 'l7', 'l8'] as const
type DrillLevel = (typeof DRILL_LEVELS)[number]
const LEVEL_LABEL: Record<DrillLevel, string> = {
  l4: 'Sub-factor (L4)', l5: 'Level 5', l6: 'Level 6', l7: 'Level 7', l8: 'Level 8',
}
const EMPTY_LEVELS: Record<DrillLevel, string> = { l4: '', l5: '', l6: '', l7: '', l8: '' }

function fmt(n: number | null): string {
  if (n == null) return '—'
  const a = Math.abs(n)
  if (a >= 1e8) return `${(n / 1e8).toFixed(1)}亿`
  if (a >= 1e4) return `${(n / 1e4).toFixed(1)}万`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  return `${Math.round(n * 100) / 100}`
}

/** DATA-008: format a value per its indicator metadata — a percentage shows `%`
 * (never a giant integer), money shows a currency mark, else a compact number. */
function fmtMeta(n: number | null, numberFormat?: string, unit?: string): string {
  if (n == null) return '—'
  if (numberFormat === 'percent') return `${Math.round(n * 10) / 10}%`
  const s = fmt(n)
  if (numberFormat === 'money') return `${unit || '¥'}${s}`
  return s
}

const AGG_LABEL: Record<string, string> = {
  sum: 'Σ', average: 'avg', count: 'count', min: 'min', max: 'max',
  distinct_count: 'distinct', weighted_average: 'w.avg',
}

/** A checkbox multi-select in a native <details> popover (empty selection = all). */
function MultiMenu({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string[]
  onChange: (next: string[]) => void
}) {
  const toggle = (o: string) =>
    onChange(value.includes(o) ? value.filter((v) => v !== o) : [...value, o])
  return (
    <details className="relative">
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors',
          value.length ? 'border-primary/40 bg-primary/5 text-primary' : 'border-border text-muted-foreground hover:bg-muted',
        )}
      >
        {label}
        {value.length > 0 && <span className="rounded bg-primary/15 px-1 text-[10px]">{value.length}</span>}
      </summary>
      <div className="absolute z-20 mt-1 max-h-56 w-56 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg">
        {options.length === 0 && (
          <div className="px-2 py-1.5 text-xs text-muted-foreground">No options</div>
        )}
        {value.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            className="mb-0.5 w-full rounded px-2 py-1 text-left text-[11px] text-muted-foreground hover:bg-muted"
          >
            Clear (show all)
          </button>
        )}
        {options.map((o) => (
          <label key={o} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted">
            <input type="checkbox" checked={value.includes(o)} onChange={() => toggle(o)} className="accent-primary" />
            <span className="truncate" title={o}>{o}</span>
          </label>
        ))}
      </div>
    </details>
  )
}

/** Single-select in a <details> popover with an "All" reset. */
function SingleMenu({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string
  onChange: (next: string) => void
}) {
  return (
    <details className="relative">
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors',
          value ? 'border-primary/40 bg-primary/5 text-primary' : 'border-border text-muted-foreground hover:bg-muted',
        )}
      >
        {label}
        {value && <span className="max-w-24 truncate text-[11px]">· {value}</span>}
      </summary>
      <div className="absolute z-20 mt-1 max-h-56 w-56 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg">
        <button
          type="button"
          onClick={() => onChange('')}
          className={cn('w-full rounded px-2 py-1 text-left text-xs hover:bg-muted', !value && 'font-medium text-primary')}
        >
          All
        </button>
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o)}
            className={cn('w-full truncate rounded px-2 py-1 text-left text-xs hover:bg-muted', value === o && 'font-medium text-primary')}
            title={o}
          >
            {o}
          </button>
        ))}
      </div>
    </details>
  )
}

/**
 * Per-year values with a same-period year-over-year change.
 *
 * The month selector matters for a seasonal business: comparing a full year to a
 * full year both hides the seasonal story and penalises the current year while it
 * is still partial. Picking March compares March to March.
 */
function YearlyTable({
  res, yoyMonth, onYoyMonth,
}: {
  res: ValidationSeriesResponse
  yoyMonth: number
  onYoyMonth: (m: number) => void
}) {
  const { years, rows } = res.yearly
  if (!years.length || !rows.length) return null
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/40 px-3 py-1.5">
        <span className="text-[11px] text-muted-foreground">
          {res.yearly.monthLabel ?? 'Full year'} · year over year
        </span>
        <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          Compare
          <select
            value={yoyMonth}
            onChange={(e) => onYoyMonth(Number(e.target.value))}
            className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px]
                       transition-colors hover:border-foreground/40 focus:border-foreground/60
                       focus:outline-none focus:ring-1 focus:ring-foreground/20"
          >
            <option value={0}>Full year</option>
            {MONTHS.map((m, i) => (
              <option key={m} value={i + 1}>{m}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/20 text-left text-muted-foreground">
            <th className="px-3 py-1.5 font-medium">Indicator</th>
            {years.map((y) => (
              <th key={y} className="px-3 py-1.5 text-right font-medium whitespace-nowrap">{y}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.metric} className="border-b border-border/50 last:border-0">
              <td className="px-3 py-1.5 font-medium">
                {r.metric}
                {r.aggregation && (
                  <span className="ml-1.5 text-[10px] font-normal text-muted-foreground" title={`aggregation: ${r.aggregation}`}>
                    {AGG_LABEL[r.aggregation] ?? r.aggregation}
                  </span>
                )}
              </td>
              {r.values.map((v, i) => {
                const yoy = r.yoy[i]
                return (
                  <td key={i} className="px-3 py-1.5 text-right whitespace-nowrap tabular-nums">
                    {fmtMeta(v, r.numberFormat, r.unit)}
                    {yoy != null && (
                      <span className={cn('ml-1.5 text-[10px]', yoy >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
                        {yoy >= 0 ? '+' : ''}{yoy}%
                      </span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}

/** DATA-005: current-window vs comparison-window totals per indicator. */
function ComparisonBlock({ res }: { res: ValidationSeriesResponse }) {
  const c = res.comparison
  if (!c) return null
  return (
    <div className="mt-3 rounded-lg border border-primary/25 bg-primary/[0.03]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-primary/15 px-3 py-1.5">
        <span className="text-[11px] font-medium text-primary">
          {c.name} · {c.current.label}
          {c.comparison && <span className="text-muted-foreground"> vs {c.comparison.label}</span>}
        </span>
        {c.comparison && !c.equalLength && (
          <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-700">
            ⚠ comparison windows are not equal length
          </span>
        )}
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border/50 text-left text-muted-foreground">
            <th className="px-3 py-1 font-medium">Indicator</th>
            <th className="px-3 py-1 text-right font-medium">Current</th>
            <th className="px-3 py-1 text-right font-medium">Comparison</th>
            <th className="px-3 py-1 text-right font-medium">Δ</th>
          </tr>
        </thead>
        <tbody>
          {c.rows.map((r) => (
            <tr key={r.metric} className="border-b border-border/40 last:border-0">
              <td className="px-3 py-1 font-medium">
                {r.metric}
                {r.aggregation && (
                  <span className="ml-1.5 text-[10px] font-normal text-muted-foreground" title={`aggregation: ${r.aggregation}`}>
                    {AGG_LABEL[r.aggregation] ?? r.aggregation}
                  </span>
                )}
              </td>
              <td className="px-3 py-1 text-right tabular-nums">{fmtMeta(r.current, r.numberFormat, r.unit)}</td>
              <td className="px-3 py-1 text-right tabular-nums text-muted-foreground">{fmtMeta(r.comparison, r.numberFormat, r.unit)}</td>
              <td className="px-3 py-1 text-right tabular-nums">
                {r.deltaPct == null ? (
                  '—'
                ) : (
                  <span className={cn(r.deltaPct >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
                    {r.deltaPct >= 0 ? '+' : ''}{r.deltaPct}%
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const VERDICT_LABEL: Record<'accepted' | 'denied' | 'mixed' | 'pending', string> = {
  accepted: 'Accepted', denied: 'Denied', mixed: 'Mixed', pending: 'Pending',
}

/** Per-indicator Accept/Deny rows beneath a chart. Clicking the value already
 * set clears it back to '' — blank means "not individually reviewed", which is
 * not the same as accepted. */
function IndicatorSignoffList({
  pairs,
  signoffs,
  onSignoffPair,
}: {
  pairs: { l4: string; indicator: string }[]
  signoffs: Record<string, string>
  onSignoffPair: (pair: { l4: string; indicator: string }, verdict: 'yes' | 'no' | '') => void
}) {
  if (!pairs.length) {
    return (
      <p className="mt-3 text-xs text-muted-foreground">
        This chart predates per-indicator sign-off — re-run 2.3 to enable it.
      </p>
    )
  }
  return (
    <div className="mt-3 divide-y divide-border/60 rounded-lg border border-border">
      {pairs.map((pair) => {
        const v = pairVerdict(signoffs, pair.l4, pair.indicator)
        return (
          <div
            key={`${pair.l4}|${pair.indicator}`}
            className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs"
          >
            <span className="min-w-0 truncate" title={`${pair.l4} · ${pair.indicator}`}>
              <span className="text-muted-foreground">{pair.l4}</span> · {pair.indicator}
            </span>
            <div className="flex shrink-0 items-center gap-1">
              {(['yes', 'no'] as const).map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => onSignoffPair(pair, v === val ? '' : val)}
                  className={cn(
                    'rounded px-2 py-0.5 text-[11px] font-medium transition-colors',
                    v === val
                      ? val === 'yes'
                        ? 'bg-emerald-500/15 text-emerald-600'
                        : 'bg-rose-500/15 text-rose-600'
                      : 'border border-border text-muted-foreground hover:bg-muted',
                  )}
                >
                  {val === 'yes' ? 'Y' : 'N'}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * The AI's reading of the chart above it.
 *
 * Rendered as labelled groups rather than one grey paragraph: a trend, an anomaly
 * and a caveat are different kinds of claim and get scanned differently. Periods
 * are monospace chips so they read against the chart's own x-axis.
 */
function ChartAnalysisBlock({
  analysis, loading, stale, error, onGenerate, onAsk,
}: {
  analysis: ValidationChartAnalysis | null
  loading: boolean
  stale: boolean
  error: string
  onGenerate: (force: boolean) => void
  /** Pin this chart's table (and its analysis) as the subject of a chat question. */
  onAsk: () => void
}) {
  if (loading) {
    return (
      <div className="mt-3 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
        Reading this chart…
      </div>
    )
  }
  if (!analysis) {
    return (
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed border-border px-3 py-2">
        <span className="text-xs text-muted-foreground">
          {error || 'No analysis for these filters yet.'}
        </span>
        <button
          type="button"
          onClick={() => onGenerate(false)}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px]
                     text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Sparkles className="h-3 w-3" /> Generate analysis
        </button>
      </div>
    )
  }
  return (
    <section className="mt-3 rounded-lg border border-border bg-muted/20">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-3 py-1.5">
        <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Sparkles className="h-3 w-3" />
          {analysis.fallback ? 'Computed readout' : 'AI analysis'}
          {analysis.filterLabel && <span className="truncate">· {analysis.filterLabel}</span>}
        </span>
        <span className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onAsk}
            title="Pin this chart's table and analysis in the chat"
            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px]
                       text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <MessageSquare className="h-3 w-3" /> Ask about this chart
          </button>
          <button
            type="button"
            onClick={() => onGenerate(true)}
            className={cn(
              'rounded-md border px-2 py-0.5 text-[11px] transition-colors',
              stale
                ? 'border-amber-500/40 bg-amber-500/10 text-amber-700 hover:bg-amber-500/20'
                : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground',
            )}
          >
            {stale ? 'Filters changed · Refresh' : 'Regenerate'}
          </button>
        </span>
      </div>
      <div className="space-y-2 px-3 py-2.5">
        <p className="text-xs leading-relaxed text-foreground">{analysis.headline}</p>
        <AnalysisList label="Trends" items={analysis.trends} />
        <AnalysisObs label="Anomalies" items={analysis.anomalies} />
        <AnalysisObs label="Inflections" items={analysis.inflections} />
        <AnalysisList label="Caveats" items={analysis.caveats} muted />
      </div>
    </section>
  )
}

function AnalysisList({ label, items, muted }: { label: string; items: string[]; muted?: boolean }) {
  if (!items.length) return null
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <ul className={cn('mt-0.5 space-y-0.5 text-xs leading-relaxed',
        muted ? 'text-muted-foreground' : 'text-foreground/90')}>
        {items.map((t, i) => <li key={i}>{t}</li>)}
      </ul>
    </div>
  )
}

function AnalysisObs({ label, items }: { label: string; items: ValidationChartAnalysis['anomalies'] }) {
  if (!items.length) return null
  return (
    <div>
      <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <ul className="mt-0.5 space-y-0.5 text-xs leading-relaxed">
        {items.map((o, i) => (
          <li key={i} className="flex gap-1.5">
            {o.period && (
              <code className="shrink-0 rounded bg-background px-1 py-px font-mono text-[10.5px] text-muted-foreground">
                {o.period}
              </code>
            )}
            <span>
              {o.metric && <span className="text-muted-foreground">{o.metric} · </span>}
              {o.note}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

interface FactorCardProps {
  group: ValidationGroup
  projectId: string
  signoffs: Record<string, string>
  onSignoffPair: (pair: { l4: string; indicator: string }, verdict: 'yes' | 'no' | '') => void
  onSignoffAll: (verdict: 'yes' | 'no') => void
}

function FactorCard({ group, projectId, signoffs, onSignoffPair, onSignoffAll }: FactorCardProps) {
  const stageMentions = useSimStore((s) => s.stageMentions)
  const ref = useRef<HTMLElement>(null)
  const [inView, setInView] = useState(false)
  const [grain, setGrain] = useState('month')
  const [sources, setSources] = useState<string[]>([])
  const [yoyMonth, setYoyMonth] = useState(0)
  const [levels, setLevels] = useState<Record<DrillLevel, string>>(EMPTY_LEVELS)
  const [indicators, setIndicators] = useState<string[]>(group.defaultIndicators)

  // DATA-004: setting or clearing a level cascade-clears every deeper level, and the
  // indicator selection resets (indicators are scoped to the drill path).
  const setLevel = (lvl: DrillLevel, value: string) => {
    setLevels((prev) => {
      const next = { ...prev, [lvl]: value }
      const idx = DRILL_LEVELS.indexOf(lvl)
      for (let i = idx + 1; i < DRILL_LEVELS.length; i++) next[DRILL_LEVELS[i]] = ''
      return next
    })
    setIndicators([])
  }
  const [brand, setBrand] = useState<string[]>([])
  const [channelType, setChannelType] = useState<string[]>([])
  const [provinceGroup, setProvinceGroup] = useState<string[]>([])
  const [res, setRes] = useState<ValidationSeriesResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Lazy-load: only query once the card scrolls into view (17+ factors otherwise
  // fire a burst of requests on open).
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ob = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setInView(true)
          ob.disconnect()
        }
      },
      { rootMargin: '160px' },
    )
    ob.observe(el)
    return () => ob.disconnect()
  }, [])

  // The one request body every fetch on this card uses — the series, and the
  // analysis of that same series. Building it once is what keeps the analysis
  // keyed to exactly the chart the user is looking at.
  const query: ValidationSeriesRequest = {
    l3: group.l3,
    l4: levels.l4 || undefined,
    l5: levels.l5 || undefined,
    l6: levels.l6 || undefined,
    l7: levels.l7 || undefined,
    l8: levels.l8 || undefined,
    indicators,
    grain,
    sources,
    brand,
    channelType,
    provinceGroup,
    yoyMonth,
  }

  const filterKey = [
    grain,
    yoyMonth,
    DRILL_LEVELS.map((l) => levels[l]).join('/'),
    indicators.join('|'),
    sources.join('|'),
    brand.join('|'),
    channelType.join('|'),
    provinceGroup.join('|'),
  ].join('~')

  useEffect(() => {
    if (!inView || !projectId) return
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading/error reset for a filter-keyed fetch, not an external-system sync
    setLoading(true)
    setError('')
    api
      .validationSeries(projectId, query)
      .then((r) => {
        if (!cancelled) setRes(r)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // filterKey captures every filter; group.l3 / inView / projectId gate the fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, projectId, group.l3, filterKey])

  // ── AI analysis of this exact chart ──
  const [analysis, setAnalysis] = useState<ValidationChartAnalysis | null>(null)
  const [analysisKey, setAnalysisKey] = useState('')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState('')

  const generate = useCallback(
    (force: boolean) => {
      if (!projectId) return
      setAnalysisLoading(true)
      setAnalysisError('')
      const forKey = filterKey
      api
        .validationChartAnalysis(projectId, query, force)
        .then((a) => { setAnalysis(a); setAnalysisKey(forKey) })
        .catch((e: unknown) => setAnalysisError(e instanceof Error ? e.message : String(e)))
        .finally(() => setAnalysisLoading(false))
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId, filterKey],
  )

  // Fetch the analysis once the series has landed, so a cached one appears with
  // the chart. It is not re-fetched on every filter twiddle — the block shows a
  // "Filters changed · Refresh" affordance instead, because generating one costs
  // a model call and the user is usually mid-exploration.
  useEffect(() => {
    if (!inView || !res || analysisKey) return
    // eslint-disable-next-line react-hooks/set-state-in-effect -- kicks off one fetch whose result lands in a callback; the same shape as the series fetch above
    generate(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inView, res, analysisKey])

  const opts = res?.options
  const grains = opts?.grains ?? ['year', 'month']
  const breadcrumb = [group.l1, group.l2, group.l3].filter(Boolean).join(' › ')
  const verdict = groupVerdict(group, signoffs)

  // The indicator list is scoped to the current drill path — say so on the control,
  // otherwise a cascade selection silently emptying it reads as a bug.
  const indicatorOptions = (opts?.indicators ?? []).map((i) => i.metric)
  const deepest = [...DRILL_LEVELS].reverse().find((l) => levels[l])
  const indicatorLabel = deepest
    ? `Indicator (${indicatorOptions.length} under ${levels[deepest]})`
    : 'Indicator'

  const analysisStale = Boolean(analysis) && analysisKey !== filterKey

  return (
    <section ref={ref} className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{group.l1} › {group.l2}</div>
          <h3 className="truncate text-sm font-semibold tracking-tight" title={breadcrumb}>{group.l3}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span
            className={cn(
              'rounded px-2 py-0.5 text-[11px] font-medium',
              verdict === 'accepted' && 'bg-emerald-500/15 text-emerald-600',
              verdict === 'denied' && 'bg-rose-500/15 text-rose-600',
              verdict === 'mixed' && 'bg-amber-500/15 text-amber-700',
              verdict === 'pending' && 'bg-muted text-muted-foreground',
            )}
          >
            {VERDICT_LABEL[verdict]}
          </span>
          <button
            type="button"
            onClick={() => onSignoffAll('yes')}
            className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted"
          >
            Accept all
          </button>
          <button
            type="button"
            onClick={() => onSignoffAll('no')}
            className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-muted"
          >
            Deny all
          </button>
        </div>
      </div>

      {/* filter bar */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          {ALL_GRAINS.map((g) => {
            const enabled = grains.includes(g)
            return (
              <button
                key={g}
                type="button"
                disabled={!enabled}
                onClick={() => enabled && setGrain(g)}
                title={enabled ? '' : 'Not available at this data granularity'}
                className={cn(
                  'px-2.5 py-1 text-xs transition-colors',
                  grain === g ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted',
                  !enabled && 'cursor-not-allowed opacity-40',
                )}
              >
                {GRAIN_LABELS[g]}
              </button>
            )
          })}
        </div>
        <MultiMenu label="Source" options={opts?.sources ?? []} value={sources} onChange={setSources} />
        {/* DATA-004: L4–L8 cascade. Selecting a level narrows every level below it and
            the indicator list. A level with no options renders disabled rather than
            vanishing, so the hierarchy reads the same whatever the data covers. */}
        {DRILL_LEVELS.map((lvl) => {
          const levelOptions = opts?.[lvl] ?? []
          if (!levelOptions.length && !levels[lvl]) {
            return <DisabledMenu key={lvl} label={LEVEL_LABEL[lvl]} />
          }
          return (
            <SingleMenu
              key={lvl}
              label={LEVEL_LABEL[lvl]}
              options={levelOptions}
              value={levels[lvl]}
              onChange={(v) => setLevel(lvl, v)}
            />
          )
        })}
        <MultiMenu
          label={indicatorLabel}
          options={indicatorOptions}
          value={indicators}
          onChange={setIndicators}
        />
        <MultiMenu label="Brand" options={opts?.brand ?? []} value={brand} onChange={setBrand} />
        <MultiMenu label="Channel" options={opts?.channelType ?? []} value={channelType} onChange={setChannelType} />
        <MultiMenu label="Region" options={opts?.provinceGroup ?? []} value={provinceGroup} onChange={setProvinceGroup} />
      </div>

      {/* DATA-004: current drill path, shared with chart, table and export. */}
      {res?.breadcrumb && res.breadcrumb.length > 1 && (
        <div className="mb-2 -mt-1 text-[11px] text-muted-foreground">
          {res.breadcrumb.map((b) => `${b.level}: ${b.value}`).join('  ›  ')}
        </div>
      )}

      {/* chart */}
      {loading && !res ? (
        <div className="grid h-[280px] place-items-center text-xs text-muted-foreground">Loading series…</div>
      ) : error ? (
        <div className="grid h-[280px] place-items-center px-6 text-center text-xs text-rose-600">{error}</div>
      ) : res && (res.kpi || res.series.length) ? (
        <ValidationChart x={res.x} kpi={res.kpi} series={res.series} />
      ) : (
        <div className="grid h-[280px] place-items-center px-6 text-center text-xs text-muted-foreground">
          {res && !res.kpi
            ? 'No sell-out KPI metric published — publish a Y-tagged metric to see the sales backdrop.'
            : 'No indicator data for this factor under the current filters.'}
        </div>
      )}

      <ChartAnalysisBlock
        analysis={analysis}
        loading={analysisLoading}
        stale={analysisStale}
        error={analysisError}
        onGenerate={generate}
        onAsk={() => stageMentions([
          // The table carries the filter state so the backend re-resolves the
          // exact rows this card is showing rather than trusting a client copy.
          { kind: 'chartTable', refId: group.l3, label: `${group.l3} · data table`,
            payload: query as unknown as Record<string, unknown> },
          ...(analysis
            ? [{ kind: 'chartAnalysis' as const, refId: analysis.key,
                 label: `${group.l3} · AI analysis` }]
            : []),
        ])}
      />

      <IndicatorSignoffList pairs={group.pairs ?? []} signoffs={signoffs} onSignoffPair={onSignoffPair} />

      {res && <ComparisonBlock res={res} />}
      {res && <YearlyTable res={res} yoyMonth={yoyMonth} onYoyMonth={setYoyMonth} />}

      {group.interpretation && (
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{group.interpretation}</p>
      )}
    </section>
  )
}

/** A cascade level with nothing to offer under the current path. Shown, not hidden,
 *  so the L4→L8 ladder does not appear to change length as you drill. */
function DisabledMenu({ label }: { label: string }) {
  return (
    <span
      title="Not available under the current drill path"
      className="cursor-not-allowed rounded-md border border-dashed border-border px-2.5 py-1 text-xs text-muted-foreground/50"
    >
      {label}
    </span>
  )
}


interface ChartsTabProps {
  projectId: string
  data: ValidationReviewData
}

/**
 * The default Business-Validation surface: one rich FactorCard per factor (L3),
 * each charting the sell-out KPI backdrop against the factor's own indicators with
 * grain / drilldown / dimension filters, a shared time-window comparison, per-year
 * table and per-indicator sign-off.
 */
export function ChartsTab({ projectId, data }: ChartsTabProps) {
  const signoffs = useSimStore((s) => s.signoffs)
  const setSignoff = useSimStore((s) => s.setSignoff)

  // Denials are the consequential verdict — an explicit 'no' excludes an
  // indicator (or, via l3, every indicator under a factor) from the model.
  const denied = Object.values(signoffs).filter((v) => v === 'no').length

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
      <header className="rounded-xl border border-border bg-muted/30 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold tracking-tight">Business Validation · {data.groups.length} factors</h2>
          {/* The response is read-only here: it is decided at 2.1 Data Processing,
              and this surface plots what the model will actually be fitted on. */}
          <span className="text-xs text-muted-foreground">
            Response Y: <span className="font-medium text-foreground">{data.kpiMetric || '—'}</span> · {denied} denied
          </span>
        </div>
        {data.note && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{data.note}</p>}
        {data.anomalies.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {data.anomalies.slice(0, 8).map((a, i) => (
              <span key={i} className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] text-amber-700">
                {a.channel} {a.year} {a.growthPct >= 0 ? '+' : ''}{a.growthPct}%
              </span>
            ))}
          </div>
        )}
      </header>

      {/* An L3 name can repeat across different L1/L2 branches ("Promotional
          Offers" appears under two parents), so the key carries the whole path —
          keying on l3 alone silently collapsed two factors into one card. */}
      {data.groups.map((g) => (
        <FactorCard
          key={`${g.l1}›${g.l2}›${g.l3}`}
          group={g}
          projectId={projectId}
          signoffs={signoffs}
          onSignoffPair={(pair, verdict) => void setSignoff({ l4: pair.l4, indicator: pair.indicator }, verdict)}
          onSignoffAll={(verdict) => void setSignoff({ l3: g.l3 }, verdict)}
        />
      ))}
    </div>
  )
}
