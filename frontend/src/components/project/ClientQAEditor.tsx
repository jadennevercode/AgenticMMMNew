import { useMemo } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import type { ClientQA, ClientQARow, ClientQAStatus } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'

const STATUSES: { id: ClientQAStatus; label: string; on: string }[] = [
  { id: 'open', label: '待回', on: 'bg-amber-500 text-white' },
  { id: 'answered', label: '已回', on: 'bg-sky-600 text-white' },
  { id: 'closed', label: '关闭', on: 'bg-emerald-600 text-white' },
]

function rid(): string {
  return `qa-m-${Math.random().toString(36).slice(2, 9)}`
}

/** Structured editor for the S2 client Q&A tracker — data/indicator questions
 * raised during validation, with owner, response and status. */
export function ClientQAEditor() {
  const qa = useSimStore((s) => s.clientQa)
  const updateClientQA = useSimStore((s) => s.updateClientQA)

  const rows = useMemo(() => qa?.rows ?? [], [qa])
  const openCount = useMemo(() => rows.filter((r) => r.status === 'open').length, [rows])

  if (!qa) return null

  function commit(next: ClientQARow[]) {
    void updateClientQA({ rows: next } satisfies ClientQA)
  }
  function patch(id: string, p: Partial<ClientQARow>) {
    commit(rows.map((r) => (r.id === id ? { ...r, ...p } : r)))
  }
  function remove(id: string) {
    commit(rows.filter((r) => r.id !== id))
  }
  function add() {
    commit([...rows, { id: rid(), question: '', owner: '', response: '', status: 'open' }])
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Client Q&amp;A · 数据&amp;指标沟通表</h3>
          <p className="text-[11px] text-muted-foreground">
            数据校验与交叉校验中需与客户确认的问题；跟踪负责人、反馈与状态。
          </p>
        </div>
        {openCount > 0 && <Badge className="bg-amber-500/10 text-amber-700">{openCount} 待回</Badge>}
      </div>

      <div className="max-h-[28rem] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 bg-muted/60">
            <tr className="text-left text-muted-foreground">
              <th className="px-2 py-1.5 font-medium">问题</th>
              <th className="w-28 px-2 py-1.5 font-medium">负责人</th>
              <th className="px-2 py-1.5 font-medium">反馈</th>
              <th className="w-44 px-2 py-1.5 text-center font-medium">状态</th>
              <th className="w-8 px-1 py-1.5" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-border align-top">
                <td className="p-0">
                  <textarea
                    value={r.question}
                    onChange={(e) => patch(r.id, { question: e.target.value })}
                    rows={1}
                    className="w-full resize-none bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  />
                </td>
                <td className="p-0">
                  <input
                    value={r.owner}
                    onChange={(e) => patch(r.id, { owner: e.target.value })}
                    className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  />
                </td>
                <td className="p-0">
                  <textarea
                    value={r.response}
                    onChange={(e) => patch(r.id, { response: e.target.value })}
                    rows={1}
                    placeholder="客户反馈…"
                    className="w-full resize-none bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  />
                </td>
                <td className="px-2 py-1">
                  <div className="inline-flex rounded-md border border-border p-0.5">
                    {STATUSES.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        onClick={() => patch(r.id, { status: s.id })}
                        className={cn('rounded px-1.5 py-0.5 text-[11px]', r.status === s.id ? s.on : 'text-muted-foreground hover:bg-accent')}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </td>
                <td className="px-1 py-1 text-center">
                  <button type="button" onClick={() => remove(r.id)} className="rounded p-1 text-muted-foreground hover:text-destructive">
                    <Trash2 className="size-3" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button size="sm" variant="outline" onClick={add}>
        <Plus />
        Add question
      </Button>
    </Card>
  )
}
