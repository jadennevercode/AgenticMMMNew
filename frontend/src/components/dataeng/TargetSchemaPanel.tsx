import { useEffect, useState } from 'react'
import {
  ArrowDown, ArrowUp, Loader2, Plus, Save, Sparkles, Table2, Trash2, X,
} from 'lucide-react'
import type { TargetColumn, TargetColumnKind } from '../../lib/types'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'

const KINDS: TargetColumnKind[] = ['dimension', 'time', 'factor', 'metric', 'value']
const KIND_STYLE: Record<TargetColumnKind, string> = {
  dimension: 'bg-sky-500/10 text-sky-700',
  time: 'bg-violet-500/10 text-violet-700',
  factor: 'bg-amber-500/10 text-amber-700',
  metric: 'bg-emerald-500/10 text-emerald-700',
  value: 'bg-rose-500/10 text-rose-700',
}

const NEW_COLUMN: TargetColumn = {
  name: '', label: '', definition: '', kind: 'dimension', required: false, standardValues: [],
}

export function TargetSchemaPanel() {
  const pid = useSimStore((s) => s.activeProjectId)
  const [cols, setCols] = useState<TargetColumn[] | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [collecting, setCollecting] = useState<string | null>(null)

  useEffect(() => {
    if (!pid) return
    void api.getTargetSchema(pid).then((c) => { setCols(c); setDirty(false) })
  }, [pid])

  const mutate = (next: TargetColumn[]) => { setCols(next); setDirty(true) }
  const patch = (i: number, p: Partial<TargetColumn>) =>
    mutate(cols!.map((c, idx) => (idx === i ? { ...c, ...p } : c)))
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (!cols || j < 0 || j >= cols.length) return
    const next = [...cols]
    ;[next[i], next[j]] = [next[j], next[i]]
    mutate(next)
  }

  async function save() {
    if (!pid || !cols) return
    setSaving(true)
    try {
      const cleaned = cols.filter((c) => c.name.trim())
      await api.putTargetSchema(pid, cleaned)
      setCols(cleaned)
      setDirty(false)
    } finally { setSaving(false) }
  }

  async function collect(i: number) {
    if (!pid || !cols) return
    const name = cols[i].name
    setCollecting(name)
    try {
      const got = await api.collectSchemaValues(pid, name)
      const merged = [...cols[i].standardValues]
      for (const v of got.values) if (!merged.includes(v)) merged.push(v)
      patch(i, { standardValues: merged })
    } finally { setCollecting(null) }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold"><Table2 className="size-4 text-primary" />Target schema</h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            The shape every published mart must emit. Standard values drive enum mappings and the values-in-allowed-set check.
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => cols && mutate([...cols, { ...NEW_COLUMN }])}>
            <Plus className="size-3.5" />Add column
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={!dirty || saving}>
            {saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}Save schema
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5">
        {!cols ? (
          <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><Loader2 className="size-4 animate-spin" />Loading…</div>
        ) : (
          <Card className="overflow-hidden p-0">
            <table className="w-full border-collapse text-[12px]">
              <thead className="bg-muted/60 text-left text-muted-foreground">
                <tr>
                  <th className="w-8 px-2 py-2" />
                  <th className="px-2 py-2 font-medium">Column</th>
                  <th className="px-2 py-2 font-medium">Kind</th>
                  <th className="px-2 py-2 font-medium">Definition</th>
                  <th className="px-2 py-2 font-medium">Standard values</th>
                  <th className="px-2 py-2 text-center font-medium">Required</th>
                  <th className="w-8 px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {cols.map((c, i) => (
                  <tr key={i} className="border-t border-border align-top">
                    <td className="px-1 py-2">
                      <div className="flex flex-col">
                        <button type="button" onClick={() => move(i, -1)} className="text-muted-foreground hover:text-foreground disabled:opacity-30" disabled={i === 0}><ArrowUp className="size-3" /></button>
                        <button type="button" onClick={() => move(i, 1)} className="text-muted-foreground hover:text-foreground disabled:opacity-30" disabled={i === cols.length - 1}><ArrowDown className="size-3" /></button>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <input
                        value={c.name}
                        onChange={(e) => patch(i, { name: e.target.value })}
                        placeholder="column_name"
                        className="w-full rounded border border-transparent bg-transparent px-1.5 py-0.5 font-mono font-medium outline-none hover:border-border focus:border-primary/60"
                      />
                      <input
                        value={c.label}
                        onChange={(e) => patch(i, { label: e.target.value })}
                        placeholder="Label"
                        className="mt-0.5 w-full rounded border border-transparent bg-transparent px-1.5 py-0.5 text-[11px] text-muted-foreground outline-none hover:border-border focus:border-primary/60"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <select
                        value={c.kind}
                        onChange={(e) => patch(i, { kind: e.target.value as TargetColumnKind })}
                        className={cn('rounded px-1.5 py-0.5 text-[11px] font-medium outline-none', KIND_STYLE[c.kind])}
                      >
                        {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      <input
                        value={c.definition}
                        onChange={(e) => patch(i, { definition: e.target.value })}
                        className="w-full rounded border border-transparent bg-transparent px-1.5 py-1 outline-none hover:border-border focus:border-primary/60"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <ValueChips
                        values={c.standardValues}
                        onChange={(vals) => patch(i, { standardValues: vals })}
                        onCollect={() => void collect(i)}
                        collecting={collecting === c.name}
                        canCollect={!!c.name.trim()}
                      />
                    </td>
                    <td className="px-2 py-2 text-center">
                      <input type="checkbox" checked={c.required} onChange={(e) => patch(i, { required: e.target.checked })} />
                    </td>
                    <td className="px-2 py-2">
                      <button type="button" onClick={() => mutate(cols.filter((_, idx) => idx !== i))} className="text-muted-foreground hover:text-rose-600" aria-label="Delete column">
                        <Trash2 className="size-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}

function ValueChips({ values, onChange, onCollect, collecting, canCollect }: {
  values: string[]
  onChange: (v: string[]) => void
  onCollect: () => void
  collecting: boolean
  canCollect: boolean
}) {
  const [draft, setDraft] = useState('')
  function add() {
    const v = draft.trim()
    if (v && !values.includes(v)) onChange([...values, v])
    setDraft('')
  }
  return (
    <div className="flex max-w-72 flex-wrap items-center gap-1">
      {values.map((v) => (
        <span key={v} className="inline-flex items-center gap-0.5 rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
          {v}
          <button type="button" onClick={() => onChange(values.filter((x) => x !== v))} className="text-muted-foreground hover:text-rose-600"><X className="size-2.5" /></button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        onBlur={add}
        placeholder="+ value"
        className="w-16 rounded border border-transparent bg-transparent px-1 py-0.5 text-[10px] outline-none placeholder:text-muted-foreground/60 hover:border-border focus:border-primary/60"
      />
      <button
        type="button"
        onClick={onCollect}
        disabled={collecting || !canCollect}
        title="Collect distinct values from this project's data"
        className="inline-flex items-center gap-0.5 rounded-full border border-dashed border-border px-1.5 py-0.5 text-[10px] text-muted-foreground hover:border-primary/50 hover:text-primary disabled:opacity-40"
      >
        {collecting ? <Loader2 className="size-2.5 animate-spin" /> : <Sparkles className="size-2.5" />}from data
      </button>
    </div>
  )
}
