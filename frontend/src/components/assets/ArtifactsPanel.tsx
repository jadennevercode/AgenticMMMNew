import { useState } from 'react'
import { ArrowDown, ArrowUp, ChevronLeft, FileText } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { ARTIFACTS, ARTIFACT_MAP } from '../../lib/artifacts-data'
import { PROPOSALS, ASSISTANT_SCRIPT, ASSISTANT_FALLBACK } from '../../lib/collab-data'
import { STAGES, STAGE_ORDER } from '../../lib/profiles'
import { confidenceWording } from '../../lib/ui-language'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { AgentChip, AssetStateBadge, MiniMarkdown } from '../ui/primitives'
import { cn } from '../../lib/cn'
import type { ArtifactInstance, DiffLine, ProposalBlueprint } from '../../lib/types'

export function AssetList({ onPick, selectedId }: { onPick: (id: string) => void; selectedId?: string | null }) {
  const artifacts = useSimStore((s) => s.artifacts)
  const produced = new Map(artifacts.map((a) => [a.id, a]))
  return (
    <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
      {STAGE_ORDER.map((sid) => {
        const items = ARTIFACTS.filter((a) => a.stage === sid)
        if (!items.length) return null
        return (
          <div key={sid}>
            <p className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {STAGES[sid].name}
            </p>
            <div className="space-y-0.5">
              {items.map((a) => {
                const inst = produced.get(a.id)
                return (
                  <button
                    key={a.id}
                    type="button"
                    disabled={!inst}
                    onClick={() => inst && onPick(a.id)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] transition-colors',
                      !inst
                        ? 'cursor-default opacity-40'
                        : selectedId === a.id
                          ? 'bg-accent'
                          : 'hover:bg-accent',
                    )}
                  >
                    <FileText className="size-3.5 shrink-0 opacity-70" />
                    <span className="min-w-0 flex-1 truncate font-medium">{a.name}</span>
                    {inst ? (
                      <AssetStateBadge state={inst.state} />
                    ) : (
                      <span className="font-mono text-[10px] text-muted-foreground">not yet</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function DiffView({ diff }: { diff: DiffLine[] }) {
  const tone: Record<DiffLine['kind'], string> = {
    add: 'border-l-2 border-success bg-success/10 text-foreground',
    remove: 'border-l-2 border-destructive bg-destructive/10 text-muted-foreground line-through',
    keep: 'border-l-2 border-transparent text-muted-foreground',
  }
  const sign: Record<DiffLine['kind'], string> = { add: '+', remove: '−', keep: ' ' }
  return (
    <div className="space-y-px overflow-hidden rounded-md border border-border bg-muted/40 py-1">
      {diff.map((l, i) => (
        <p key={i} className={`flex gap-2 px-3 py-1 text-[12px] leading-relaxed ${tone[l.kind]}`}>
          <span className="shrink-0 font-mono">{sign[l.kind]}</span>
          <span>{l.text}</span>
        </p>
      ))}
    </div>
  )
}

function SuggestionCard({ proposal }: { proposal: ProposalBlueprint }) {
  const runtime = useSimStore((s) => s.proposals[proposal.id])
  const resolveProposal = useSimStore((s) => s.resolveProposal)
  const open = runtime?.status === 'open'
  return (
    <div className="rounded-lg border border-border bg-card px-3.5 py-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-semibold">{proposal.title}</p>
        {!open && <Badge variant="muted" className="font-normal">{runtime?.status === 'accepted' ? 'Applied' : 'Set aside'}</Badge>}
      </div>
      <p className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
        <AgentChip agent={proposal.sourceAgent} /> · {confidenceWording(proposal.confidence)}
      </p>
      <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">{proposal.summary}</p>
      <div className="mt-2">
        <DiffView diff={proposal.diff} />
      </div>
      {open && (
        <div className="mt-2.5 flex gap-2">
          <Button size="sm" onClick={() => resolveProposal(proposal.id, true)}>Apply change</Button>
          <Button size="sm" variant="outline" onClick={() => resolveProposal(proposal.id, false)}>Set aside</Button>
        </div>
      )}
    </div>
  )
}

function Sources({ asset, onPick }: { asset: ArtifactInstance; onPick: (id: string) => void }) {
  const artifacts = useSimStore((s) => s.artifacts)
  const upstream = asset.lineage.map((id) => artifacts.find((a) => a.id === id) ?? ARTIFACT_MAP.get(id)).filter(Boolean)
  const downstream = ARTIFACTS.filter((a) => a.lineage.includes(asset.id))
  const Row = ({ id, name, dir }: { id: string; name: string; dir: 'up' | 'down' }) => (
    <button
      type="button"
      onClick={() => onPick(id)}
      className="flex w-full items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-left text-[12.5px] hover:border-primary/40"
    >
      {dir === 'up' ? <ArrowUp className="size-3.5 text-muted-foreground" /> : <ArrowDown className="size-3.5 text-muted-foreground" />}
      <span className="font-medium">{name}</span>
    </button>
  )
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Built from</p>
        {upstream.length === 0 ? (
          <p className="text-[12.5px] text-muted-foreground">Nothing — this is a root document.</p>
        ) : (
          <div className="space-y-1.5">{upstream.map((u) => <Row key={u!.id} id={u!.id} name={u!.name} dir="up" />)}</div>
        )}
      </div>
      <div>
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Feeds into</p>
        {downstream.length === 0 ? (
          <p className="text-[12.5px] text-muted-foreground">Nothing downstream yet.</p>
        ) : (
          <div className="space-y-1.5">{downstream.map((d) => <Row key={d.id} id={d.id} name={d.name} dir="down" />)}</div>
        )}
      </div>
    </div>
  )
}

function Ask() {
  const [q, setQ] = useState('')
  const [thread, setThread] = useState<{ role: 'user' | 'assistant'; text: string }[]>([])
  const ask = () => {
    if (!q.trim()) return
    const lower = q.toLowerCase()
    const hit = ASSISTANT_SCRIPT.find((e) => e.match.some((m) => lower.includes(m.toLowerCase())))
    setThread((t) => [...t, { role: 'user', text: q }, { role: 'assistant', text: hit?.answer ?? ASSISTANT_FALLBACK }])
    setQ('')
  }
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pb-2">
        {thread.length === 0 && (
          <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
            Ask about this document — any language is fine.
          </p>
        )}
        {thread.map((m, i) => (
          <div key={i} className={cn('rounded-lg px-3 py-2 text-[12.5px] leading-relaxed', m.role === 'user' ? 'ml-5 bg-primary text-primary-foreground' : 'mr-5 border border-border bg-muted/40 text-muted-foreground')}>
            {m.text}
          </div>
        ))}
      </div>
      <div className="flex gap-2 border-t border-border pt-2.5">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask()}
          placeholder="Ask…"
          className="min-w-0 flex-1 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none placeholder:text-muted-foreground focus:border-primary/50"
        />
        <Button size="sm" onClick={ask}>Ask</Button>
      </div>
    </div>
  )
}

type Tab = 'content' | 'sources' | 'changes' | 'ask'

export function AssetDetail({ asset, onBack, onPick }: { asset: ArtifactInstance; onBack?: () => void; onPick: (id: string) => void }) {
  const proposals = useSimStore((s) => s.proposals)
  const tasks = useSimStore((s) => s.tasks)
  const related = PROPOSALS.filter((p) => p.targetArtifactId === asset.id && tasks[p.afterTask]?.status === 'done')
  const openCount = related.filter((p) => proposals[p.id]?.status === 'open').length
  const [tab, setTab] = useState<Tab>('content')
  return (
    <div className="flex min-h-0 flex-1 flex-col px-4 py-3">
      {onBack && (
        <button type="button" onClick={onBack} className="mb-2 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-3.5" /> All assets
        </button>
      )}
      <div className="mb-2.5 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Step {asset.taskRef} · <AgentChip agent={asset.producedByAgent} />
          </p>
          <h3 className="mt-0.5 truncate text-base font-semibold">{asset.name}</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="font-mono text-[11px] text-muted-foreground">v{asset.version}</span>
          <AssetStateBadge state={asset.state} />
        </div>
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="flex-wrap">
          <TabsTrigger value="content">Content</TabsTrigger>
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="changes">Changes{openCount > 0 ? ` (${openCount})` : ''}</TabsTrigger>
          <TabsTrigger value="ask">Ask</TabsTrigger>
        </TabsList>
        <TabsContent value="content" className="mt-3 min-h-0 flex-1 overflow-y-auto">
          <MiniMarkdown text={asset.content} />
        </TabsContent>
        <TabsContent value="sources" className="mt-3 min-h-0 flex-1 overflow-y-auto">
          <Sources asset={asset} onPick={onPick} />
        </TabsContent>
        <TabsContent value="changes" className="mt-3 min-h-0 flex-1 space-y-2.5 overflow-y-auto">
          {related.length === 0 ? (
            <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">No suggested changes.</p>
          ) : (
            related.map((p) => <SuggestionCard key={p.id} proposal={p} />)
          )}
        </TabsContent>
        <TabsContent value="ask" className="mt-3 min-h-0 flex-1">
          <Ask />
        </TabsContent>
      </Tabs>
    </div>
  )
}

export function ArtifactsPanel() {
  const artifacts = useSimStore((s) => s.artifacts)
  const selectedAssetId = useSimStore((s) => s.selectedAssetId)
  const selectAsset = useSimStore((s) => s.selectAsset)
  const current = artifacts.find((a) => a.id === selectedAssetId) ?? null

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Everything produced</p>
          <h2 className="text-base font-semibold tracking-tight">Artifacts</h2>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{artifacts.length}/{ARTIFACTS.length}</span>
      </div>
      {current ? (
        <AssetDetail asset={current} onBack={() => selectAsset(null)} onPick={selectAsset} />
      ) : (
        <AssetList onPick={selectAsset} />
      )}
    </div>
  )
}
