import { useEffect, useMemo, useState } from 'react'
import { Check, Loader2, RotateCcw, Save, X } from 'lucide-react'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { Button } from '../../ui/button'
import type { OlsRangeDisposition, OlsRangeRow, OlsRangeScorecard } from '../../../lib/types'

/**
 * 2.5d — the factor tree with an accept/reject verdict on every fitted factor.
 *
 * The same shape as the 2.2 and 2.4 reviews, which is the point: 2.5 was the one
 * S2 layer with no per-row human turn, so the only lever over a factor's fate was
 * the gate's all-or-nothing "drop the flagged ones".
 *
 * Two behaviours the UI has to make legible, because both are easy to mistake for
 * bugs:
 *  - saving **re-fits**, so the coefficients change under you. A rejected variable
 *    leaves the model and the rest of the model is re-estimated without it — that
 *    is the honest result, not a glitch.
 *  - the AI's recommendation keeps being recomputed, but a row you have ruled on
 *    keeps *your* verdict. The `overridden` badge is where the two disagree.
 *
 * Draft + dirty guard is mandatory: the state poll replaces this slice every tick
 * and would otherwise clobber in-flight edits.
 */

const num = (v: number | null, d = 2): string => (v === null || v === undefined ? '—' : v.toFixed(d))
const pct = (v: number | null, d = 1): string => (v === null || v === undefined ? '—' : `${v.toFixed(d)}%`)

const STATUS_CHIP: Record<string, string> = {
  inRange: 'bg-emerald-500/15 text-emerald-600',
  review: 'bg-amber-500/15 text-amber-700',
  noBenchmark: 'bg-slate-500/15 text-slate-500',
}
const STATUS_LABEL: Record<string, string> = {
  inRange: 'In range',
  review: 'Out of range',
  noBenchmark: 'No benchmark',
}

function useScorecardDraft() {
  const stored = useSimStore((s) => s.olsScorecard)
  const save = useSimStore((s) => s.updateOlsScorecard)
  const [draft, setDraft] = useState<OlsRangeScorecard | null>(stored)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored && !dirty) setDraft(stored)
  }, [stored, dirty])

  const setRow = (id: string, patch: Partial<OlsRangeRow>) => {
    setDraft((d) =>
      d ? { ...d, rows: d.rows.map((r) => (r.id === id ? { ...r, ...patch } : r)) } : d,
    )
    setDirty(true)
  }

  const commit = async () => {
    if (!draft) return
    setSaving(true)
    try {
      await save(draft)
      setDirty(false)
    } finally {
      setSaving(false)
    }
  }

  const revert = () => {
    setDraft(stored)
    setDirty(false)
  }

  return { draft, dirty, saving, setRow, commit, revert }
}

function VerdictToggle({ row, onChange }: {
  row: OlsRangeRow
  onChange: (d: OlsRangeDisposition) => void
}) {
  const btn = (value: OlsRangeDisposition, label: string, Icon: typeof Check, on: string) => (
    <button
      type="button"
      onClick={() => onChange(value)}
      aria-pressed={row.disposition === value}
      className={cn(
        'inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium transition-colors',
        row.disposition === value ? on : 'text-muted-foreground hover:bg-accent',
      )}
    >
      <Icon className="size-3" />
      {label}
    </button>
  )
  return (
    <div className="inline-flex items-center gap-0.5 rounded-md border border-border p-0.5">
      {btn('accept', 'Accept', Check, 'bg-emerald-500/15 text-emerald-700')}
      {btn('reject', 'Reject', X, 'bg-rose-500/15 text-rose-600')}
    </div>
  )
}

export function OlsFactorTreePanel() {
  const { draft, dirty, saving, setRow, commit, revert } = useScorecardDraft()
  const [onlyDisputed, setOnlyDisputed] = useState(false)

  // Memoised: a fresh `[]` each render would re-run both memos below every time.
  const rows = useMemo(() => draft?.rows ?? [], [draft])
  const stats = useMemo(() => ({
    total: rows.length,
    accepted: rows.filter((r) => r.disposition === 'accept').length,
    rejected: rows.filter((r) => r.disposition === 'reject').length,
    overridden: rows.filter((r) => r.decidedBy === 'human' && r.disposition !== r.autoVerdict).length,
  }), [rows])

  const shown = useMemo(
    () => (onlyDisputed ? rows.filter((r) => r.autoVerdict === 'reject' || r.decidedBy === 'human') : rows),
    [rows, onlyDisputed],
  )

  if (!draft) {
    return (
      <section className="mt-3 rounded-lg border border-border bg-card p-3">
        <p className="text-[11px] text-muted-foreground">
          The OLS has not been fitted yet — run 2.5 to get a verdict per factor.
        </p>
      </section>
    )
  }

  return (
    <section className="mt-3 rounded-lg border border-border bg-card p-3">
      <header className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-[12.5px] font-semibold">Factor verdicts</h4>
          <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
            Accept or reject each fitted factor against its industry ROI / contribution band.
            Saving re-fits: a rejected variable leaves the model and the remaining
            coefficients are re-estimated without it.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {dirty && (
            <Button size="sm" variant="ghost" onClick={revert} disabled={saving}>
              <RotateCcw /> Revert
            </Button>
          )}
          <Button size="sm" onClick={commit} disabled={!dirty || saving}>
            {saving ? <Loader2 className="animate-spin" /> : <Save />}
            {saving ? 'Re-fitting…' : 'Save & refit'}
          </Button>
        </div>
      </header>

      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="text-muted-foreground">
          {stats.total} factor{stats.total === 1 ? '' : 's'} · {stats.accepted} accepted ·{' '}
          {stats.rejected} rejected
        </span>
        {stats.overridden > 0 && (
          <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium text-primary">
            {stats.overridden} overridden
          </span>
        )}
        <button
          type="button"
          onClick={() => setOnlyDisputed((v) => !v)}
          className={cn(
            'ml-auto rounded-md border px-2 py-0.5 font-medium transition-colors',
            onlyDisputed ? 'border-primary/50 bg-accent' : 'border-border text-muted-foreground hover:bg-accent/60',
          )}
        >
          {onlyDisputed ? 'Showing needs-attention' : 'Only needs attention'}
        </button>
      </div>

      <div className="max-h-[26rem] overflow-auto rounded-lg border border-border">
        <table className="w-full min-w-[760px] text-[12px]">
          <thead className="sticky top-0 z-10 bg-muted/80 backdrop-blur">
            <tr className="text-left text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
              <th className="px-2 py-2 font-medium">Factor</th>
              <th className="px-2 py-2 font-medium">Model</th>
              <th className="px-2 py-2 text-right font-medium">ROI</th>
              <th className="px-2 py-2 text-right font-medium">Contribution</th>
              <th className="px-2 py-2 font-medium">Band check</th>
              <th className="px-2 py-2 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => {
              const overridden = r.decidedBy === 'human' && r.disposition !== r.autoVerdict
              return (
                <tr key={r.id} className="border-t border-border/50 align-top hover:bg-accent/30">
                  <td className="px-2 py-1.5">
                    <span className="block font-medium leading-snug">{r.indicator || '—'}</span>
                    <span className="block text-[10px] text-muted-foreground">
                      {[r.l3, r.l4].filter(Boolean).join(' › ')}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-[11px] text-muted-foreground">{r.object}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-[11px]">
                    {num(r.roi)}
                    {r.roiRange && (
                      <span className="block text-[9px] text-muted-foreground">{r.roiRange}</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-[11px]">
                    {pct(r.contribution)}
                    {r.contributionRange && (
                      <span className="block text-[9px] text-muted-foreground">{r.contributionRange}</span>
                    )}
                  </td>
                  <td className="px-2 py-1.5">
                    <span className={cn('inline-flex rounded px-1.5 py-0.5 text-[10.5px] font-medium',
                      STATUS_CHIP[r.status] ?? 'bg-muted text-muted-foreground')}>
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                    {/* The recommendation and why — kept visible even after an
                        override, so the disagreement stays on screen. */}
                    <p className="mt-0.5 max-w-[260px] text-[10px] leading-snug text-muted-foreground">
                      {r.autoReason || r.flagReason}
                    </p>
                  </td>
                  <td className="px-2 py-1.5">
                    <VerdictToggle
                      row={r}
                      onChange={(d) => setRow(r.id, { disposition: d, decidedBy: 'human' })}
                    />
                    {overridden && (
                      <span className="mt-0.5 block text-[9px] text-primary">
                        overrides the recommendation ({r.autoVerdict})
                      </span>
                    )}
                    {r.decidedBy === 'human' && !overridden && (
                      <span className="mt-0.5 block text-[9px] text-muted-foreground">confirmed by you</span>
                    )}
                  </td>
                </tr>
              )
            })}
            {shown.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-[12px] text-muted-foreground">
                  {rows.length === 0
                    ? 'No fitted factors carry a range verdict yet.'
                    : 'Nothing needs attention — every factor matched its recommendation.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}
