import { useMemo, useState } from 'react'

import type { QualityDisposition, QualityRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { indicatorKey } from '../factor-tree/keys'
import { blockedBefore, useLedgerIndex } from '../factor-tree/useLedgerIndex'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

const DISPOSITIONS: { id: QualityDisposition; label: string; on: string }[] = [
  { id: 'accept', label: 'Accept', on: 'bg-emerald-500/15 text-emerald-600' },
  { id: 'flag', label: 'Flag', on: 'bg-amber-500/15 text-amber-600' },
  { id: 'drop', label: 'Drop', on: 'bg-rose-500/15 text-rose-600' },
]
const DIMENSIONS = [
  { key: 'consistency', label: 'Consistency' },
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'completeness', label: 'Completeness' },
  { key: 'granularity', label: 'Granularity' },
] as const
const TONE: Record<string, FactorCanvasTone> = { pass: 'ok', borderline: 'warn', unusable: 'bad' }

/**
 * 2.2 Data Quality Score on the shared factor tree.
 *
 * The four dimension scores ride on the tree row; the ten subchecks and the AI's
 * per-dimension notes open below for the selected indicator. Indicators an earlier
 * layer already rejected are greyed by the canvas — re-scoring a settled decision
 * would put it back in front of the human as if it were open.
 */
export function QualityCanvas() {
  const card = useSimStore((s) => s.qualityScorecard)
  const update = useSimStore((s) => s.updateQualityScorecard)
  const { index } = useLedgerIndex()
  const [selected, setSelected] = useState('')

  const cardRows = useMemo(() => card?.rows ?? [], [card])

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      cardRows.map((r) => ({
        key: r.id,
        l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
        indicator: r.indicator,
        tone: TONE[r.autoVerdict] ?? 'muted',
        statusLabel: r.autoVerdict || '—',
        cells: [
          r.consistency.toString(), r.accuracy.toString(),
          r.completeness.toString(), r.granularity.toString(),
          r.total.toFixed(2),
        ],
        blockedBy: blockedBefore(index.get(indicatorKey(r.l4, r.indicator)), 'quality'),
      })),
    [cardRows, index],
  )

  const current: QualityRow | undefined = useMemo(
    () => cardRows.find((r) => r.id === selected),
    [cardRows, selected],
  )

  if (!card) return null

  function setDisposition(id: string, disposition: QualityDisposition) {
    void update({ rows: cardRows.map((r) => (r.id === id ? { ...r, disposition } : r)) })
  }

  const header = (
    <header>
      <h3 className="text-sm font-medium">Data Quality Score</h3>
      <p className="text-[11px] text-muted-foreground">
        {cardRows.length} indicators · {cardRows.filter((r) => r.disposition === 'drop').length} dropped
      </p>
    </header>
  )

  return (
    <>
      <FactorTreeCanvas
        rows={rows}
        columns={['Cons.', 'Acc.', 'Comp.', 'Gran.', 'Total']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="Run 2.2 to score the indicators."
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
        <aside className="max-h-64 overflow-auto border-t border-border p-3">
          <p className="mb-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {current.l4 || current.l3} · {current.indicator}
          </p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {DIMENSIONS.map((dim) => (
              <section key={dim.key}>
                <p className="text-[11px] font-medium">{dim.label}</p>
                <p className="text-[11px] text-muted-foreground">
                  {(current[`${dim.key}Note` as keyof QualityRow] as string) || '—'}
                </p>
                <ul className="mt-1 space-y-0.5">
                  {(current.subScores ?? [])
                    .filter((s) => s.dimension === dim.key)
                    .map((s) => (
                      <li key={s.key} className="text-[10.5px] text-muted-foreground">
                        <span className="tabular-nums">{s.score}</span> · {s.label}
                        {!s.computed && <span className="ml-1 text-muted-foreground/60">(advisory)</span>}
                      </li>
                    ))}
                </ul>
              </section>
            ))}
          </div>
        </aside>
      )}
    </>
  )
}
