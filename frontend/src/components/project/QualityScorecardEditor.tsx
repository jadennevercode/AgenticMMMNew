import { useMemo, useState } from 'react'
import { useSimStore } from '../../store/useSimStore'
import type { QualityDisposition, QualityRow, QualityScorecard } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'

const DISPOSITIONS: { id: QualityDisposition; label: string; on: string }[] = [
  { id: 'accept', label: '采纳', on: 'bg-emerald-600 text-white' },
  { id: 'flag', label: '待确认', on: 'bg-amber-500 text-white' },
  { id: 'drop', label: '剔除', on: 'bg-destructive text-destructive-foreground' },
]

const VERDICT_STYLE: Record<string, string> = {
  pass: 'text-emerald-600',
  borderline: 'text-amber-600',
  unusable: 'text-destructive',
}

/** Structured editor for the S2 data quality scorecard — per-metric human
 * disposition (accept / flag / drop) drives the downstream model-input set. */
export function QualityScorecardEditor() {
  const card = useSimStore((s) => s.qualityScorecard)
  const updateQualityScorecard = useSimStore((s) => s.updateQualityScorecard)
  const [filter, setFilter] = useState<'all' | 'attention'>('all')

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

  const visible = filter === 'attention' ? rows.filter((r) => r.autoVerdict !== 'pass') : rows

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Data Validation · 4-Dim Quality Scorecard</h3>
          <p className="text-[11px] text-muted-foreground">
            每个因子×指标按一致性/准确性/完整性/颗粒度打分；对临界与不可用项做人工处置。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="bg-emerald-600/10 text-emerald-700">采纳 {counts.accept}</Badge>
          <Badge className="bg-amber-500/10 text-amber-700">待确认 {counts.flag}</Badge>
          <Badge className="bg-destructive/10 text-destructive">剔除 {counts.drop}</Badge>
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
              需处置
            </button>
          </div>
        </div>
      </div>

      <div className="max-h-[28rem] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 bg-muted/60">
            <tr className="text-left text-muted-foreground">
              <th className="px-2 py-1.5 font-medium">L4 · 指标</th>
              <th className="w-10 px-1 py-1.5 text-center font-medium" title="一致性">一致</th>
              <th className="w-10 px-1 py-1.5 text-center font-medium" title="准确性">准确</th>
              <th className="w-10 px-1 py-1.5 text-center font-medium" title="完整性">完整</th>
              <th className="w-10 px-1 py-1.5 text-center font-medium" title="颗粒度">颗粒</th>
              <th className="w-12 px-1 py-1.5 text-center font-medium">总分</th>
              <th className="w-40 px-2 py-1.5 text-center font-medium">处置</th>
              <th className="px-2 py-1.5 font-medium">备注</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.id} className="border-t border-border align-middle">
                <td className="px-2 py-1">
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
                    placeholder="处置理由 / 客户说明…"
                    className="w-full bg-transparent px-1 py-0.5 outline-none focus:bg-primary/5"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-muted-foreground">
        剔除的指标不进入后续宽表集成与建模（Model Input）。临界项（borderline）默认「待确认」，建议在数据校验闸口（d-2.11）与客户对齐后再定。
      </p>
    </Card>
  )
}
