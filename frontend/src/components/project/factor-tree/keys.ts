/**
 * The indicator key space shared by every S2 layer. Must match the backend's
 * `ledger._norm_pair` exactly — (l4, metric), each trimmed and lower-cased.
 * L4 only: an indicator is identified by its leaf factor and its metric, never
 * by its L1–L3 path.
 */
export function indicatorKey(l4: string, indicator: string): string {
  return `${l4.trim().toLowerCase()}|${indicator.trim().toLowerCase()}`
}

/**
 * The per-Channel-Type key: `object|l4|indicator`. Used to look an indicator's
 * verdict up for one channel, so two channels' rulings on the same indicator do
 * not collide onto one entry. `object` empty → the OBJECT_ANY sentinel `*`.
 */
export function objectKey(object: string, l4: string, indicator: string): string {
  return `${(object || '*').trim().toLowerCase()}|${indicatorKey(l4, indicator)}`
}
