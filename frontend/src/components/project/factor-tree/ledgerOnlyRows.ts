import type { IndicatorLedgerRow } from '../../../lib/types'
import { blockedBefore } from './useLedgerIndex'
import type { FactorCanvasRow } from './types'

/**
 * The greyed tail of a scorecard canvas: ledger indicators an earlier layer
 * already rejected before this module's scorecard builder ran, so they never
 * got a scorecard row at all. Without these the tree silently shrinks between
 * steps instead of visibly narrowing — the central promise of the shared
 * canvas. Callers union this with their own scored rows; scorecard rows stay
 * first-class, these are only the ones with nothing else to show.
 */
export function ledgerOnlyRows(
  index: Map<string, IndicatorLedgerRow>,
  scoredKeys: Set<string>,
  layer: string,
): FactorCanvasRow[] {
  const out: FactorCanvasRow[] = []
  for (const [key, row] of index) {
    if (scoredKeys.has(key)) continue
    out.push({
      key: `ledger:${key}`,
      l1: row.l1, l2: row.l2, l3: row.l3, l4: row.l4,
      indicator: row.indicator,
      tone: 'muted',
      statusLabel: row.rejectedAt ? `Denied @ ${row.rejectedAt}` : '—',
      cells: [],
      blockedBy: blockedBefore(row, layer),
    })
  }
  return out
}
