import type { ReactNode } from 'react'

/** Visual weight of a row's module status. */
export type FactorCanvasTone = 'ok' | 'warn' | 'bad' | 'muted'

/**
 * One indicator row on the shared FactorTree canvas. Each S2 module builds these
 * from its own slice — the canvas only groups, renders and selects. It never
 * derives status itself, so a module's overlay can never disagree with its data.
 */
export interface FactorCanvasRow {
  /** Unique within the canvas. Use `indicatorKey(l4, indicator)` unless the
   *  module has its own row id (2.1 maps factor-tree rows, which can repeat a key). */
  key: string
  /** Model object (channel type) this row belongs to, when the canvas is
   *  scoped to one channel. Empty/undefined = the collapsed "all channels" view. */
  object?: string
  l1: string
  l2: string
  l3: string
  l4: string
  indicator: string
  tone: FactorCanvasTone
  /** Short status word shown on the row, e.g. "Mapped", "Denied", "Good". */
  statusLabel: string
  /** Compact extra cells, aligned to the canvas's `columns` prop. A cell may be
   *  a rendered control (2.1 puts its Role / Aggregation selects here) so a
   *  per-row decision lives in its own column instead of a catch-all Action one. */
  cells?: ReactNode[]
  /** Set when an EARLIER S2 layer already rejected this indicator — the row
   *  renders greyed and non-interactive. Value is the layer's label. */
  blockedBy?: string
}
