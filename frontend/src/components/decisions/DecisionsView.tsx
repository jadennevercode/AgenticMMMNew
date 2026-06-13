import { useSimStore } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { DecisionCard } from './DecisionCard'

/** Full-page inbox of every decision (open then resolved) */
export default function DecisionsView() {
  const decisions = useSimStore((s) => s.decisions)
  const withDecision = TASKS.filter((t) => t.decision)
  const open = withDecision.filter((t) => decisions[t.decision!.id]?.status === 'open')
  const resolved = withDecision.filter((t) => decisions[t.decision!.id]?.status === 'resolved')

  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      <div className="mb-5 flex items-end justify-between">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Waiting on you</p>
          <h2 className="text-2xl font-semibold tracking-tight">Decisions</h2>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{open.length} open · {resolved.length} decided</span>
      </div>

      {open.length === 0 && (
        <div className="rounded-xl border border-dashed border-border px-6 py-10 text-center">
          <p className="text-sm">Nothing needs you right now.</p>
          <p className="mt-1 text-xs text-muted-foreground">
            The project keeps moving on its own — you’ll be called when a call is yours to make.
          </p>
        </div>
      )}

      <div className="space-y-5">
        {open.map((t) => (
          <DecisionCard key={t.id} decision={t.decision!} runtime={decisions[t.decision!.id]} taskId={t.id} />
        ))}
        {resolved.length > 0 && (
          <p className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Already decided</p>
        )}
        {resolved.map((t) => (
          <DecisionCard key={t.id} decision={t.decision!} runtime={decisions[t.decision!.id]} taskId={t.id} />
        ))}
      </div>
    </div>
  )
}
