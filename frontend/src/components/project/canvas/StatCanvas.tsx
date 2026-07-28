import { useMemo, useState } from 'react'

import type { StatDisposition, StatScoreRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { indicatorKey } from '../factor-tree/keys'
import { ledgerOnlyRows } from '../factor-tree/ledgerOnlyRows'
import { useLedgerIndex } from '../factor-tree/useLedgerIndex'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

const DISPOSITIONS: { id: StatDisposition; label: string; on: string }[] = [
  { id: 'include', label: 'Include', on: 'bg-emerald-500/15 text-emerald-600' },
  { id: 'review', label: 'Review', on: 'bg-amber-500/15 text-amber-600' },
  { id: 'drop', label: 'Drop', on: 'bg-rose-500/15 text-rose-600' },
]
const TONE: Record<string, FactorCanvasTone> = {
  Good: 'ok',
  Acceptable: 'warn',
  unconsiderable: 'bad',
}

/**
 * 2.4 Statistical Score on the shared factor tree.
 *
 * Three tests per indicator, each 0 / 0.5 / 1, multiplied into the total — so a
 * zero anywhere is the whole story, and the selected row spells out which test
 * produced it.
 */
export function StatCanvas() {
  const card = useSimStore((s) => s.statScorecard)
  const update = useSimStore((s) => s.updateStatScorecard)
  const { index, blockedBeforeFor, reload } = useLedgerIndex()
  const [selected, setSelected] = useState('')

  // One national total model — every scorecard row is the single TOTAL object.
  const cardRows = useMemo(() => card?.rows ?? [], [card])
  const visibleCardRows = cardRows

  const rows: FactorCanvasRow[] = useMemo(() => {
    const scored = visibleCardRows.map((r) => ({
      key: r.id,
      object: r.object,
      l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
      indicator: r.indicator,
      tone: TONE[r.autoVerdict] ?? 'muted',
      statusLabel: r.autoVerdict === 'unconsiderable' ? 'Unconsiderable' : r.autoVerdict || '—',
      cells: [
        `${r.cv.toFixed(2)} (${r.cvScore})`,
        `${r.pearson >= 0 ? '+' : ''}${r.pearson.toFixed(2)} (${r.pearsonScore})`,
        `${r.vif.toFixed(1)} (${r.vifScore})`,
        r.total.toFixed(2),
      ],
      blockedBy: blockedBeforeFor(r.l4, r.indicator, 'statistical', undefined),
    }))
    const scoredKeys = new Set(visibleCardRows.map((r) => indicatorKey(r.l4, r.indicator)))
    return [...scored, ...ledgerOnlyRows(index, scoredKeys, 'statistical')]
  }, [visibleCardRows, index, blockedBeforeFor])

  const current: StatScoreRow | undefined = useMemo(
    () => cardRows.find((r) => r.id === selected),
    [cardRows, selected],
  )

  if (!card) return null

  function setDisposition(id: string, disposition: StatDisposition) {
    // A drop here is a statistical-layer verdict the selection step inherits.
    void update({ rows: cardRows.map((r) => (r.id === id ? { ...r, disposition } : r)) }).then(reload)
  }

  const zeroed = visibleCardRows.filter((r) => r.total === 0).length
  const header = (
    <header className="flex items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">Statistical Score</h3>
        <p className="text-[11px] text-muted-foreground">
          {visibleCardRows.length} scored · {zeroed} failed a test · Total = CV × Pearson × VIF
        </p>
      </div>
    </header>
  )

  return (
    <>
      <FactorTreeCanvas
        rows={rows}
        columns={['CV', 'Pearson', 'VIF', 'Total']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="Run 2.4 to score the indicators."
        actions={(r) => {
          const row = cardRows.find((x) => x.id === r.key)
          if (!row) return null
          return (
            <div className="inline-flex rounded-md border border-border p-0.5">
              {DISPOSITIONS.map((d) => (
                <button key={d.id} type="button" onClick={() => setDisposition(row.id, d.id)}
                  className={cn('rounded px-1.5 py-0.5 text-[11px]',
                    row.disposition === d.id ? d.on : 'text-muted-foreground hover:bg-accent')}>
                  {d.label}
                </button>
              ))}
            </div>
          )
        }}
      />
      {current && (
        <aside className="max-h-56 overflow-auto border-t border-border p-3">
          <p className="mb-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {current.l4 || current.l3} · {current.indicator}
          </p>
          <dl className="grid grid-cols-3 gap-3 text-[11px]">
            <div>
              <dt className="text-muted-foreground">Volatility · CV</dt>
              <dd className="tabular-nums">{current.cv.toFixed(3)} → band {current.cvScore}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Correlation · r</dt>
              <dd className="tabular-nums">{current.pearson.toFixed(3)} → band {current.pearsonScore}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Collinearity · VIF</dt>
              <dd className="tabular-nums">{current.vif.toFixed(2)} → band {current.vifScore}</dd>
            </div>
          </dl>
          {current.note && <p className="mt-2 text-[11px] text-muted-foreground">{current.note}</p>}
        </aside>
      )}
    </>
  )
}
