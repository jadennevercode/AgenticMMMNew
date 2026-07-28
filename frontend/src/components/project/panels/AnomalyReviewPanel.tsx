import { useEffect, useState } from 'react'
import { Loader2, Save } from 'lucide-react'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { Button } from '../../ui/button'
import type { AnomalyHandling, AnomalyHypothesis, AnomalyReview } from '../../../lib/types'

/**
 * 2.3a — one card per detected anomaly. The AI states a cause and proposes a
 * handling; the human accepts, edits or rejects it.
 *
 * The handling is not advisory. An accepted card reaches the fit directly:
 *   event → a dummy control over the window (the spike is absorbed as business,
 *           not credited to marketing)
 *   cap   → the response is winsorized over the window
 *   raw   → nothing but a caveat carried into the report
 * A pending or rejected card does nothing at all.
 */

const HANDLINGS: { id: AnomalyHandling; label: string; effect: string }[] = [
  { id: 'event', label: 'Structural event', effect: 'Adds a dummy control over the window' },
  { id: 'cap', label: 'Cap the outlier', effect: 'Winsorizes the response over the window' },
  { id: 'raw', label: 'Leave raw', effect: 'Keeps the data; carries a caveat into the report' },
]

/** Local draft over the store's review, guarded against poll churn. */
function useAnomalyDraft() {
  const stored = useSimStore((s) => s.anomalyReview)
  const updateAnomalyReview = useSimStore((s) => s.updateAnomalyReview)
  const [draft, setDraft] = useState<AnomalyReview | null>(stored)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored && !dirty) setDraft(stored)
  }, [stored, dirty])

  function patchRow(id: string, p: Partial<AnomalyHypothesis>) {
    setDraft((d) => (d ? { rows: d.rows.map((r) => (r.id === id ? { ...r, ...p } : r)) } : d))
    setDirty(true)
  }
  async function save() {
    if (!draft) return
    setSaving(true)
    try {
      await updateAnomalyReview(draft)
      setDirty(false)
    } finally {
      setSaving(false)
    }
  }
  return { draft, dirty, saving, patchRow, save }
}

/** yyyymm ↔ the month input's yyyy-mm. */
const toMonthInput = (v: number): string =>
  v > 0 ? `${Math.floor(v / 100)}-${String(v % 100).padStart(2, '0')}` : ''
const fromMonthInput = (v: string): number => {
  const [y, m] = v.split('-').map(Number)
  return y && m ? y * 100 + m : 0
}

function Card({ r, onPatch }: { r: AnomalyHypothesis; onPatch: (p: Partial<AnomalyHypothesis>) => void }) {
  const decided = r.status !== 'pending'
  return (
    <li
      className={cn(
        'rounded-lg border px-3 py-2.5',
        r.status === 'accepted' ? 'border-emerald-500/40 bg-emerald-500/5'
          : r.status === 'rejected' ? 'border-border bg-muted/30 opacity-70'
            : 'border-amber-500/40 bg-amber-500/5',
      )}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex items-baseline gap-1.5">
          <span className="text-[12.5px] font-semibold">{r.channel}</span>
          <span className="text-[11px] text-muted-foreground">{r.year}</span>
          <span className={cn('font-mono text-[11px] font-medium',
            r.growthPct >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
            {r.growthPct >= 0 ? '+' : ''}{r.growthPct}%
          </span>
        </span>
        <span className={cn('rounded px-1.5 py-0.5 text-[9px] font-medium uppercase',
          r.status === 'accepted' ? 'bg-emerald-500/15 text-emerald-600'
            : r.status === 'rejected' ? 'bg-muted text-muted-foreground'
              : 'bg-amber-500/15 text-amber-600')}>
          {r.status}
        </span>
      </header>

      <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">{r.hypothesis}</p>

      <div className="mt-2 flex flex-wrap gap-1">
        {HANDLINGS.map((h) => (
          <button
            key={h.id} type="button" title={h.effect}
            onClick={() => onPatch({ handling: h.id })}
            className={cn(
              'rounded-md border px-2 py-1 text-[11px] transition-colors',
              r.handling === h.id
                ? 'border-primary/50 bg-accent font-medium'
                : 'border-border text-muted-foreground hover:bg-accent/50',
            )}
          >
            {h.label}
            {r.proposed === h.id && (
              <span className="ml-1 text-[9px] text-primary">proposed</span>
            )}
          </button>
        ))}
      </div>
      <p className="mt-1 text-[10.5px] leading-snug text-muted-foreground">
        {HANDLINGS.find((h) => h.id === r.handling)?.effect}
        {r.handling === r.proposed && r.tradeoff ? ` · Trade-off: ${r.tradeoff}` : ''}
      </p>

      {r.handling !== 'raw' && (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-0.5">
            <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">From</span>
            <input
              type="month" value={toMonthInput(r.start)}
              onChange={(e) => onPatch({ start: fromMonthInput(e.target.value) })}
              className="rounded-md border border-border bg-transparent px-1.5 py-0.5 text-[11px] outline-none focus:border-primary/50"
            />
          </label>
          <label className="flex flex-col gap-0.5">
            <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">To</span>
            <input
              type="month" value={toMonthInput(r.end)}
              onChange={(e) => onPatch({ end: fromMonthInput(e.target.value) })}
              className="rounded-md border border-border bg-transparent px-1.5 py-0.5 text-[11px] outline-none focus:border-primary/50"
            />
          </label>
          <span className="pb-1 text-[10px] text-muted-foreground">
            Narrow the window once the client confirms the dates.
          </span>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Button
          size="sm" variant={r.status === 'accepted' ? 'default' : 'outline'}
          onClick={() => onPatch({ status: r.status === 'accepted' ? 'pending' : 'accepted' })}
        >
          {r.status === 'accepted' ? 'Accepted' : 'Accept'}
        </Button>
        <Button
          size="sm" variant="ghost"
          onClick={() => onPatch({ status: r.status === 'rejected' ? 'pending' : 'rejected' })}
        >
          {r.status === 'rejected' ? 'Rejected' : 'Reject'}
        </Button>
        <input
          value={r.note} placeholder="Note (e.g. what the client said)"
          onChange={(e) => onPatch({ note: e.target.value })}
          className="min-w-0 flex-1 rounded-md border border-border bg-transparent px-2 py-1 text-[11px] outline-none focus:border-primary/50"
        />
      </div>
      {decided && r.status === 'rejected' && (
        <p className="mt-1 text-[10px] text-muted-foreground">
          Rejected — this anomaly has no effect on the model.
        </p>
      )}
    </li>
  )
}

export function AnomalyReviewPanel() {
  const { draft, dirty, saving, patchRow, save } = useAnomalyDraft()

  if (!draft) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-border px-3 py-2 text-[11.5px] text-muted-foreground">
        The anomaly cards have not been drafted yet — run the previous step first.
      </p>
    )
  }
  if (draft.rows.length === 0) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-border px-3 py-2 text-[11.5px] text-muted-foreground">
        No year-on-year move crossed the ±40% threshold — there is nothing to explain.
      </p>
    )
  }

  const accepted = draft.rows.filter((r) => r.status === 'accepted')
  const pending = draft.rows.filter((r) => r.status === 'pending').length

  return (
    <section className="mt-3 rounded-lg border border-border bg-card p-3">
      <header className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-[12.5px] font-semibold">Anomaly hypotheses</h4>
          <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
            The AI proposes a cause and a handling for each anomaly; your ruling reaches the
            model. {accepted.length} accepted{pending > 0 ? `, ${pending} still pending` : ''}.
          </p>
        </div>
        <Button size="sm" onClick={() => void save()} disabled={!dirty || saving} className="shrink-0">
          {saving ? <Loader2 className="animate-spin" /> : <Save />}
          {saving ? 'Saving…' : 'Save rulings'}
        </Button>
      </header>
      <ul className="space-y-2">
        {draft.rows.map((r) => (
          <Card key={r.id} r={r} onPatch={(p) => patchRow(r.id, p)} />
        ))}
      </ul>
    </section>
  )
}
