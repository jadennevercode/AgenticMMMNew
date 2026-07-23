import { useMemo, useState } from 'react'

import type { QualityDisposition, QualityRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { ChannelTypeSelect } from '../factor-tree/ChannelTypeSelect'
import { indicatorKey } from '../factor-tree/keys'
import { ledgerOnlyRows } from '../factor-tree/ledgerOnlyRows'
import { useLedgerIndex } from '../factor-tree/useLedgerIndex'
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
  const channel = useSimStore((s) => s.s2ChannelFilter)
  const setChannel = useSimStore((s) => s.setS2ChannelFilter)
  const { index, blockedBeforeFor, reload } = useLedgerIndex()
  const [selected, setSelected] = useState('')
  const [applyAll, setApplyAll] = useState(false)

  const cardRows = useMemo(() => card?.rows ?? [], [card])

  // Data-derived channel options — the distinct model objects the scorecard rows
  // were screened under. Never hardcoded.
  const channels = useMemo(
    () => [...new Set(cardRows.map((r) => r.object).filter(Boolean) as string[])].sort(),
    [cardRows],
  )

  // A channel is selected → that channel's own rows. "All channels" → each
  // indicator once (dedup by key, first occurrence) to reproduce the collapsed view.
  const visibleCardRows = useMemo(() => {
    if (channel) return cardRows.filter((r) => (r.object ?? '') === channel)
    const seen = new Set<string>()
    return cardRows.filter((r) => {
      const k = indicatorKey(r.l4, r.indicator)
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
  }, [cardRows, channel])

  const rows: FactorCanvasRow[] = useMemo(() => {
    const scored = visibleCardRows.map((r) => ({
      key: r.id,
      object: r.object,
      l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
      indicator: r.indicator,
      tone: TONE[r.autoVerdict] ?? 'muted',
      statusLabel: r.autoVerdict || '—',
      cells: [
        r.consistency.toString(), r.accuracy.toString(),
        r.completeness.toString(), r.granularity.toString(),
        r.total.toFixed(2),
      ],
      blockedBy: blockedBeforeFor(r.l4, r.indicator, 'quality', channel || undefined),
    }))
    const scoredKeys = new Set(visibleCardRows.map((r) => indicatorKey(r.l4, r.indicator)))
    return [...scored, ...ledgerOnlyRows(index, scoredKeys, 'quality')]
  }, [visibleCardRows, index, blockedBeforeFor, channel])

  const current: QualityRow | undefined = useMemo(
    () => cardRows.find((r) => r.id === selected),
    [cardRows, selected],
  )

  if (!card) return null

  function setDisposition(id: string, disposition: QualityDisposition) {
    // A drop here is a quality-layer verdict every later layer inherits — reload
    // the ledger so the "Denied @ …" badges downstream reflect it immediately.
    // Default: this channel's row only. "Apply to all channels": every object's
    // row for the same indicator.
    const target = cardRows.find((r) => r.id === id)
    const applies = (r: QualityRow) =>
      r.id === id ||
      (applyAll && target != null && indicatorKey(r.l4, r.indicator) === indicatorKey(target.l4, target.indicator))
    void update({ rows: cardRows.map((r) => (applies(r) ? { ...r, disposition } : r)) }).then(reload)
  }

  const header = (
    <header className="flex items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">Data Quality Score</h3>
        <p className="text-[11px] text-muted-foreground">
          {visibleCardRows.length} indicators · {visibleCardRows.filter((r) => r.disposition === 'drop').length} dropped
          {channel && <> · <span className="text-primary">{channel}</span></>}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <ChannelTypeSelect options={channels} value={channel} onChange={setChannel} />
        {channel && (
          <label className="flex cursor-pointer items-center gap-1 text-[11px] text-muted-foreground">
            <input type="checkbox" checked={applyAll} onChange={(e) => setApplyAll(e.target.checked)} />
            apply to all channels
          </label>
        )}
      </div>
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
