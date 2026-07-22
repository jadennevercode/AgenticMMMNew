import type { ValidationGroup } from '../../../lib/types'

/** Mirrors backend `ledger.signoff_key` — the indicator form of a signoffs key. */
export function signoffKey(l4: string, indicator: string): string {
  return `i:${l4.trim().toLowerCase()}|${indicator.trim().toLowerCase()}`
}

/** This indicator's recorded verdict, '' when never reviewed. */
export function pairVerdict(
  signoffs: Record<string, string>, l4: string, indicator: string,
): 'yes' | 'no' | '' {
  const v = signoffs[signoffKey(l4, indicator)]
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
