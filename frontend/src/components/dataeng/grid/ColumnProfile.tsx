import type { ColumnStat } from '../../../lib/types'
import { cn } from '../../../lib/cn'

/**
 * The distribution strip under a grid column's name.
 *
 * Profiling belongs where the data is, not on a separate report tab: the shape of
 * a column is what tells you whether the step above it did the right thing. Numeric
 * columns get their histogram, categorical columns their value mix, and every
 * column its missing-value share.
 */

const CATEGORY_TONES = [
  'bg-primary/70', 'bg-primary/45', 'bg-primary/30',
  'bg-foreground/25', 'bg-foreground/15', 'bg-foreground/10',
]

export function ColumnProfile({ stat }: { stat: ColumnStat | undefined }) {
  if (!stat) return <div className="h-6" />
  const hasHistogram = stat.histogram.length > 0
  const hasTop = stat.top.length > 0

  return (
    <div className="space-y-1">
      <div className="flex h-5 items-end gap-px" aria-hidden>
        {hasHistogram && <Histogram buckets={stat.histogram} min={stat.min} max={stat.max} />}
        {!hasHistogram && hasTop && <ValueMix top={stat.top} />}
        {!hasHistogram && !hasTop && <div className="h-px w-full bg-border" />}
      </div>
      <div className="flex items-center gap-1.5 text-[9px] font-normal tabular-nums text-muted-foreground">
        <span className={cn(stat.nullPct > 0 && 'text-amber-600')}>
          {stat.nullPct > 0 ? `${stat.nullPct}% null` : 'complete'}
        </span>
        {stat.distinct > 0 && <span className="text-muted-foreground/60">·</span>}
        {stat.distinct > 0 && <span>{stat.distinct.toLocaleString()} distinct</span>}
      </div>
    </div>
  )
}

function Histogram({ buckets, min, max }: { buckets: number[]; min: string; max: string }) {
  const peak = Math.max(...buckets, 1)
  const lo = Number(min)
  const hi = Number(max)
  const width = Number.isFinite(lo) && Number.isFinite(hi) ? (hi - lo) / buckets.length : 0
  return (
    <>
      {buckets.map((n, i) => (
        <span
          key={i}
          title={width > 0
            ? `${fmt(lo + i * width)} – ${fmt(lo + (i + 1) * width)}: ${n.toLocaleString()} rows`
            : `${n.toLocaleString()} rows`}
          className="min-w-0 flex-1 rounded-t-[1px] bg-primary/40"
          style={{ height: `${Math.max(8, (n / peak) * 100)}%` }}
        />
      ))}
    </>
  )
}

function ValueMix({ top }: { top: [string, number][] }) {
  const total = top.reduce((sum, [, n]) => sum + n, 0) || 1
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-sm">
      {top.map(([value, n], i) => (
        <span
          key={value}
          title={`${value}: ${n.toLocaleString()} rows`}
          className={cn('h-full', CATEGORY_TONES[i % CATEGORY_TONES.length])}
          style={{ width: `${(n / total) * 100}%` }}
        />
      ))}
    </div>
  )
}

const fmt = (n: number) =>
  Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : n.toLocaleString(undefined, { maximumFractionDigits: 2 })
