import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../../../api/client'
import type { IndicatorLedger, IndicatorLedgerRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { indicatorKey } from './keys'

/**
 * Every indicator's fate across the six S2 layers, indexed by `indicatorKey`.
 *
 * Fetched rather than derived: the ledger is the backend's own resolution of the
 * layer order, and re-deriving it here is exactly how a surface comes to disagree
 * with what the model was actually fitted on. Call `reload()` after a mutation
 * that changes a verdict.
 */
export function useLedgerIndex(): {
  index: Map<string, IndicatorLedgerRow>
  reload: () => void
} {
  const projectId = useSimStore((s) => s.activeProjectId)
  const [ledger, setLedger] = useState<IndicatorLedger | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    api
      .indicatorLedger(projectId)
      .then((l) => { if (!cancelled) setLedger(l) })
      .catch(() => { if (!cancelled) setLedger(null) })
    return () => { cancelled = true }
  }, [projectId, nonce])

  const index = useMemo(() => {
    const m = new Map<string, IndicatorLedgerRow>()
    for (const r of ledger?.rows ?? []) m.set(indicatorKey(r.l4, r.indicator), r)
    return m
  }, [ledger])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { index, reload }
}

/** The six S2 layers in the order they rule. Mirrors `ledger.LAYERS`. */
const LAYER_ORDER = ['mapping', 'quality', 'signoff', 'statistical', 'selection', 'range']

/**
 * The label of the layer that rejected this indicator BEFORE `layer` — or
 * undefined if no earlier layer did. A module uses this to grey out rows it must
 * not re-litigate: a rejection at any layer is inherited by every later one.
 */
export function blockedBefore(
  row: IndicatorLedgerRow | undefined,
  layer: string,
): string | undefined {
  if (!row) return undefined
  const cutoff = LAYER_ORDER.indexOf(layer)
  if (cutoff < 0) return undefined
  for (const v of row.verdicts) {
    const at = LAYER_ORDER.indexOf(v.layer)
    if (at >= 0 && at < cutoff && v.status === 'rejected') return v.label || v.layer
  }
  return undefined
}
