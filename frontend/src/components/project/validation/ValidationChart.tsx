import { useState } from 'react'
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
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

interface ValidationChartProps {
  x: string[]
  kpi: ValidationKpi | null
  series: ValidationOverlay[]
}

export function ValidationChart({ x, kpi, series }: ValidationChartProps) {
  // DATA-009: click a legend entry to hide/show a series; recharts recomputes the
  // axis domain from the still-visible series (hidden series drop out of the scale).
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const toggle = (key: string) =>
    setHidden((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const data = x.map((label, i) => {
    const row: Record<string, number | string | null> = { x: label }
    if (kpi) row[kpi.metric] = kpi.data[i] ?? null
    for (const s of series) row[s.metric] = s.data[i]
    return row
  })
  const interval = tickInterval(x.length)

  // Per-series metadata for the tooltip (unit / format / aggregation — DATA-008).
  const meta: Record<string, SeriesMeta> = {}
  if (kpi) meta[kpi.metric] = { unit: kpi.unit, numberFormat: kpi.numberFormat, aggregation: kpi.aggregation }
  for (const s of series) meta[s.metric] = { unit: s.unit, numberFormat: s.numberFormat, aggregation: s.aggregation }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 10, right: 8, left: 4, bottom: 4 }}>
        <defs>
          <linearGradient id="kpiFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={KPI_COLOR} stopOpacity={0.22} />
            <stop offset="100%" stopColor={KPI_COLOR} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="x" tick={AXIS} interval={interval} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis
          yAxisId="kpi"
          tick={AXIS}
          tickFormatter={compact}
          tickLine={false}
          axisLine={false}
          width={46}
        />
        <YAxis
          yAxisId="ov"
          orientation="right"
          tick={AXIS}
          tickFormatter={compact}
          tickLine={false}
          axisLine={false}
          width={46}
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
            name={`${kpi.metric} (KPI)`}
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
      </ComposedChart>
    </ResponsiveContainer>
  )
}
