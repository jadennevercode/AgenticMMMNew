import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../../../api/client'
import type { FactorMap, QualityDisposition, QualityRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { indicatorKey } from '../factor-tree/keys'
import { ledgerOnlyRows } from '../factor-tree/ledgerOnlyRows'
import { useLedgerIndex } from '../factor-tree/useLedgerIndex'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

/** The 2.1 mapping status, as this canvas filters on it. */
type StatusFilter = 'all' | 'matched' | 'unmatched'
const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'matched', label: 'Matched' },
  { id: 'unmatched', label: 'Unmatched' },
]

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
  const projectId = useSimStore((s) => s.activeProjectId)
  const reportError = useSimStore((s) => s.reportError)
  const { index, blockedBeforeFor, reload } = useLedgerIndex()
  const [selected, setSelected] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [matched, setMatched] = useState<Set<string> | null>(null)

  // Quality rows are grouped straight from the modeling table, so they carry no
  // mapping status of their own — it is joined from the 2.1 factor map by
  // `indicatorKey(l4, indicator)`. Fetched once here, like the 2.1 canvas does:
  // it is derived from published indicators, not a polled ProjectState slice.
  const loadMap = useCallback(() => {
    if (!projectId) return
    api.getFactorMap(projectId)
      .then((m: FactorMap) => setMatched(new Set(
        m.rows.filter((r) => r.status === 'mapped')
          .map((r) => indicatorKey(r.l4, r.metric || r.indicator)),
      )))
      .catch((e) => { setMatched(null); reportError(e) })
  }, [projectId, reportError])

  useEffect(loadMap, [loadMap])

  const isMatched = useCallback(
    (l4: string, indicator: string) => matched?.has(indicatorKey(l4, indicator)) ?? false,
    [matched],
  )

  // One national total model — every scorecard row belongs to the single TOTAL
  // object, so there is no channel dimension to filter or dedup on.
  const cardRows = useMemo(() => card?.rows ?? [], [card])
  const visibleCardRows = useMemo(() => {
    if (status === 'all' || matched === null) return cardRows
    const want = status === 'matched'
    return cardRows.filter((r) => isMatched(r.l4, r.indicator) === want)
  }, [cardRows, status, matched, isMatched])

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
      blockedBy: blockedBeforeFor(r.l4, r.indicator, 'quality', undefined),
    }))
    const scoredKeys = new Set(cardRows.map((r) => indicatorKey(r.l4, r.indicator)))
    // Ledger-only rows (rejected before 2.2 ever scored them) obey the same
    // filter — otherwise the filter would visibly leak rows it excluded.
    const extra = ledgerOnlyRows(index, scoredKeys, 'quality').filter((r) =>
      status === 'all' || matched === null || isMatched(r.l4, r.indicator) === (status === 'matched'))
    return [...scored, ...extra]
  }, [visibleCardRows, cardRows, index, blockedBeforeFor, status, matched, isMatched])

  const current: QualityRow | undefined = useMemo(
    () => cardRows.find((r) => r.id === selected),
    [cardRows, selected],
  )

  if (!card) return null

  function setDisposition(id: string, disposition: QualityDisposition) {
    // A drop here is a quality-layer verdict every later layer inherits — reload
    // the ledger so the "Denied @ …" badges downstream reflect it immediately.
    void update({ rows: cardRows.map((r) => (r.id === id ? { ...r, disposition } : r)) }).then(reload)
  }

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">Data Quality Score</h3>
        <p className="text-[11px] text-muted-foreground">
          {status === 'all'
            ? `${cardRows.length} indicators`
            : `${visibleCardRows.length} shown of ${cardRows.length} indicators`}
          {' · '}
          {visibleCardRows.filter((r) => r.disposition === 'drop').length} dropped
        </p>
      </div>
      <div
        role="group"
        aria-label="Filter by Data Processing status"
        className="inline-flex rounded-md border border-border p-0.5"
      >
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            aria-pressed={status === f.id}
            disabled={f.id !== 'all' && matched === null}
            onClick={() => setStatus(f.id)}
            className={cn(
              'rounded px-2 py-0.5 text-[11px] transition-colors disabled:opacity-40',
              status === f.id ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/60',
            )}
          >
            {f.label}
          </button>
        ))}
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
