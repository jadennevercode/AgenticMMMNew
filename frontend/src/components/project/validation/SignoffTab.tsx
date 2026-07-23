// frontend/src/components/project/validation/SignoffTab.tsx
import type { ValidationGroup } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { groupVerdict, pairVerdict } from './signoff'

const VERDICT_LABEL: Record<'accepted' | 'denied' | 'mixed' | 'pending', string> = {
  accepted: 'Accepted', denied: 'Denied', mixed: 'Mixed', pending: 'Pending',
}

export function SignoffTab({ groups }: { groups: ValidationGroup[] }) {
  const signoffs = useSimStore((s) => s.signoffs)
  const setSignoff = useSimStore((s) => s.setSignoff)

  if (!groups.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        No factors to sign off — run task 2.3 first.
      </div>
    )
  }
  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
      {groups.map((g) => {
        const verdict = groupVerdict(g, signoffs)
        return (
          <section key={g.l3} className="rounded-xl border border-border bg-card p-4">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{g.l1} › {g.l2}</div>
                <h3 className="truncate text-sm font-semibold" title={g.l3}>{g.l3}</h3>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <span className={cn('rounded px-2 py-0.5 text-[11px] font-medium',
                  verdict === 'accepted' && 'bg-emerald-500/15 text-emerald-600',
                  verdict === 'denied' && 'bg-rose-500/15 text-rose-600',
                  verdict === 'mixed' && 'bg-amber-500/15 text-amber-700',
                  verdict === 'pending' && 'bg-muted text-muted-foreground')}>
                  {VERDICT_LABEL[verdict]}
                </span>
                <button type="button" onClick={() => void setSignoff({ l3: g.l3 }, 'yes')}
                  className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted">Accept all</button>
                <button type="button" onClick={() => void setSignoff({ l3: g.l3 }, 'no')}
                  className="rounded-md border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-muted">Deny all</button>
              </div>
            </div>
            <div className="divide-y divide-border/60 rounded-lg border border-border">
              {(g.pairs ?? []).map((pair) => {
                const v = pairVerdict(signoffs, pair.l4, pair.indicator)
                return (
                  <div key={`${pair.l4}|${pair.indicator}`} className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs">
                    <span className="min-w-0 truncate" title={`${pair.l4} · ${pair.indicator}`}>
                      <span className="text-muted-foreground">{pair.l4}</span> · {pair.indicator}
                    </span>
                    <div className="flex shrink-0 items-center gap-1">
                      {(['yes', 'no'] as const).map((val) => (
                        <button key={val} type="button"
                          onClick={() => void setSignoff({ l4: pair.l4, indicator: pair.indicator }, v === val ? '' : val)}
                          className={cn('rounded px-2 py-0.5 text-[11px] font-medium',
                            v === val ? (val === 'yes' ? 'bg-emerald-500/15 text-emerald-600' : 'bg-rose-500/15 text-rose-600')
                              : 'border border-border text-muted-foreground hover:bg-muted')}>
                          {val === 'yes' ? 'Y' : 'N'}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
              {!(g.pairs ?? []).length && (
                <p className="px-3 py-2 text-xs text-muted-foreground">This factor predates per-indicator sign-off — re-run 2.3.</p>
              )}
            </div>
          </section>
        )
      })}
    </div>
  )
}
