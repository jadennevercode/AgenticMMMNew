import { useMemo, useState } from 'react'
import { Check, Plus, Sparkles, Trash2, UploadCloud, X } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import type { FactorRow, FactorStatus, FactorTree } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'

const STATUS_STYLE: Record<FactorStatus, string> = {
  baseline: 'text-muted-foreground',
  proposed: 'text-primary',
  accepted: 'text-emerald-600',
  rejected: 'text-muted-foreground line-through opacity-60',
}

function rid(): string {
  return `ft-m-${Math.random().toString(36).slice(2, 9)}`
}

export function FactorTreeEditor() {
  const factorTree = useSimStore((s) => s.factorTree)
  const updateFactorTree = useSimStore((s) => s.updateFactorTree)
  const profile = useSimStore((s) => s.profile)
  const [filter, setFilter] = useState<'all' | 'proposed'>('all')

  const rows = useMemo(() => factorTree?.rows ?? [], [factorTree])
  const proposedCount = useMemo(() => rows.filter((r) => r.status === 'proposed').length, [rows])
  // Default dimension for new rows: the model-scope dimension names from the project profile.
  const defaultDimension = useMemo(
    () => (profile?.modelScope.dimensions ?? []).map((d) => d.name.trim()).filter(Boolean).join(', '),
    [profile],
  )

  function commit(next: FactorRow[]) {
    void updateFactorTree({ rows: next } satisfies FactorTree)
  }
  function setStatus(id: string, status: FactorStatus) {
    commit(rows.map((r) => (r.id === id ? { ...r, status } : r)))
  }
  function patch(id: string, p: Partial<FactorRow>) {
    commit(rows.map((r) => (r.id === id ? { ...r, ...p } : r)))
  }
  function remove(id: string) {
    commit(rows.filter((r) => r.id !== id))
  }
  function add() {
    commit([...rows, { id: rid(), l1: '', l2: '', l3: '', l4: '', indicator: '', dimension: defaultDimension, source: 'manual', status: 'accepted', rationale: '', evidence: '' }])
  }
  function acceptAll() {
    commit(rows.map((r) => (r.status === 'proposed' ? { ...r, status: 'accepted' } : r)))
  }

  if (!factorTree) return null
  const visible = filter === 'proposed' ? rows.filter((r) => r.status === 'proposed') : rows
  const cols: { key: keyof FactorRow; label: string; w: string }[] = [
    { key: 'l1', label: 'L1', w: 'w-28' }, { key: 'l2', label: 'L2', w: 'w-28' },
    { key: 'l3', label: 'L3', w: 'w-32' }, { key: 'l4', label: 'L4', w: 'w-32' },
    { key: 'indicator', label: 'Indicator', w: '' },
    { key: 'dimension', label: 'Dimension', w: 'w-44' },
  ]

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Factor Tree · L1–L4 + Indicator + Dimension</h3>
          <p className="text-[11px] text-muted-foreground">
            Baseline from the industry template; accept or reject each AI recommendation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {proposedCount > 0 && <Badge>{proposedCount} AI proposed</Badge>}
          <div className="inline-flex rounded-md border border-border p-0.5 text-xs">
            <button type="button" onClick={() => setFilter('all')} className={cn('rounded px-2 py-1', filter === 'all' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}>All</button>
            <button type="button" onClick={() => setFilter('proposed')} className={cn('rounded px-2 py-1', filter === 'proposed' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground')}>AI only</button>
          </div>
          {proposedCount > 0 && <Button size="sm" variant="outline" onClick={acceptAll}><Check />Accept all</Button>}
        </div>
      </div>

      <div className="max-h-[28rem] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 bg-muted/60">
            <tr className="text-left text-muted-foreground">
              {cols.map((c) => <th key={c.key} className="px-2 py-1.5 font-medium">{c.label}</th>)}
              <th className="w-20 px-2 py-1.5 font-medium">Source</th>
              <th className="w-24 px-2 py-1.5 text-center font-medium">Confirm</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.id} className="border-t border-border align-top">
                {cols.map((c) => (
                  <td key={c.key} className={cn('p-0', c.w)}>
                    <input
                      value={r[c.key] as string}
                      onChange={(e) => patch(r.id, { [c.key]: e.target.value } as Partial<FactorRow>)}
                      className={cn('w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5', STATUS_STYLE[r.status])}
                      title={r.source === 'ai' ? r.rationale : undefined}
                    />
                  </td>
                ))}
                <td className="px-2 py-1">
                  <span className={cn('inline-flex items-center gap-1 font-mono text-[10px] uppercase', r.source === 'ai' ? 'text-primary' : r.source === 'upload' ? 'text-foreground' : 'text-muted-foreground')}>
                    {r.source === 'ai' && <Sparkles className="size-2.5" />}
                    {r.source === 'upload' && <UploadCloud className="size-2.5" />}
                    {r.source}
                  </span>
                </td>
                <td className="px-2 py-1">
                  {r.status === 'proposed' ? (
                    <div className="flex items-center justify-center gap-1">
                      <button type="button" onClick={() => setStatus(r.id, 'accepted')} className="rounded p-1 text-emerald-600 hover:bg-emerald-500/10" title="Accept"><Check className="size-3.5" /></button>
                      <button type="button" onClick={() => setStatus(r.id, 'rejected')} className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive" title="Reject"><X className="size-3.5" /></button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-center gap-1">
                      <span className={cn('font-mono text-[10px] uppercase', STATUS_STYLE[r.status])}>{r.status}</span>
                      <button type="button" onClick={() => remove(r.id)} className="rounded p-1 text-muted-foreground hover:text-destructive"><Trash2 className="size-3" /></button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Button size="sm" variant="outline" onClick={add}><Plus />Add factor</Button>
    </Card>
  )
}
