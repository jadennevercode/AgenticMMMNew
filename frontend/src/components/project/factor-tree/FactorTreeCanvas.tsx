import { Fragment, type ReactNode, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Lock } from 'lucide-react'

import { cn } from '../../../lib/cn'
import type { FactorCanvasRow, FactorCanvasTone } from './types'

const TONE: Record<FactorCanvasTone, string> = {
  ok: 'bg-emerald-500/15 text-emerald-600',
  warn: 'bg-amber-500/15 text-amber-600',
  bad: 'bg-rose-500/15 text-rose-600',
  muted: 'bg-muted text-muted-foreground',
}

interface Group {
  key: string
  l1: string
  l2: string
  l3: string
  rows: FactorCanvasRow[]
}

function groupRows(rows: FactorCanvasRow[]): Group[] {
  const out: Group[] = []
  const byKey = new Map<string, Group>()
  for (const r of rows) {
    const key = `${r.l1}›${r.l2}›${r.l3}`
    let g = byKey.get(key)
    if (!g) {
      g = { key, l1: r.l1, l2: r.l2, l3: r.l3, rows: [] }
      byKey.set(key, g)
      out.push(g)
    }
    g.rows.push(r)
  }
  return out
}

/**
 * The FactorTree, rendered once and reused by every S2 module.
 *
 * Every S2 step is doing the same thing to the same object — integrating and
 * filtering the factor tree — so they share this canvas and differ only in the
 * status each row carries. The component owns no data and derives no verdicts:
 * modules pass rows they built from their own slice, which is what keeps an
 * overlay from disagreeing with the thing it is displaying.
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
  const groups = useMemo(() => groupRows(rows), [rows])
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

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {header}
      <table className="mt-3 w-full border-collapse text-[11.5px]">
        <thead>
          <tr className="border-b border-border text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            <th className="px-2 py-1.5 font-medium">Factor · Indicator</th>
            {columns.map((c) => (
              <th key={c} className="px-2 py-1.5 text-right font-medium">{c}</th>
            ))}
            <th className="px-2 py-1.5 font-medium">Status</th>
            {actions && <th className="px-2 py-1.5 font-medium">Action</th>}
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => {
            const isCollapsed = collapsed.has(g.key)
            const span = 2 + columns.length + (actions ? 1 : 0)
            return (
              <Fragment key={g.key}>
                <tr className="bg-muted/30">
                  <td colSpan={span} className="px-2 py-1">
                    <button
                      type="button"
                      onClick={() => toggle(g.key)}
                      className="flex items-center gap-1 text-[10.5px] font-medium text-muted-foreground hover:text-foreground"
                    >
                      {isCollapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      <span>{g.l1 || '—'}</span>
                      {g.l2 && <span className="text-muted-foreground/60">› {g.l2}</span>}
                      {g.l3 && <span className="text-muted-foreground/60">› {g.l3}</span>}
                      <span className="ml-1 text-muted-foreground/50">({g.rows.length})</span>
                    </button>
                  </td>
                </tr>
                {!isCollapsed && g.rows.map((r) => {
                  const blocked = Boolean(r.blockedBy)
                  return (
                    <tr
                      key={r.key}
                      onClick={() => !blocked && onSelect?.(r.key)}
                      className={cn(
                        'border-b border-border/40',
                        blocked ? 'opacity-45' : 'cursor-pointer hover:bg-accent/50',
                        selectedKey === r.key && 'bg-accent',
                      )}
                    >
                      <td className="px-2 py-1">
                        <span className="text-muted-foreground">{r.l4 || r.l3 || '—'}</span>
                        <span className="text-muted-foreground/50"> · </span>
                        <span className="font-medium">{r.indicator}</span>
                      </td>
                      {columns.map((c, i) => (
                        <td key={c} className="px-2 py-1 text-right tabular-nums text-muted-foreground">
                          {r.cells?.[i] ?? ''}
                        </td>
                      ))}
                      <td className="px-2 py-1">
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
                        <td className="px-2 py-1" onClick={(e) => e.stopPropagation()}>
                          {blocked ? null : actions(r)}
                        </td>
                      )}
                    </tr>
                  )
                })}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
