import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { Button } from '../../ui/button'
import type { DataRequestProposal } from '../../../lib/types'

/**
 * 1.5 data-request review — the AI reads the interview minutes and proposes
 * per-L4 indicator add/removes the data request does not yet reflect; the
 * human accepts or rejects each one. Mirrors `AnomalyReviewPanel` (2.3a): a
 * list of cards, one API call per ruling, then a refresh.
 *
 * Unlike the anomaly review there is no dedicated `ProjectState` slice for
 * this — the backend keeps the pending set only on the re-rendered
 * `a-data-request` artifact, as the "Interview-driven changes (proposed)"
 * sheet (`_datareq_review_sheet` in business.py). That sheet is appended only
 * while proposals are pending, so reading it off `s.artifacts` (already
 * polled/refreshed like every other artifact) is both the simplest and the
 * always-current source — no separate fetch to keep in sync.
 */

const REVIEW_SHEET_NAME = 'Interview-driven changes (proposed)'

function useDataRequestProposals(): DataRequestProposal[] {
  const inst = useSimStore((s) => s.artifacts.find((a) => a.id === 'a-data-request'))
  const body = inst?.body
  if (!body || !('sheets' in body)) return []
  const sheet = body.sheets.find((sh) => sh.name === REVIEW_SHEET_NAME)
  if (!sheet) return []
  const iOp = sheet.columns.indexOf('Op')
  const iL3 = sheet.columns.indexOf('L3')
  const iL4 = sheet.columns.indexOf('L4')
  const iInd = sheet.columns.indexOf('Indicator')
  const iRat = sheet.columns.indexOf('Rationale')
  const iQuote = sheet.columns.indexOf('Quote')
  return sheet.rows
    .filter((r) => r[iOp] === 'add' || r[iOp] === 'remove')
    .map((r) => ({
      op: r[iOp] as 'add' | 'remove',
      l3: r[iL3] ?? '',
      l4: r[iL4] ?? '',
      indicator: r[iInd] ?? '',
      rationale: r[iRat] ?? '',
      quote: r[iQuote] ?? '',
    }))
}

/** op+l3+l4+indicator uniquely identifies a proposal — same key space the
 *  backend uses (`_dr_key` + op:indicator), so it doubles as the React key
 *  and the in-flight guard. */
function keyOf(p: DataRequestProposal): string {
  return `${p.op}|${p.l3}|${p.l4}|${p.indicator}`
}

function Card({
  p,
  busy,
  onAct,
}: {
  p: DataRequestProposal
  busy: boolean
  onAct: (accept: boolean) => void
}) {
  return (
    <li className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2.5">
      <header className="flex flex-wrap items-baseline gap-1.5">
        <span
          className={cn(
            'rounded px-1.5 py-0.5 text-[9px] font-medium uppercase',
            p.op === 'add' ? 'bg-emerald-500/15 text-emerald-600' : 'bg-rose-500/15 text-rose-600',
          )}
        >
          {p.op}
        </span>
        <span className="text-[12.5px] font-semibold">{p.l3}</span>
        <span className="text-[11px] text-muted-foreground">{p.l4}</span>
        <span className="font-mono text-[11px] font-medium">{p.indicator}</span>
      </header>

      <p className="mt-1 text-[11.5px] leading-snug text-muted-foreground">{p.rationale}</p>
      {p.quote && (
        <p className="mt-1 border-l-2 border-border pl-2 text-[11px] italic leading-snug text-muted-foreground/80">
          “{p.quote}”
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Button size="sm" disabled={busy} onClick={() => onAct(true)}>
          {busy ? <Loader2 className="animate-spin" /> : null}
          Accept
        </Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => onAct(false)}>
          Reject
        </Button>
      </div>
    </li>
  )
}

export function DataRequestReviewPanel() {
  const proposals = useDataRequestProposals()
  const projectId = useSimStore((s) => s.activeProjectId)
  const refresh = useSimStore((s) => s.refresh)
  const reportError = useSimStore((s) => s.reportError)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  if (proposals.length === 0) return null

  async function act(p: DataRequestProposal, accept: boolean) {
    if (!projectId) return
    const k = keyOf(p)
    setBusyKey(k)
    try {
      await api.reviewDataRequest(projectId, { op: p.op, l3: p.l3, l4: p.l4, indicator: p.indicator, accept })
      await refresh()
    } catch (e) {
      reportError(e)
    } finally {
      setBusyKey((cur) => (cur === k ? null : cur))
    }
  }

  return (
    <section className="mt-3 rounded-lg border border-border bg-card p-3">
      <header className="mb-2">
        <h4 className="text-[12.5px] font-semibold">Interview-driven changes</h4>
        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
          The AI found {proposals.length} field {proposals.length === 1 ? 'change' : 'changes'} in the interview
          minutes that the data request does not yet reflect. Accept applies it; reject dismisses it for good.
        </p>
      </header>
      <ul className="space-y-2">
        {proposals.map((p) => (
          <Card key={keyOf(p)} p={p} busy={busyKey === keyOf(p)} onAct={(accept) => void act(p, accept)} />
        ))}
      </ul>
    </section>
  )
}
