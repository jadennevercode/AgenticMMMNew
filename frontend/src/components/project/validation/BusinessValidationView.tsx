import { useEffect, useRef, useState } from 'react'
import type {
  ArtifactInstance,
  TimeWindow,
  ValidationGroup,
  ValidationSeriesResponse,
} from '../../../lib/types'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'
import { asValidation } from '../../../lib/artifact-format'
import { cn } from '../../../lib/cn'
import { ValidationChart } from './ValidationChart'

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

function YearlyTable({ res }: { res: ValidationSeriesResponse }) {
  const { years, rows } = res.yearly
  if (!years.length || !rows.length) return null
  return (
    <div className="mt-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/40 text-left text-muted-foreground">
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

interface FactorCardProps {
  group: ValidationGroup
  projectId: string
  editing: boolean
  timeWindowId: string
  onSignoff: (l3: string, value: 'yes' | 'no') => void
}

function FactorCard({ group, projectId, editing, timeWindowId, onSignoff }: FactorCardProps) {
  const ref = useRef<HTMLElement>(null)
  const [inView, setInView] = useState(false)
  const [grain, setGrain] = useState('month')
  const [sources, setSources] = useState<string[]>([])
  const [kpiMetric, setKpiMetric] = useState('')  // DATA-009: KPI Volume/Value backdrop
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

  const filterKey = [
    grain,
    timeWindowId,
    kpiMetric,
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
    setLoading(true)
    setError('')
    api
      .validationSeries(projectId, {
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
        timeWindowId: timeWindowId || undefined,
        kpiMetric: kpiMetric || undefined,
      })
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

  const opts = res?.options
  const grains = opts?.grains ?? ['year', 'month']
  const breadcrumb = [group.l1, group.l2, group.l3].filter(Boolean).join(' › ')

  return (
    <section ref={ref} className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{group.l1} › {group.l2}</div>
          <h3 className="truncate text-sm font-semibold tracking-tight" title={breadcrumb}>{group.l3}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <span className="text-[10px] text-muted-foreground">Sign-off</span>
          {(['yes', 'no'] as const).map((v) => (
            <button
              key={v}
              type="button"
              disabled={!editing}
              onClick={() => onSignoff(group.l3, v)}
              className={cn(
                'rounded px-2 py-0.5 text-[11px] font-medium transition-colors',
                group.signoff === v
                  ? v === 'yes'
                    ? 'bg-emerald-500/15 text-emerald-600'
                    : 'bg-rose-500/15 text-rose-600'
                  : 'border border-border text-muted-foreground hover:bg-muted',
                !editing && 'cursor-not-allowed opacity-60',
              )}
            >
              {v === 'yes' ? 'Y' : 'N'}
            </button>
          ))}
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
        {/* DATA-009: KPI Volume/Value switcher — only when the project has more than one
            KPI. Switching only changes this chart's backdrop, never the OLS default Y. */}
        {(opts?.kpiMetrics?.length ?? 0) > 1 && (
          <div className="inline-flex overflow-hidden rounded-md border border-border" title="KPI backdrop">
            {opts!.kpiMetrics.map((k) => {
              const active = (res?.kpiMetric ?? '') === k.metric
              const label = k.semanticType === 'kpi_value' ? 'Value' : k.semanticType === 'kpi_volume' ? 'Volume' : k.metric
              return (
                <button
                  key={k.metric}
                  type="button"
                  onClick={() => setKpiMetric(k.metric)}
                  title={k.metric}
                  className={cn(
                    'px-2.5 py-1 text-xs transition-colors',
                    active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted',
                  )}
                >
                  {label}
                </button>
              )
            })}
          </div>
        )}
        <MultiMenu label="Source" options={opts?.sources ?? []} value={sources} onChange={setSources} />
        {/* DATA-004: L4–L8 cascade. Each level shows only when it has options (or holds a
            value); selecting one narrows the levels below it. */}
        {DRILL_LEVELS.map((lvl) => {
          const levelOptions = opts?.[lvl] ?? []
          if (!levelOptions.length && !levels[lvl]) return null
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
          label="Indicator"
          options={(opts?.indicators ?? []).map((i) => i.metric)}
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

      {res && <ComparisonBlock res={res} />}
      {res && <YearlyTable res={res} />}

      {group.interpretation && (
        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{group.interpretation}</p>
      )}
    </section>
  )
}

/** DATA-005: project-level time-window picker + inline "create window" form. The
 * chosen window is applied across every factor card (one shared time口径). */
function TimeWindowBar({
  projectId,
  value,
  onChange,
}: {
  projectId: string
  value: string
  onChange: (id: string) => void
}) {
  const [windows, setWindows] = useState<TimeWindow[]>([])
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', currentStart: '', currentEnd: '', comparisonType: 'yoy' })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!projectId) return
    api.getTimeWindows(projectId).then(setWindows).catch(() => undefined)
  }, [projectId])

  const save = async () => {
    if (!form.name.trim() || !/^\d{4}-\d{2}$/.test(form.currentStart) || !/^\d{4}-\d{2}$/.test(form.currentEnd)) {
      setErr('Enter a name and YYYY-MM start/end')
      return
    }
    setSaving(true)
    setErr('')
    const next: TimeWindow = {
      id: `tw-${Date.now()}`, name: form.name.trim(), periodType: 'custom',
      currentStart: form.currentStart, currentEnd: form.currentEnd,
      comparisonType: form.comparisonType as TimeWindow['comparisonType'],
      comparisonStart: '', comparisonEnd: '', rollingMonths: 0, version: 1,
    }
    try {
      const saved = await api.putTimeWindows(projectId, [...windows, next])
      setWindows(saved)
      onChange(next.id)
      setCreating(false)
      setForm({ name: '', currentStart: '', currentEnd: '', comparisonType: 'yoy' })
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const inputCls = 'rounded border border-border bg-background px-2 py-1 text-xs'
  return (
    <div className="mt-2.5 flex flex-wrap items-center gap-2">
      <span className="text-[11px] text-muted-foreground">Time window</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>
        <option value="">Full range (no comparison)</option>
        {windows.map((w) => (
          <option key={w.id} value={w.id}>{w.name}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => setCreating((v) => !v)}
        className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
      >
        {creating ? 'Cancel' : '+ New'}
      </button>
      {creating && (
        <div className="flex flex-wrap items-center gap-1.5">
          <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={cn(inputCls, 'w-36')} />
          <input placeholder="Start YYYY-MM" value={form.currentStart} onChange={(e) => setForm({ ...form, currentStart: e.target.value })} className={cn(inputCls, 'w-28')} />
          <input placeholder="End YYYY-MM" value={form.currentEnd} onChange={(e) => setForm({ ...form, currentEnd: e.target.value })} className={cn(inputCls, 'w-28')} />
          <select value={form.comparisonType} onChange={(e) => setForm({ ...form, comparisonType: e.target.value })} className={inputCls}>
            <option value="yoy">YoY (same span, prior year)</option>
            <option value="pop">Prev. period</option>
            <option value="none">No comparison</option>
          </select>
          <button type="button" disabled={saving} onClick={save} className="rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground disabled:opacity-60">
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
      {err && <span className="text-[11px] text-rose-600">{err}</span>}
    </div>
  )
}

export function BusinessValidationView({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const editArtifact = useSimStore((s) => s.editArtifact)
  const projectId = useSimStore((s) => s.activeProjectId)
  const [windowId, setWindowId] = useState('')  // DATA-005: shared across all cards
  const data = asValidation(inst.body)

  if (!data || !data.groups.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        Business Validation is not ready yet — run task 2.3 to chart each factor against sell-out.
      </div>
    )
  }

  const setSignoff = (l3: string, value: 'yes' | 'no') =>
    editArtifact(inst.id, {
      body: {
        ...data,
        groups: data.groups.map((g) =>
          g.l3 !== l3 ? g : { ...g, signoff: g.signoff === value ? '' : value },
        ),
      },
    })

  const signedOff = data.groups.filter((g) => g.signoff === 'yes').length

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
      <header className="rounded-xl border border-border bg-muted/30 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold tracking-tight">Business Validation · {data.groups.length} factors</h2>
          <span className="text-xs text-muted-foreground">
            KPI backdrop: <span className="font-medium text-foreground">{data.kpiMetric || '—'}</span> · signed off {signedOff}/{data.groups.length}
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
        {projectId && <TimeWindowBar projectId={projectId} value={windowId} onChange={setWindowId} />}
      </header>

      {projectId &&
        data.groups.map((g) => (
          <FactorCard key={g.l3} group={g} projectId={projectId} editing={editing} timeWindowId={windowId} onSignoff={setSignoff} />
        ))}
    </div>
  )
}
