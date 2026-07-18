import { Fragment, useMemo, useState } from 'react'
import { useSimStore } from '../../store/useSimStore'
import type { QualityDisposition, QualityRow, QualityScorecard, QualitySubScore } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'

const DISPOSITIONS: { id: QualityDisposition; label: string; on: string }[] = [
  { id: 'accept', label: 'Accept', on: 'bg-emerald-600 text-white' },
  { id: 'flag', label: 'Flag', on: 'bg-amber-500 text-white' },
  { id: 'drop', label: 'Drop', on: 'bg-destructive text-destructive-foreground' },
]

const VERDICT_STYLE: Record<string, string> = {
  pass: 'text-emerald-600',
  borderline: 'text-amber-600',
  unusable: 'text-destructive',
}

const DIMENSIONS: { key: string; label: string }[] = [
  { key: 'consistency', label: 'Consistency' },
  { key: 'accuracy', label: 'Accuracy' },
  { key: 'completeness', label: 'Completeness' },
  { key: 'granularity', label: 'Granularity' },
]

/** 0 / 0.5 / 1 → a compact colored score chip. */
function ScoreChip({ score }: { score: number }) {
  const tone =
    score >= 1 ? 'bg-emerald-500/15 text-emerald-700' : score > 0 ? 'bg-amber-500/15 text-amber-700' : 'bg-destructive/15 text-destructive'
  return <span className={cn('inline-block min-w-[2rem] rounded px-1 py-0.5 text-center font-mono tabular-nums', tone)}>{score}</span>
}

/** The 10-subcheck breakdown behind a row's four dimension scores. */
function SubcheckDetail({ subs, notes }: { subs: QualitySubScore[]; notes: Record<string, string | undefined> }) {
  return (
    <div className="grid gap-3 bg-muted/30 p-3 md:grid-cols-2">
      {DIMENSIONS.map((dim) => {
        const rows = subs.filter((s) => s.dimension === dim.key)
        if (rows.length === 0) return null
        return (
          <div key={dim.key} className="space-y-1">
            <div className="flex items-baseline justify-between">
              <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{dim.label}</h4>
              {notes[dim.key] ? <span className="text-[10px] italic text-muted-foreground">{notes[dim.key]}</span> : null}
            </div>
            <ul className="space-y-1">
              {rows.map((s) => (
                <li key={s.key} className="flex items-start gap-2 text-[11px]">
                  <ScoreChip score={s.score} />
                  <div className="min-w-0">
                    <span className="font-medium">{s.label}</span>
                    {!s.computed ? (
                      <span className="ml-1 rounded bg-slate-400/15 px-1 text-[9px] uppercase text-slate-500" title="Advisory — needs an external reference to verify; does not gate the score">
                        advisory
                      </span>
                    ) : null}
                    {!s.blocking && s.computed ? (
                      <span className="ml-1 rounded bg-slate-400/15 px-1 text-[9px] uppercase text-slate-500" title="Informational — does not drag the dimension score down">
                        info
                      </span>
                    ) : null}
                    <p className="text-muted-foreground">{s.note}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

/** Structured editor for the S2 data quality scorecard — per-metric human
 * disposition (accept / flag / drop) drives the downstream model-input set.
 * Each row expands to its 2.11 subcheck breakdown (the driver of every score). */
export function QualityScorecardEditor() {
  const card = useSimStore((s) => s.qualityScorecard)
  const updateQualityScorecard = useSimStore((s) => s.updateQualityScorecard)
  const [filter, setFilter] = useState<'all' | 'attention'>('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const rows = useMemo(() => card?.rows ?? [], [card])
  const counts = useMemo(() => {
    const c = { accept: 0, flag: 0, drop: 0 }
    rows.forEach((r) => (c[r.disposition] += 1))
    return c
  }, [rows])

  if (!card) return null

  function commit(next: QualityRow[]) {
    void updateQualityScorecard({ rows: next } satisfies QualityScorecard)
  }
  function setDisposition(id: string, disposition: QualityDisposition) {
    commit(rows.map((r) => (r.id === id ? { ...r, disposition } : r)))
  }
  function setNote(id: string, note: string) {
    commit(rows.map((r) => (r.id === id ? { ...r, note } : r)))
  }
  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const visible = filter === 'attention' ? rows.filter((r) => r.autoVerdict !== 'pass') : rows

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Data Quality Score · 2.11 4-Dimension Validation</h3>
          <p className="text-[11px] text-muted-foreground">
            Each factor × indicator is scored 0 / 0.5 / 1 on consistency, accuracy, completeness and granularity. Total = the product of
            the four dimensions. Expand a row to see the subcheck evidence, then disposition every borderline / unusable metric.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="bg-emerald-600/10 text-emerald-700">Accept {counts.accept}</Badge>
          <Badge className="bg-amber-500/10 text-amber-700">Flag {counts.flag}</Badge>
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

      <div className="max-h-[28rem] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 bg-muted/60">
            <tr className="text-left text-muted-foreground">
              <th className="px-2 py-1.5 font-medium">Indicator</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium" title="Consistency">Cons.</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium" title="Accuracy">Acc.</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium" title="Completeness">Comp.</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium" title="Granularity">Gran.</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium">Total</th>
              <th className="w-40 px-2 py-1.5 text-center font-medium">Disposition</th>
              <th className="px-2 py-1.5 font-medium">Notes</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const isOpen = expanded.has(r.id)
              const notes: Record<string, string | undefined> = {
                consistency: r.consistencyNote,
                accuracy: r.accuracyNote,
                completeness: r.completenessNote,
                granularity: r.granularityNote,
              }
              return (
                <Fragment key={r.id}>
                  <tr className="border-t border-border align-middle">
                    <td className="px-2 py-1">
                      <button
                        type="button"
                        onClick={() => toggle(r.id)}
                        className="mr-1 inline-block w-3 text-muted-foreground transition-transform"
                        title={isOpen ? 'Hide subchecks' : 'Show subchecks'}
                        aria-expanded={isOpen}
                      >
                        {isOpen ? '▾' : '▸'}
                      </button>
                      <span className="font-medium">{r.l4 || r.l3 || r.l1}</span>
                      <span className="text-muted-foreground"> · {r.indicator}</span>
                      <span className={cn('ml-1 font-mono text-[10px] uppercase', VERDICT_STYLE[r.autoVerdict] ?? 'text-muted-foreground')}>
                        {r.autoVerdict}
                      </span>
                    </td>
                    <td className="px-1 py-1 text-center tabular-nums">{r.consistency}</td>
                    <td className="px-1 py-1 text-center tabular-nums">{r.accuracy}</td>
                    <td className="px-1 py-1 text-center tabular-nums">{r.completeness}</td>
                    <td className="px-1 py-1 text-center tabular-nums">{r.granularity}</td>
                    <td className="px-1 py-1 text-center font-semibold tabular-nums">{r.total}</td>
                    <td className="px-2 py-1">
                      <div className="inline-flex rounded-md border border-border p-0.5">
                        {DISPOSITIONS.map((d) => (
                          <button
                            key={d.id}
                            type="button"
                            onClick={() => setDisposition(r.id, d.id)}
                            className={cn('rounded px-1.5 py-0.5 text-[11px]', r.disposition === d.id ? d.on : 'text-muted-foreground hover:bg-accent')}
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
                        placeholder="Disposition rationale / client note…"
                        className="w-full bg-transparent px-1 py-0.5 outline-none focus:bg-primary/5"
                      />
                    </td>
                  </tr>
                  {isOpen && r.subScores && r.subScores.length > 0 ? (
                    <tr className="border-t border-border/50">
                      <td colSpan={8} className="p-0">
                        <SubcheckDetail subs={r.subScores} notes={notes} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        Dropped indicators do not enter master-data assembly or modeling (Model Input). Borderline metrics (Total &lt; 0.5) default to
        Flag — align with the client at the data-validation gate (d-2.2) before finalizing.
      </p>
    </Card>
  )
}
