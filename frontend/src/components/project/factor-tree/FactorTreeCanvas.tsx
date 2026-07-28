import { type ReactNode, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Lock } from 'lucide-react'

import { cn } from '../../../lib/cn'
import type { FactorCanvasRow, FactorCanvasTone } from './types'

const TONE: Record<FactorCanvasTone, string> = {
  ok: 'bg-emerald-500/15 text-emerald-600',
  warn: 'bg-amber-500/15 text-amber-600',
  bad: 'bg-rose-500/15 text-rose-600',
  muted: 'bg-muted text-muted-foreground',
}

/** A row plus its vertical-merge flags: whether each L-level is the first of its run. */
interface Laid {
  row: FactorCanvasRow
  groupKey: string // l1›l2›l3 — the collapse unit
  firstL1: boolean
  firstL2: boolean
  firstL3: boolean
  groupFirst: boolean // first row of this l1›l2›l3 group
  groupCount: number
}

function layout(rows: FactorCanvasRow[]): Laid[] {
  const out: Laid[] = []
  const counts = new Map<string, number>()
  for (const r of rows) {
    const g = `${r.l1}›${r.l2}›${r.l3}`
    counts.set(g, (counts.get(g) ?? 0) + 1)
  }
  let prev: FactorCanvasRow | undefined
  const seenGroup = new Set<string>()
  for (const row of rows) {
    const groupKey = `${row.l1}›${row.l2}›${row.l3}`
    const firstL1 = !prev || prev.l1 !== row.l1
    const firstL2 = firstL1 || prev!.l2 !== row.l2
    const firstL3 = firstL2 || prev!.l3 !== row.l3
    const groupFirst = !seenGroup.has(groupKey)
    seenGroup.add(groupKey)
    out.push({ row, groupKey, firstL1, firstL2, firstL3, groupFirst, groupCount: counts.get(groupKey) ?? 1 })
    prev = row
  }
  return out
}

/**
 * The FactorTree, rendered once and reused by every S2 module — now as a true
 * horizontal `L1 | L2 | L3 | L4 | Indicator | …columns | Status | Action` table.
 *
 * Repeated parent values are merged vertically (shown once per run), giving the
 * editorial-table hierarchy without a repeated-value grid. The component owns no
 * data and derives no verdicts: modules pass rows built from their own slice.
 *
 * **Uniform typography.** Every cell renders at the same weight and the same
 * colour. The hierarchy is carried by the column order and the vertical merge,
 * not by weight or opacity: the old ladder (semibold L1, 80%/70%/45%/40% opacity
 * per level, muted L4, medium Indicator) made a wide row read as five different
 * kinds of text and made a repeated parent look disabled. Emphasis is reserved
 * for the things that actually differ per row — the status chip and the blocked
 * state.
 */
export function FactorTreeCanvas({
  rows,
  columns = [],
  selectedKey,
  onSelect,
  actions,
  header,
  emptyHint = 'No factors to show yet.',
}: {
  rows: FactorCanvasRow[]
  columns?: string[]
  selectedKey?: string
  onSelect?: (key: string) => void
  actions?: (row: FactorCanvasRow) => ReactNode
  header?: ReactNode
  emptyHint?: string
}) {
  const laid = useMemo(() => layout(rows), [rows])
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  function toggle(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  if (!rows.length) {
    return (
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {header}
        <p className="mt-6 text-center text-xs text-muted-foreground">{emptyHint}</p>
      </div>
    )
  }

  const lastCols = 1 /*Status*/ + (actions ? 1 : 0)

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {header}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[11.5px]">
          <thead>
            <tr className="border-b border-border text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <th className="px-2 py-1.5 font-normal">L1</th>
              <th className="px-2 py-1.5 font-normal">L2</th>
              <th className="px-2 py-1.5 font-normal">L3</th>
              <th className="px-2 py-1.5 font-normal">L4</th>
              <th className="px-2 py-1.5 font-normal">Indicator</th>
              {columns.map((c) => (
                <th key={c} className="px-2 py-1.5 text-right font-normal">{c}</th>
              ))}
              <th className="px-2 py-1.5 font-normal">Status</th>
              {actions && <th className="px-2 py-1.5 font-normal">Action</th>}
            </tr>
          </thead>
          <tbody>
            {laid.map(({ row: r, groupKey, firstL1, firstL3, groupFirst, groupCount }) => {
              const isCollapsed = collapsed.has(groupKey)
              // A collapsed group shows only a single summary row (its first).
              if (isCollapsed && !groupFirst) return null
              const blocked = Boolean(r.blockedBy)
              if (isCollapsed) {
                return (
                  <tr key={groupKey} className="border-b border-border/40 bg-muted/20">
                    <td className="px-2 py-1 align-top">
                      <button
                        type="button"
                        onClick={() => toggle(groupKey)}
                        className="flex items-center gap-1 text-left hover:text-foreground"
                      >
                        <ChevronRight className="h-3 w-3 shrink-0" />
                        <span>{r.l1 || '—'}</span>
                      </button>
                    </td>
                    <td className="px-2 py-1 align-top">{r.l2}</td>
                    <td className="px-2 py-1 align-top">{r.l3}</td>
                    <td className="px-2 py-1 align-top text-muted-foreground" colSpan={2 + columns.length + lastCols}>
                      {groupCount} indicator{groupCount === 1 ? '' : 's'} — collapsed
                    </td>
                  </tr>
                )
              }
              return (
                <tr
                  key={r.key}
                  onClick={() => !blocked && onSelect?.(r.key)}
                  className={cn(
                    'border-b border-border/40',
                    firstL1 && 'border-t border-border/70',
                    blocked ? 'opacity-45' : 'cursor-pointer hover:bg-accent/50',
                    selectedKey === r.key && 'bg-accent',
                  )}
                >
                  {/* Every level shows its value on every row, at the same weight
                      and colour. The run-start flags now drive only the collapse
                      affordance and the group rule — never the type treatment. */}
                  <td className="px-2 py-1 align-top">{r.l1 || '—'}</td>
                  <td className="px-2 py-1 align-top">{r.l2}</td>
                  <td className="px-2 py-1 align-top">
                    {firstL3 ? (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); toggle(groupKey) }}
                        className="flex items-center gap-1 text-left hover:text-foreground"
                        title="Collapse this factor"
                      >
                        <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground/60" />
                        <span>{r.l3}</span>
                      </button>
                    ) : (
                      <span className="flex items-center gap-1 pl-4">{r.l3}</span>
                    )}
                  </td>
                  <td className="px-2 py-1 align-top">{r.l4}</td>
                  <td className="px-2 py-1 align-top">{r.indicator}</td>
                  {columns.map((c, i) => (
                    <td key={c} className="px-2 py-1 text-right align-top tabular-nums">
                      {r.cells?.[i] ?? ''}
                    </td>
                  ))}
                  <td className="px-2 py-1 align-top">
                    {blocked ? (
                      <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10.5px] bg-muted text-muted-foreground">
                        <Lock className="h-2.5 w-2.5" />
                        Denied @ {r.blockedBy}
                      </span>
                    ) : (
                      <span className={cn('rounded px-1.5 py-0.5 text-[10.5px]', TONE[r.tone])}>
                        {r.statusLabel}
                      </span>
                    )}
                  </td>
                  {actions && (
                    <td className="px-2 py-1 align-top" onClick={(e) => e.stopPropagation()}>
                      {blocked ? null : actions(r)}
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
