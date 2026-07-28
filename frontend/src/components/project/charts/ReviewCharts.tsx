import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import type { ReviewChart } from '../../../lib/types'

// Intentional, restrained palette (indigo / amber / teal / rose) — not default recharts blue.
const COLORS = ['oklch(58% 0.19 266)', 'oklch(72% 0.17 64)', 'oklch(64% 0.13 195)', 'oklch(63% 0.21 17)']

function compact(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e8) return `${(n / 1e8).toFixed(1)}亿`
  if (a >= 1e4) return `${(n / 1e4).toFixed(1)}万`
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  return `${Math.round(n * 100) / 100}`
}

const AXIS = { fontSize: 11, fill: 'var(--muted-foreground, #71717a)' } as const
const GRID = 'var(--border, #e4e4e7)'

function rows(chart: ReviewChart): Record<string, number | string>[] {
  return chart.x.map((label, i) => {
    const row: Record<string, number | string> = { x: label }
    for (const s of chart.series) row[s.name] = s.data[i]
    return row
  })
}

// Thin out dense monthly tick labels so the axis stays readable.
function tickInterval(n: number): number {
  return n <= 12 ? 0 : Math.ceil(n / 8) - 1
}

const tooltipStyle = {
  contentStyle: {
    background: 'var(--popover, #fff)',
    border: `1px solid ${GRID}`,
    borderRadius: 8,
    fontSize: 12,
  },
  formatter: (v: unknown) => compact(Number(v)),
}

export function ReviewChartView({ chart }: { chart: ReviewChart }) {
  const data = rows(chart)
  const left = chart.series.filter((s) => s.axis !== 'right')
  const right = chart.series.filter((s) => s.axis === 'right')
  const interval = tickInterval(chart.x.length)

  if (chart.type === 'bar') {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="x" tick={AXIS} interval={interval} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickFormatter={compact} tickLine={false} axisLine={false} width={44} />
          <Tooltip {...tooltipStyle} />
          {chart.series.map((s, i) => (
            <Bar key={s.name} dataKey={s.name} fill={COLORS[i % COLORS.length]} radius={[3, 3, 0, 0]} maxBarSize={38} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chart.type === 'dualAxis') {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 4, bottom: 4 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="x" tick={AXIS} interval={interval} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis yAxisId="left" tick={AXIS} tickFormatter={compact} tickLine={false} axisLine={false} width={44} />
          <YAxis yAxisId="right" orientation="right" tick={AXIS} tickFormatter={compact} tickLine={false} axisLine={false} width={44} />
          <Tooltip {...tooltipStyle} />
          {left.map((s, i) => (
            <Line yAxisId="left" key={s.name} type="monotone" dataKey={s.name} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
          ))}
          {right.map((s, i) => (
            <Bar yAxisId="right" key={s.name} dataKey={s.name} fill={COLORS[(i + 1) % COLORS.length]} opacity={0.45} radius={[3, 3, 0, 0]} maxBarSize={26} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    )
  }

  if (chart.type === 'waterfall') {
    // Diverging bars anchored at zero: teal = increase, rose = decrease.
    const s = chart.series[0]
    const UP = 'oklch(64% 0.13 195)'
    const DOWN = 'oklch(63% 0.21 17)'
    return (
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="x" tick={AXIS} interval={0} tickLine={false} axisLine={{ stroke: GRID }} angle={-20} textAnchor="end" height={54} />
          <YAxis tick={AXIS} tickFormatter={compact} tickLine={false} axisLine={false} width={44} />
          <Tooltip {...tooltipStyle} />
          <ReferenceLine y={0} stroke={GRID} />
          <Bar dataKey={s?.name ?? 'Δ'} radius={[3, 3, 0, 0]} maxBarSize={44}>
            {data.map((row, i) => (
              <Cell key={i} fill={Number(row[s?.name ?? 'Δ']) >= 0 ? UP : DOWN} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chart.type === 'quadrant') {
    const pts = chart.points ?? []
    const midX = pts.length ? pts.reduce((s, p) => s + p.x, 0) / pts.length : 0
    const midY = pts.length ? pts.reduce((s, p) => s + p.y, 0) / pts.length : 0
    return (
      <ResponsiveContainer width="100%" height={240}>
        <ScatterChart margin={{ top: 10, right: 16, left: 4, bottom: 14 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" name="份额" unit="%" tick={AXIS} tickFormatter={compact} axisLine={{ stroke: GRID }}
            label={{ value: '份额 →', position: 'insideBottomRight', offset: -4, fontSize: 10, fill: AXIS.fill }} />
          <YAxis type="number" dataKey="y" name="增长" unit="%" tick={AXIS} tickFormatter={compact} axisLine={{ stroke: GRID }}
            label={{ value: '增长 ↑', position: 'insideTopLeft', fontSize: 10, fill: AXIS.fill }} />
          <ZAxis range={[80, 80]} />
          <ReferenceLine x={midX} stroke={GRID} />
          <ReferenceLine y={midY} stroke={GRID} />
          <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={pts} fill={COLORS[0]}>
            <LabelList dataKey="label" position="top" style={{ fontSize: 10, fill: AXIS.fill }} />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // line / share — single or multi-line trend
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="x" tick={AXIS} interval={interval} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis tick={AXIS} tickFormatter={compact} tickLine={false} axisLine={false} width={44} />
        <Tooltip {...tooltipStyle} />
        {chart.series.map((s, i) => (
          <Line key={s.name} type="monotone" dataKey={s.name} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
