import { useEffect, useState } from 'react'
import { BookMarked, Database, Plus, Table2 } from 'lucide-react'
import type { DataAssetStatus } from '../../lib/types'
import { useSimStore } from '../../store/useSimStore'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'
import { AssetDetail } from './AssetDetail'
import { TargetSchemaPanel } from './TargetSchemaPanel'
import { IndicatorCatalogPanel } from './IndicatorCatalogPanel'

type EngineView = 'assets' | 'schema' | 'indicators'

const DOT: Record<DataAssetStatus, string> = {
  raw: 'bg-muted-foreground/40',
  reviewed: 'bg-primary',
  spec: 'bg-primary',
  cleaned: 'bg-amber-500',
  published: 'bg-emerald-500',
}

export default function DataEngineView() {
  const assets = useSimStore((s) => s.dataAssets)
  const selectedId = useSimStore((s) => s.selectedDataAssetId)
  const { loadDataAssets, loadFiles, createDataAsset, selectDataAsset } = useSimStore.getState()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [view, setView] = useState<EngineView>('assets')

  useEffect(() => {
    void loadDataAssets()
    void loadFiles()
  }, [loadDataAssets, loadFiles])

  const selected = assets.find((a) => a.id === selectedId) ?? null

  async function create() {
    const trimmed = name.trim()
    if (!trimmed) return
    const id = await createDataAsset(trimmed)
    if (id) selectDataAsset(id)
    setName('')
    setCreating(false)
  }

  return (
    <div className="flex h-[calc(100vh-52px)]">
      {/* ── asset list ── */}
      <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Database className="size-4 text-primary" />
            <h1 className="text-sm font-semibold">Data Engine</h1>
          </div>
          <Button size="icon" variant="ghost" onClick={() => setCreating((v) => !v)} aria-label="New asset">
            <Plus className="size-4" />
          </Button>
        </div>

        <div className="flex gap-1 border-b border-border p-2">
          <button type="button" onClick={() => setView('schema')}
            className={cn('flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors',
              view === 'schema' ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-accent')}>
            <Table2 className="size-3.5" />Schema
          </button>
          <button type="button" onClick={() => setView('indicators')}
            className={cn('flex flex-1 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors',
              view === 'indicators' ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-accent')}>
            <BookMarked className="size-3.5" />Indicators
          </button>
        </div>

        {creating && (
          <div className="space-y-2 border-b border-border p-3">
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void create() }}
              placeholder="Asset name, e.g. Channel Sales"
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-[12px] outline-none focus:border-primary/60"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={() => void create()} disabled={!name.trim()}>Create</Button>
              <Button size="sm" variant="ghost" onClick={() => { setCreating(false); setName('') }}>Cancel</Button>
            </div>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto p-2">
          {assets.length === 0 ? (
            <p className="px-2 py-6 text-center text-[12px] text-muted-foreground">
              No data assets yet. Click + to register one and turn the client's raw data into a reusable asset.
            </p>
          ) : (
            <ul className="space-y-1">
              {assets.map((a) => (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => { selectDataAsset(a.id); setView('assets') }}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12px] transition-colors',
                      a.id === selectedId && view === 'assets' ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                    )}
                  >
                    <span className={cn('size-2 shrink-0 rounded-full', DOT[a.status])} />
                    <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
                    {a.latestVersion > 0 && <span className="font-mono text-[10px] text-emerald-600">v{a.latestVersion}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* ── detail ── */}
      <main className="min-w-0 flex-1">
        {view === 'schema' ? (
          <TargetSchemaPanel />
        ) : view === 'indicators' ? (
          <IndicatorCatalogPanel onOpenAsset={(id) => { selectDataAsset(id); setView('assets') }} />
        ) : selected ? (
          <AssetDetail key={selected.id} asset={selected} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground">
            <Database className="size-10 opacity-30" />
            <div>
              <p className="text-sm font-medium text-foreground">Data Engine</p>
              <p className="mt-1 max-w-md text-[12px]">
                Register raw data → Review (completeness / granularity / volatility / consistency) →
                AI drafts the dbt transform → you refine it → publish as a data asset the workflow can consume.
              </p>
            </div>
            <Button onClick={() => setCreating(true)}><Plus className="size-4" />Register data asset</Button>
          </div>
        )}
      </main>
    </div>
  )
}
