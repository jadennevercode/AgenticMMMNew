import type { ValidationGroup } from '../../../lib/types'

/**
 * The model object a verdict applies to. Mirrors backend `ledger.OBJECT_ANY`:
 * a sign-off from the 2.3 deck denies the indicator for every channel unless a
 * caller explicitly names one.
 */
export const OBJECT_ANY = '*'

/**
 * Mirrors backend `ledger.signoff_key` — `i:<object>:<norm_l4>|<norm_metric>`.
 *
 * The `object` segment is not optional. The backend gained it when screening went
 * per-channel; this helper did not, so every verdict the UI wrote was read back
 * under a key that no longer existed — the Y/N buttons stayed blank however many
 * times you pressed them, and the chart's group verdict never moved off
 * "Pending". Any change to the backend key shape has to land here in the same
 * commit.
 */
export function signoffKey(l4: string, indicator: string, object: string = OBJECT_ANY): string {
  return `i:${object || OBJECT_ANY}:${l4.trim().toLowerCase()}|${indicator.trim().toLowerCase()}`
}

/** This indicator's recorded verdict, '' when never reviewed. */
export function pairVerdict(
  signoffs: Record<string, string>, l4: string, indicator: string, object: string = OBJECT_ANY,
): 'yes' | 'no' | '' {
  // A verdict recorded for every channel (OBJECT_ANY) governs a concrete channel
  // too, so an object-scoped read falls back to the global key.
  const v = signoffs[signoffKey(l4, indicator, object)]
    ?? (object === OBJECT_ANY ? undefined : signoffs[signoffKey(l4, indicator)])
  return v === 'yes' || v === 'no' ? v : ''
}

/** How a whole chart stands, from its own indicators. */
export function groupVerdict(
  group: ValidationGroup, signoffs: Record<string, string>,
): 'accepted' | 'denied' | 'mixed' | 'pending' {
  const pairs = group.pairs ?? []
  if (!pairs.length) return 'pending'
  let yes = 0, no = 0
  for (const p of pairs) {
    const v = pairVerdict(signoffs, p.l4, p.indicator)
    if (v === 'yes') yes += 1
    else if (v === 'no') no += 1
  }
  if (yes === pairs.length) return 'accepted'
  if (no === pairs.length) return 'denied'
  if (yes || no) return 'mixed'
  return 'pending'
}
