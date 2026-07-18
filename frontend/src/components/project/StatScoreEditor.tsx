import { Fragment, useMemo, useState } from 'react'
import { useSimStore } from '../../store/useSimStore'
import type { StatDisposition, StatScoreRow, StatScorecard } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'

const DISPOSITIONS: { id: StatDisposition; label: string; on: string }[] = [
  { id: 'include', label: 'Include', on: 'bg-emerald-600 text-white' },
  { id: 'review', label: 'Review', on: 'bg-amber-500 text-white' },
  { id: 'drop', label: 'Drop', on: 'bg-destructive text-destructive-foreground' },
]

const VERDICT_STYLE: Record<string, string> = {
  Good: 'text-emerald-600',
  Acceptable: 'text-amber-600',
  unconsiderable: 'text-destructive',
}
const VERDICT_LABEL: Record<string, string> = {
  Good: 'Good',
  Acceptable: 'Acceptable',
  unconsiderable: 'Unconsiderable',
}

/** The 2.33 rule legend — three tests, each banded 0 / 0.5 / 1 / 2. */
const RULES: { test: string; metric: string; bands: string[] }[] = [
  {
    test: 'Volatility · CV',
    metric: 'Scale series to [0,1], then variance / mean',
    bands: ['0 · CV ≤ 0.05', '0.5 · 0.05–0.1', '1 · 0.1–0.2', '2 · CV ≥ 0.2'],
  },
  {
    test: 'Correlation · Pearson r',
    metric: '|r| between the indicator and the KPI (univariate)',
    bands: ['0 · |r| < 0.1', '0.5 · 0.1–0.3', '1 · 0.3–0.5', '2 · |r| ≥ 0.5'],
  },
  {
    test: 'Collinearity · VIF',
    metric: 'Variance inflation vs the other indicators',
    bands: ['0 · VIF = 1', '0.5 · 1–5', '1 · VIF ≥ 5', '2 · VIF ≥ 10'],
  },
]

/** Color a 0 / 0.5 / 1 / 2 band score — red → amber → blue → green. */
function scoreClass(score: number): string {
  if (score >= 2) return 'bg-emerald-600/15 text-emerald-700'
  if (score >= 1) return 'bg-sky-600/15 text-sky-700'
  if (score >= 0.5) return 'bg-amber-500/15 text-amber-700'
  return 'bg-destructive/15 text-destructive'
}

function ScoreChip({ raw, score }: { raw: string; score: number }) {
  return (
    <span className={cn('inline-flex min-w-[3.2rem] items-center justify-center gap-1 rounded px-1.5 py-0.5 tabular-nums', scoreClass(score))}>
      <span className="text-[11px]">{raw}</span>
      <span className="font-mono text-[9px] opacity-70">{score}</span>
    </span>
  )
}

/** Structured editor for the S2 (2.4) statistical score — per-indicator CV /
 * Pearson / VIF band scores with a human include / review / drop decision that
 * drives which indicators reach the OLS regression test (2.5). */
export function StatScoreEditor() {
  const card = useSimStore((s) => s.statScorecard)
  const updateStatScorecard = useSimStore((s) => s.updateStatScorecard)
  const [filter, setFilter] = useState<'all' | 'attention'>('all')
  const [rulesOpen, setRulesOpen] = useState(false)

  const rows = useMemo(() => card?.rows ?? [], [card])
  const counts = useMemo(() => {
    const c = { include: 0, review: 0, drop: 0 }
    rows.forEach((r) => (c[r.disposition] += 1))
    return c
  }, [rows])

  if (!card) return null

  function commit(next: StatScoreRow[]) {
    void updateStatScorecard({ rows: next } satisfies StatScorecard)
  }
  function setDisposition(id: string, disposition: StatDisposition) {
    commit(rows.map((r) => (r.id === id ? { ...r, disposition } : r)))
  }
  function setNote(id: string, note: string) {
    commit(rows.map((r) => (r.id === id ? { ...r, note } : r)))
  }

  const visible = filter === 'attention' ? rows.filter((r) => r.autoVerdict !== 'Good') : rows

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Statistical Score · 2.33 CV / Pearson / VIF</h3>
          <p className="text-[11px] text-muted-foreground">
            Every FactorTree indicator is scored on volatility (CV), correlation with the KPI (Pearson) and collinearity (VIF), each
            0 / 0.5 / 1 / 2. Total = the sum — Good ≥ 3, Acceptable 1.5–3, Unconsiderable &lt; 1.5. Disposition each indicator to admit
            it into the OLS regression test.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="bg-emerald-600/10 text-emerald-700">Include {counts.include}</Badge>
          <Badge className="bg-amber-500/10 text-amber-700">Review {counts.review}</Badge>
          <Badge className="bg-destructive/10 text-destructive">Drop {counts.drop}</Badge>
          <div className="inline-flex rounded-md border border-border p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setFilter('all')}
              className={cn('rounded px-2 py-1', filter === 'all' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}
            >
              All
            </button>
            <button
              type="button"
              onClick={() => setFilter('attention')}
              className={cn('rounded px-2 py-1', filter === 'attention' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}
            >
              Needs review
            </button>
          </div>
        </div>
      </div>

      {/* Rule legend (2.33 Sheet1) — collapsed by default. */}
      <div className="rounded-lg border border-border">
        <button
          type="button"
          onClick={() => setRulesOpen((v) => !v)}
          className="flex w-full items-center gap-1.5 px-3 py-2 text-left text-[12px] font-medium"
          aria-expanded={rulesOpen}
        >
          <span className="w-3 text-muted-foreground">{rulesOpen ? '▾' : '▸'}</span>
          Scoring rules · CV / Pearson / VIF bands
        </button>
        {rulesOpen && (
          <div className="grid gap-2 border-t border-border p-3 sm:grid-cols-3">
            {RULES.map((rule) => (
              <div key={rule.test} className="space-y-1">
                <p className="text-[12px] font-semibold">{rule.test}</p>
                <p className="text-[10.5px] leading-snug text-muted-foreground">{rule.metric}</p>
                <ul className="space-y-0.5">
                  {rule.bands.map((b) => (
                    <li key={b} className="font-mono text-[10px] text-muted-foreground">
                      {b}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="max-h-[30rem] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 z-10 bg-muted/60">
            <tr className="text-left text-muted-foreground">
              <th className="px-2 py-1.5 font-medium">Indicator</th>
              <th className="w-24 px-1 py-1.5 text-center font-medium" title="Volatility (CV)">CV</th>
              <th className="w-24 px-1 py-1.5 text-center font-medium" title="Pearson r vs KPI">Pearson</th>
              <th className="w-24 px-1 py-1.5 text-center font-medium" title="Variance inflation factor">VIF</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium">Total</th>
              <th className="w-44 px-2 py-1.5 text-center font-medium">Disposition</th>
              <th className="px-2 py-1.5 font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r, i) => {
              const prev = visible[i - 1]
              const groupChanged = !prev || prev.l1 !== r.l1 || prev.l2 !== r.l2 || prev.l3 !== r.l3
              return (
                <Fragment key={r.id}>
                  {groupChanged && (
                    <tr className="bg-muted/30">
                      <td colSpan={7} className="px-2 py-1 text-[10.5px] font-medium text-muted-foreground">
                        <span>{r.l1 || '—'}</span>
                        {r.l2 && <span className="text-muted-foreground/60"> › {r.l2}</span>}
                        {r.l3 && <span className="text-muted-foreground/60"> › {r.l3}</span>}
                      </td>
                    </tr>
                  )}
                  <tr className="border-t border-border align-middle">
                    <td className="px-2 py-1">
                      <span className="font-medium">{r.l4 || r.l3 || r.l1}</span>
                      <span className="text-muted-foreground"> · {r.indicator}</span>
                      <span className={cn('ml-1.5 font-mono text-[10px] uppercase', VERDICT_STYLE[r.autoVerdict] ?? 'text-muted-foreground')}>
                        {VERDICT_LABEL[r.autoVerdict] ?? r.autoVerdict}
                      </span>
                    </td>
                    <td className="px-1 py-1 text-center">
                      <ScoreChip raw={r.cv.toFixed(2)} score={r.cvScore} />
                    </td>
                    <td className="px-1 py-1 text-center">
                      <ScoreChip raw={(r.pearson >= 0 ? '+' : '') + r.pearson.toFixed(2)} score={r.pearsonScore} />
                    </td>
                    <td className="px-1 py-1 text-center">
                      <ScoreChip raw={r.vif >= 1000 ? '≥1e3' : r.vif.toFixed(1)} score={r.vifScore} />
                    </td>
                    <td className="px-1 py-1 text-center font-semibold tabular-nums">{r.total}</td>
                    <td className="px-2 py-1">
                      <div className="inline-flex rounded-md border border-border p-0.5">
                        {DISPOSITIONS.map((d) => (
                          <button
                            key={d.id}
                            type="button"
                            onClick={() => setDisposition(r.id, d.id)}
                            className={cn(
                              'rounded px-1.5 py-0.5 text-[11px]',
                              r.disposition === d.id ? d.on : 'text-muted-foreground hover:bg-accent',
                            )}
                          >
                            {d.label}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={r.note}
                        onChange={(e) => setNote(r.id, e.target.value)}
                        placeholder="Add a note…"
                        className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-[11px] outline-none hover:border-border focus:border-primary"
                      />
                    </td>
                  </tr>
                </Fragment>
              )
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={7} className="px-2 py-6 text-center text-[12px] text-muted-foreground">
                  No indicators scored yet — run the Statistical Score step first.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}
