import { useMemo, useState } from 'react'
import {
  Area,
  Bar,
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { RotateCcw, SlidersHorizontal } from 'lucide-react'

import { cn } from '../../../lib/cn'
import type { ValidationKpi, ValidationOverlay } from '../../../lib/types'

// Overlay palette (indigo / amber / rose / violet); the KPI area uses a muted teal
// so the sell-out backdrop reads as context rather than a competing series.
const OVERLAY_COLORS = [
  'oklch(58% 0.19 266)',
  'oklch(72% 0.17 64)',
  'oklch(63% 0.21 17)',
  'oklch(60% 0.19 305)',
  'oklch(55% 0.14 230)',
  'oklch(68% 0.15 140)',
]
const KPI_COLOR = 'oklch(64% 0.13 195)'
const AXIS = { fontSize: 11, fill: 'var(--muted-foreground, #71717a)' } as const
const GRID = 'var(--border, #e4e4e7)'

function compact(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e8) return `${(n / 1e8).toFixed(1)}亿`
  if (a >= 1e4) return `${(n / 1e4).toFixed(1)}万`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  return `${Math.round(n * 100) / 100}`
}

/** DATA-008/009: format a tooltip/axis value per its indicator metadata. */
function fmtMeta(n: number, numberFormat?: string, unit?: string): string {
  if (numberFormat === 'percent') return `${Math.round(n * 10) / 10}%`
  const s = compact(n)
  return numberFormat === 'money' ? `${unit || '¥'}${s}` : s
}

function tickInterval(n: number): number {
  return n <= 12 ? 0 : Math.ceil(n / 8) - 1
}

interface SeriesMeta {
  unit?: string
  numberFormat?: string
  aggregation?: string
}

/** A manual axis bound. Empty string means "let recharts fit the data". */
type Bound = string
interface AxisRange {
  driversMin: Bound
  driversMax: Bound
  responseMin: Bound
  responseMax: Bound
}
const NO_RANGE: AxisRange = { driversMin: '', driversMax: '', responseMin: '', responseMax: '' }

/** Turn a pair of manual bounds into a recharts domain, falling back per side. */
function domainOf(min: Bound, max: Bound): [number | 'auto', number | 'auto'] {
  const lo = min.trim() === '' || Number.isNaN(Number(min)) ? 'auto' : Number(min)
  const hi = max.trim() === '' || Number.isNaN(Number(max)) ? 'auto' : Number(max)
  return [lo, hi]
}

interface ValidationChartProps {
  x: string[]
  kpi: ValidationKpi | null
  series: ValidationOverlay[]
}

/**
 * The factor chart: the response as a filled area on the **right** axis, every
 * driver on the **left**.
 *
 * The response and its drivers live in unrelated units (cases vs ¥ vs %), so they
 * cannot share a scale. Putting the drivers — the things the chart exists to
 * compare against each other — on the primary left axis, and the response on the
 * secondary right one, means the axis you read by default is the axis most of the
 * plotted series are actually on.
 *
 * Both scales and the time span are user-adjustable: `auto` fits the visible data,
 * and any bound the user types wins for that side only (`allowDataOverflow` makes a
 * manual bound actually clip rather than being widened back out to fit).
 */
export function ValidationChart({ x, kpi, series }: ValidationChartProps) {
  // DATA-009: click a legend entry to hide/show a series; recharts recomputes the
  // axis domain from the still-visible series (hidden series drop out of the scale).
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const toggle = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  // Axis bounds and the brush window are deliberately component-local and never
  // reconciled from the store: the project state poll replaces its slices every
  // 1.5s and would otherwise reset an axis mid-edit.
  const [range, setRange] = useState<AxisRange>(NO_RANGE)
  const [rangeOpen, setRangeOpen] = useState(false)
  const [brush, setBrush] = useState<{ startIndex?: number; endIndex?: number }>({})

  const data = useMemo(
    () =>
      x.map((label, i) => {
        const row: Record<string, number | string | null> = { x: label }
        if (kpi) row[kpi.metric] = kpi.data[i] ?? null
        for (const s of series) row[s.metric] = s.data[i]
        return row
      }),
    [x, kpi, series],
  )
  const interval = tickInterval(x.length)

  // Per-series metadata for the tooltip (unit / format / aggregation — DATA-008).
  const meta: Record<string, SeriesMeta> = {}
  if (kpi) meta[kpi.metric] = { unit: kpi.unit, numberFormat: kpi.numberFormat, aggregation: kpi.aggregation }
  for (const s of series) meta[s.metric] = { unit: s.unit, numberFormat: s.numberFormat, aggregation: s.aggregation }

  const zoomed = Boolean(
    range.driversMin || range.driversMax || range.responseMin || range.responseMax)
  const brushed =
    brush.startIndex != null &&
    (brush.startIndex > 0 || (brush.endIndex ?? x.length - 1) < x.length - 1)

  const reset = () => {
    setRange(NO_RANGE)
    setBrush({})
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-end gap-1.5">
        {(zoomed || brushed) && (
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11px]
                       text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <RotateCcw className="h-3 w-3" /> Reset view
          </button>
        )}
        <button
          type="button"
          aria-expanded={rangeOpen}
          onClick={() => setRangeOpen((v) => !v)}
          className={cn(
            'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] transition-colors',
            zoomed
              ? 'border-primary/40 bg-primary/5 text-primary'
              : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground',
          )}
        >
          <SlidersHorizontal className="h-3 w-3" /> Axis range
        </button>
      </div>

      {rangeOpen && (
        <div className="mb-2 rounded-lg border border-border bg-muted/30 p-2.5">
          <div className="grid gap-2 sm:grid-cols-2">
            <AxisBounds
              legend="Left axis · drivers"
              min={range.driversMin}
              max={range.driversMax}
              onMin={(v) => setRange((r) => ({ ...r, driversMin: v }))}
              onMax={(v) => setRange((r) => ({ ...r, driversMax: v }))}
            />
            <AxisBounds
              legend={`Right axis · ${kpi?.metric ?? 'response'}`}
              min={range.responseMin}
              max={range.responseMax}
              onMin={(v) => setRange((r) => ({ ...r, responseMin: v }))}
              onMax={(v) => setRange((r) => ({ ...r, responseMax: v }))}
            />
          </div>
          <p className="mt-1.5 text-[10.5px] text-muted-foreground">
            Leave a bound empty to fit it to the data. Drag the strip under the chart to narrow the time span.
          </p>
        </div>
      )}

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 10, right: 8, left: 4, bottom: 4 }}>
          <defs>
            <linearGradient id="kpiFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={KPI_COLOR} stopOpacity={0.22} />
              <stop offset="100%" stopColor={KPI_COLOR} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="x" tick={AXIS} interval={interval} tickLine={false} axisLine={{ stroke: GRID }} />
          {/* Drivers on the primary (left) axis. */}
          <YAxis
            yAxisId="ov"
            tick={AXIS}
            tickFormatter={compact}
            tickLine={false}
            axisLine={false}
            width={46}
            domain={domainOf(range.driversMin, range.driversMax)}
            allowDataOverflow
          />
          {/* The response on the secondary (right) axis. */}
          <YAxis
            yAxisId="kpi"
            orientation="right"
            tick={AXIS}
            tickFormatter={compact}
            tickLine={false}
            axisLine={false}
            width={46}
            domain={domainOf(range.responseMin, range.responseMax)}
            allowDataOverflow
          />
          <Tooltip
            contentStyle={{ background: 'var(--popover, #fff)', border: `1px solid ${GRID}`, borderRadius: 8, fontSize: 12 }}
            formatter={(v: unknown, _name: unknown, item: unknown) => {
              if (v == null) return ['—', String(_name)]
              const key = String((item as { dataKey?: string })?.dataKey ?? _name)
              const m = meta[key]
              const val = fmtMeta(Number(v), m?.numberFormat, m?.unit)
              return [m?.aggregation ? `${val} · ${m.aggregation}` : val, String(_name)]
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, cursor: 'pointer' }}
            iconType="plainline"
            onClick={(e: unknown) => {
              const p = e as { dataKey?: string; value?: string }
              toggle(String(p.dataKey ?? p.value ?? ''))
            }}
          />
          {kpi && (
            <Area
              yAxisId="kpi"
              type="monotone"
              dataKey={kpi.metric}
              name={`${kpi.metric} (Y)`}
              stroke={KPI_COLOR}
              strokeWidth={1.5}
              fill="url(#kpiFill)"
              isAnimationActive={false}
              dot={false}
              hide={hidden.has(kpi.metric)}
            />
          )}
          {series.map((s, i) => {
            const color = OVERLAY_COLORS[i % OVERLAY_COLORS.length]
            if (s.kind === 'bar') {
              return (
                <Bar
                  key={s.metric}
                  yAxisId="ov"
                  dataKey={s.metric}
                  name={s.metric}
                  fill={color}
                  opacity={0.55}
                  radius={[3, 3, 0, 0]}
                  maxBarSize={26}
                  isAnimationActive={false}
                  hide={hidden.has(s.metric)}
                />
              )
            }
            return (
              <Line
                key={s.metric}
                yAxisId="ov"
                type="monotone"
                dataKey={s.metric}
                name={s.metric}
                stroke={color}
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
                hide={hidden.has(s.metric)}
              />
            )
          })}
          {x.length > 3 && (
            <Brush
              dataKey="x"
              height={18}
              travellerWidth={8}
              stroke={GRID}
              fill="transparent"
              startIndex={brush.startIndex}
              endIndex={brush.endIndex}
              onChange={(r: unknown) => {
                const b = r as { startIndex?: number; endIndex?: number }
                setBrush({ startIndex: b.startIndex, endIndex: b.endIndex })
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/** One axis's min/max pair. Empty means "fit to data" for that bound alone. */
function AxisBounds({
  legend, min, max, onMin, onMax,
}: {
  legend: string
  min: Bound
  max: Bound
  onMin: (v: string) => void
  onMax: (v: string) => void
}) {
  const cls =
    'w-full rounded border border-border bg-background px-1.5 py-0.5 text-[11px] tabular-nums ' +
    'transition-colors hover:border-foreground/40 focus:border-foreground/60 focus:outline-none ' +
    'focus:ring-1 focus:ring-foreground/20'
  return (
    <fieldset className="min-w-0">
      <legend className="mb-1 truncate text-[10px] uppercase tracking-[0.14em] text-muted-foreground" title={legend}>
        {legend}
      </legend>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          inputMode="decimal"
          placeholder="min"
          aria-label={`${legend} minimum`}
          value={min}
          onChange={(e) => onMin(e.target.value)}
          className={cls}
        />
        <span className="text-[11px] text-muted-foreground">–</span>
        <input
          type="number"
          inputMode="decimal"
          placeholder="max"
          aria-label={`${legend} maximum`}
          value={max}
          onChange={(e) => onMax(e.target.value)}
          className={cls}
        />
      </div>
    </fieldset>
  )
}
