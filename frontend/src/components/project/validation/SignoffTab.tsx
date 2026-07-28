import { useMemo, useState } from 'react'

import type { ValidationGroup } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import { useLedgerIndex } from '../factor-tree/useLedgerIndex'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'
import { pairVerdict } from './signoff'

/**
 * 2.3 Client sign-off, on the same horizontal `L1 · L2 · L3 · L4 · Indicator`
 * table every other S2 module uses.
 *
 * **Accepted is the default, and that is a display convention, not a write.**
 * An indicator that survived 2.1 and 2.2 is already headed for the model — the
 * backend's sign-off layer only rejects on an explicit `"no"`. So the table
 * renders an unset row as `Accepted · default` and writes nothing until someone
 * actually flips one. Stamping `"yes"` across every row on load would produce
 * hundreds of state writes and, worse, destroy the only signal distinguishing
 * "a human looked at this" from "nobody objected".
 *
 * Indicators an earlier layer already rejected are greyed by the canvas and are
 * not offered for sign-off: a settled decision must not be put back in front of
 * the reviewer as if it were open.
 */
export function SignoffTab({ groups }: { groups: ValidationGroup[] }) {
  const signoffs = useSimStore((s) => s.signoffs)
  const setSignoff = useSimStore((s) => s.setSignoff)
  const { blockedBeforeFor, reload } = useLedgerIndex()
  const [selected, setSelected] = useState('')
  const [bulkL3, setBulkL3] = useState('')

  const flat = useMemo(
    () =>
      groups.flatMap((g) =>
        (g.pairs ?? []).map((p) => ({
          ...p, l1: g.l1, l2: g.l2, l3: g.l3,
          // An (l4, indicator) pair can repeat under different parents, so the row
          // key carries the whole path. It is never parsed back apart — see the
          // `actions` lookup below.
          key: `${g.l1}›${g.l2}›${g.l3}|${p.l4}|${p.indicator}`,
        }))),
    [groups],
  )
  const byKey = useMemo(() => new Map(flat.map((p) => [p.key, p])), [flat])

  function set(l4: string, indicator: string, verdict: 'yes' | 'no' | '') {
    // A denial is a sign-off-layer verdict every later layer inherits — reload the
    // ledger so the "Denied @ …" badges at 2.4 / 2.5 reflect it immediately.
    void setSignoff({ l4, indicator }, verdict).then(reload)
  }

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      flat.map((p) => {
        const v = pairVerdict(signoffs, p.l4, p.indicator)
        const blockedBy = blockedBeforeFor(p.l4, p.indicator, 'signoff', undefined)
        const tone: FactorCanvasTone = v === 'no' ? 'bad' : 'ok'
        return {
          key: p.key,
          l1: p.l1, l2: p.l2, l3: p.l3, l4: p.l4,
          indicator: p.indicator,
          tone,
          statusLabel: v === 'no' ? 'Rejected' : v === 'yes' ? 'Accepted' : 'Accepted · default',
          blockedBy,
        }
      }),
    [flat, signoffs, blockedBeforeFor],
  )

  const rejected = flat.filter((p) => pairVerdict(signoffs, p.l4, p.indicator) === 'no').length
  const reviewed = flat.filter((p) => pairVerdict(signoffs, p.l4, p.indicator) !== '').length

  if (!groups.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        No factors to sign off — run task 2.3 first.
      </div>
    )
  }

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">Client sign-off</h3>
        <p className="text-[11px] text-muted-foreground">
          {flat.length} indicators · {rejected} rejected · {reviewed} explicitly reviewed.
          Everything that passed the earlier steps is accepted unless you reject it.
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <select
          aria-label="Factor to apply a bulk verdict to"
          value={bulkL3}
          onChange={(e) => setBulkL3(e.target.value)}
          className="max-w-44 rounded border border-border bg-background px-1.5 py-0.5 text-[11px]
                     transition-colors hover:border-foreground/40 focus:border-foreground/60
                     focus:outline-none focus:ring-1 focus:ring-foreground/20"
        >
          <option value="">Whole factor…</option>
          {groups.map((g) => (
            <option key={`${g.l1}›${g.l2}›${g.l3}`} value={g.l3}>{g.l3}</option>
          ))}
        </select>
        <button
          type="button"
          disabled={!bulkL3}
          onClick={() => bulkL3 && void setSignoff({ l3: bulkL3 }, 'yes').then(reload)}
          className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground
                     transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
        >
          Accept all
        </button>
        <button
          type="button"
          disabled={!bulkL3}
          onClick={() => bulkL3 && void setSignoff({ l3: bulkL3 }, 'no').then(reload)}
          className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground
                     transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
        >
          Reject all
        </button>
      </div>
    </header>
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <FactorTreeCanvas
        rows={rows}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="No indicators to sign off — re-run 2.3 to build the per-indicator list."
        actions={(r) => {
          // Look the pair up rather than parsing it back out of the key: the key
          // has to carry the whole L1›L2›L3 path to stay unique, and an L4 or an
          // indicator name may itself contain a '|'.
          const row = byKey.get(r.key)
          if (!row) return null
          const { l4, indicator } = row
          const v = pairVerdict(signoffs, l4, indicator)
          return (
            <div className="inline-flex rounded-md border border-border p-0.5">
              <button
                type="button"
                aria-pressed={v !== 'no'}
                onClick={() => set(l4, indicator, v === 'yes' ? '' : 'yes')}
                className={cn(
                  'rounded px-2 py-0.5 text-[11px] transition-colors',
                  v !== 'no' ? 'bg-emerald-500/15 text-emerald-600' : 'text-muted-foreground hover:bg-accent',
                )}
              >
                Accept
              </button>
              <button
                type="button"
                aria-pressed={v === 'no'}
                onClick={() => set(l4, indicator, v === 'no' ? '' : 'no')}
                className={cn(
                  'rounded px-2 py-0.5 text-[11px] transition-colors',
                  v === 'no' ? 'bg-rose-500/15 text-rose-600' : 'text-muted-foreground hover:bg-accent',
                )}
              >
                Reject
              </button>
            </div>
          )
        }}
      />
    </div>
  )
}
