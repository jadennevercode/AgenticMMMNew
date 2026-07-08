import { useEffect, useRef, useState } from 'react'
import { FileText } from 'lucide-react'
import { useSimStore, type BackendInsight } from '../../store/useSimStore'
import { ARTIFACT_MAP } from '../../lib/artifacts-data'
import { INSIGHT_KIND_LABEL, confidenceWording } from '../../lib/ui-language'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'
import type { EvidenceRef, InsightKind } from '../../lib/types'

const SUGGESTED = [
  'Why was 批发 merged into TT?',
  'Is the cooler ROI believable?',
  'What happened with O2O in 2025?',
]

function EvidenceRow({ evidence }: { evidence: EvidenceRef[] }) {
  const selectAsset = useSimStore((s) => s.selectAsset)
  if (!evidence.length) return null
  return (
    <span className="mt-2 flex flex-wrap gap-1.5">
      {evidence.map((ev) => (
        <button
          key={ev.artifactId}
          type="button"
          onClick={() => selectAsset(ev.artifactId)}
          className="inline-flex items-center gap-1 rounded border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground hover:border-primary/40"
        >
          <FileText className="size-3" />
          {ARTIFACT_MAP.get(ev.artifactId)?.name ?? ev.artifactId}
        </button>
      ))}
    </span>
  )
}

function FindingCard({ insight }: { insight: BackendInsight }) {
  const resolveInsight = useSimStore((s) => s.resolveInsight)
  const selectAsset = useSimStore((s) => s.selectAsset)
  const kind = INSIGHT_KIND_LABEL[insight.kind as InsightKind] ?? INSIGHT_KIND_LABEL.connection
  const Icon = kind.icon
  const isNew = insight.status === 'new'
  return (
    <div className={cn('rounded-lg border bg-card px-3.5 py-3', isNew ? 'border-primary/40' : 'border-border opacity-80')}>
      <div className="flex items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          <Icon className="size-3.5 text-primary" />
          {kind.label} · {confidenceWording(insight.confidence)}
        </p>
        {!isNew && <Badge variant="muted" className="font-normal">{insight.status === 'actioned' ? 'Picked up' : 'Dismissed'}</Badge>}
      </div>
      <h4 className="mt-1.5 text-[13px] font-semibold leading-snug">{insight.title}</h4>
      <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">{insight.finding}</p>
      <EvidenceRow evidence={insight.evidence} />
      {isNew && (
        <div className="mt-2.5 flex flex-wrap gap-2">
          {insight.actions.map((a) => (
            <Button
              key={a.label}
              size="sm"
              variant={a.kind === 'open_asset' ? 'default' : 'outline'}
              onClick={() => {
                if (a.kind === 'open_asset' && a.artifactId) selectAsset(a.artifactId)
                resolveInsight(insight.id, true)
              }}
            >
              {a.label}
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={() => resolveInsight(insight.id, false)}>Not useful</Button>
        </div>
      )}
    </div>
  )
}

function Findings() {
  const insights = useSimStore((s) => s.insights)
  const surfaced = insights.filter((i) => i.surfacedAtTick !== undefined)
  if (surfaced.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border px-3 py-8 text-center text-xs text-muted-foreground">
        As the project runs, the AI watches across stages and posts connections, gaps and contradictions here.
      </div>
    )
  }
  return <div className="space-y-2.5">{[...surfaced].reverse().map((i) => <FindingCard key={i.id} insight={i} />)}</div>
}

function Chat() {
  const assistant = useSimStore((s) => s.assistant)
  const askAssistant = useSimStore((s) => s.askAssistant)
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), [assistant.length])
  const send = (text: string) => {
    if (!text.trim()) return
    askAssistant(text)
    setInput('')
  }
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto pb-2">
        {assistant.map((m, i) => (
          <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={cn('max-w-[88%] rounded-lg px-3 py-2 text-[12.5px] leading-relaxed', m.role === 'user' ? 'bg-primary text-primary-foreground' : 'border border-border bg-muted/40 text-muted-foreground')}>
              {m.text}
              {m.evidence && <EvidenceRow evidence={m.evidence} />}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-border pt-2.5">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SUGGESTED.map((q) => (
            <button key={q} type="button" onClick={() => send(q)} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-foreground">
              {q}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder="Ask about the project — any language"
            className="min-w-0 flex-1 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none placeholder:text-muted-foreground focus:border-primary/50"
          />
          <Button size="sm" onClick={() => send(input)}>Send</Button>
        </div>
      </div>
    </div>
  )
}

export function AssistantPanel() {
  const newCount = useSimStore((s) =>
    s.insights.filter((i) => i.status === 'new' && i.surfacedAtTick !== undefined).length,
  )
  const [tab, setTab] = useState('chat')
  return (
    <Tabs value={tab} onValueChange={setTab} className="flex h-full flex-col">
      <TabsList>
        <TabsTrigger value="chat">Ask</TabsTrigger>
        <TabsTrigger value="findings">Noticed{newCount > 0 ? ` (${newCount})` : ''}</TabsTrigger>
      </TabsList>
      <TabsContent value="chat" className="mt-3 min-h-0 flex-1">
        <Chat />
      </TabsContent>
      <TabsContent value="findings" className="mt-3 min-h-0 flex-1 overflow-y-auto">
        <Findings />
      </TabsContent>
    </Tabs>
  )
}
