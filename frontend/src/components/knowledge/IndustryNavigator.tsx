import { useMemo, useState } from 'react'
import { ChevronDown, Globe, Layers, Plus, Search, X } from 'lucide-react'
import { l1Options, l2Options } from '../../lib/industries'
import { packItemCount, type Pack } from '../../lib/knowledge'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'

export type Selection = { type: 'general' } | { type: 'pack'; key: string }

interface Props {
  packs: Pack[]
  selection: Selection
  onSelect: (s: Selection) => void
  onNewPack: (l1: string, l2: string | undefined) => void
}

export function IndustryNavigator({ packs, selection, onSelect, onNewPack }: Props) {
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const [newL1, setNewL1] = useState(() => l1Options()[0]?.code ?? '')
  const [newL2, setNewL2] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return packs
    return packs.filter((p) => p.label.toLowerCase().includes(q) || p.key.toLowerCase().includes(q))
  }, [packs, query])

  const newL2List = useMemo(() => l2Options(newL1), [newL1])

  function create() {
    onNewPack(newL1, newL2 || undefined)
    setAdding(false)
    setNewL2('')
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search industries"
          className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-[13px] outline-none focus:border-primary"
        />
      </div>

      {/* General knowledge — cross-industry, pinned on top */}
      <button
        type="button"
        onClick={() => onSelect({ type: 'general' })}
        className={cn('flex items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
          selection.type === 'general' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40')}
      >
        <Globe className="size-4 shrink-0 text-primary" />
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold">General knowledge</p>
          <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">Cross-industry · all projects</p>
        </div>
      </button>

      <div className="flex items-center justify-between px-0.5">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Industry packs</p>
        <span className="font-mono text-[10px] text-muted-foreground/70">{filtered.length}</span>
      </div>

      <div className="space-y-1.5">
        {filtered.map((p) => {
          const active = selection.type === 'pack' && selection.key === p.key
          const sectionCount = Object.keys(p.sections).length
          return (
            <button
              key={p.key}
              type="button"
              onClick={() => onSelect({ type: 'pack', key: p.key })}
              className={cn('flex w-full items-center gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
                active ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40')}
            >
              <Layers className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{p.label}</p>
                <p className="truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {sectionCount} sections · {packItemCount(p)} items
                </p>
              </div>
            </button>
          )
        })}
        {filtered.length === 0 && (
          <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            {query ? 'No matching packs.' : 'No packs yet.'}
          </p>
        )}
      </div>

      {adding ? (
        <div className="space-y-2 rounded-lg border border-primary/40 bg-primary/5 p-3">
          <div className="flex items-center justify-between">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">New pack</p>
            <button type="button" onClick={() => setAdding(false)} className="text-muted-foreground hover:text-foreground">
              <X className="size-3.5" />
            </button>
          </div>
          <label className="block">
            <select
              value={newL1}
              onChange={(e) => { setNewL1(e.target.value); setNewL2('') }}
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none"
            >
              {l1Options().map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
            </select>
          </label>
          <div className="relative">
            <select
              value={newL2}
              onChange={(e) => setNewL2(e.target.value)}
              className="w-full appearance-none rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none"
            >
              <option value="">(whole L1 — any sub-category)</option>
              {newL2List.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          </div>
          <Button size="sm" className="w-full" onClick={create}><Plus />Create pack</Button>
        </div>
      ) : (
        <Button size="sm" variant="outline" className="w-full" onClick={() => setAdding(true)}>
          <Plus />New pack
        </Button>
      )}
    </div>
  )
}
