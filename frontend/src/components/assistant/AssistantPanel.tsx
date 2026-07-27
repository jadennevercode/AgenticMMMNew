import { useEffect, useRef, useState } from 'react'
import { AtSign, FileText, X } from 'lucide-react'
import { api } from '../../api/client'
import { useSimStore, type BackendInsight } from '../../store/useSimStore'
import { ARTIFACT_MAP } from '../../lib/artifacts-data'
import { INSIGHT_KIND_LABEL, confidenceWording } from '../../lib/ui-language'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'
import type { ChatMention, EvidenceRef, InsightKind, Mentionable } from '../../lib/types'

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

/** A chip for one pinned object, above the composer or on a sent turn. */
function MentionChip({ label, onRemove }: { label: string; onRemove?: () => void }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground">
      <AtSign className="size-2.5 shrink-0" />
      <span className="truncate" title={label}>{label}</span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${label}`}
          className="shrink-0 rounded text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="size-2.5" />
        </button>
      )}
    </span>
  )
}

function Chat() {
  const assistant = useSimStore((s) => s.assistant)
  const askAssistant = useSimStore((s) => s.askAssistant)
  const projectId = useSimStore((s) => s.activeProjectId)
  const staged = useSimStore((s) => s.pendingMentions)
  const [input, setInput] = useState('')
  const [mentions, setMentions] = useState<ChatMention[]>([])
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), [assistant.length])

  // "Ask about this chart" elsewhere in the app stages a mention here.
  useEffect(() => {
    if (staged.length) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- adopting a value staged by another surface, not deriving state
      setMentions((prev) => [...prev.filter((m) => !staged.some((s) => s.refId === m.refId)), ...staged])
      inputRef.current?.focus()
    }
  }, [staged])

  // ── the @ picker ──
  const [picker, setPicker] = useState<{ open: boolean; query: string; at: number }>(
    { open: false, query: '', at: -1 })
  const [options, setOptions] = useState<Mentionable[]>([])
  const [active, setActive] = useState(0)

  useEffect(() => {
    if (!picker.open || !projectId) return
    let cancelled = false
    api.mentionables(projectId, picker.query)
      .then((o) => { if (!cancelled) { setOptions(o); setActive(0) } })
      .catch(() => { if (!cancelled) setOptions([]) })
    return () => { cancelled = true }
  }, [picker.open, picker.query, projectId])

  function onChange(value: string) {
    setInput(value)
    // The picker opens on an `@` that starts a word and closes on whitespace.
    const caret = inputRef.current?.selectionStart ?? value.length
    const at = value.lastIndexOf('@', caret - 1)
    const ok = at >= 0 && (at === 0 || /\s/.test(value[at - 1]))
    const frag = ok ? value.slice(at + 1, caret) : ''
    setPicker(ok && !/\s/.test(frag) ? { open: true, query: frag, at } : { open: false, query: '', at: -1 })
  }

  function pick(o: Mentionable) {
    setMentions((prev) => (prev.some((m) => m.refId === o.refId && m.kind === o.kind)
      ? prev
      : [...prev, { kind: o.kind, refId: o.refId, label: o.label }]))
    // Drop the "@fragment" the user was typing — the chip is the reference now.
    if (picker.at >= 0) {
      const caret = inputRef.current?.selectionStart ?? input.length
      setInput(input.slice(0, picker.at) + input.slice(caret))
    }
    setPicker({ open: false, query: '', at: -1 })
    inputRef.current?.focus()
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (picker.open && options.length) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setActive((i) => (i + 1) % options.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => (i - 1 + options.length) % options.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); pick(options[active]); return }
      if (e.key === 'Escape') { e.preventDefault(); setPicker({ open: false, query: '', at: -1 }); return }
    }
    if (e.key === 'Enter') send(input)
  }

  const send = (text: string) => {
    if (!text.trim()) return
    askAssistant(text, mentions)
    setInput('')
    setMentions([])
    setPicker({ open: false, query: '', at: -1 })
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto pb-2">
        {assistant.map((m, i) => (
          <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={cn('max-w-[88%] rounded-lg px-3 py-2 text-[12.5px] leading-relaxed', m.role === 'user' ? 'bg-primary text-primary-foreground' : 'border border-border bg-muted/40 text-muted-foreground')}>
              {m.mentions && m.mentions.length > 0 && (
                <span className="mb-1 flex flex-wrap gap-1">
                  {m.mentions.map((mm) => <MentionChip key={mm.refId + mm.kind} label={mm.label} />)}
                </span>
              )}
              {m.text}
              {m.evidence && <EvidenceRow evidence={m.evidence} />}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="border-t border-border pt-2.5">
        {mentions.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {mentions.map((m) => (
              <MentionChip
                key={m.refId + m.kind}
                label={m.label}
                onRemove={() => setMentions((prev) => prev.filter((x) => !(x.refId === m.refId && x.kind === m.kind)))}
              />
            ))}
          </div>
        )}
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SUGGESTED.map((q) => (
            <button key={q} type="button" onClick={() => send(q)} className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:border-primary/40 hover:text-foreground">
              {q}
            </button>
          ))}
        </div>
        <div className="relative flex gap-2">
          {picker.open && options.length > 0 && (
            <ul
              role="listbox"
              aria-label="Mentionable objects"
              className="absolute bottom-full left-0 z-30 mb-1 max-h-56 w-72 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg"
            >
              {options.map((o, i) => (
                <li key={o.kind + o.refId}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={i === active}
                    onMouseEnter={() => setActive(i)}
                    onMouseDown={(e) => { e.preventDefault(); pick(o) }}
                    className={cn(
                      'flex w-full items-baseline justify-between gap-2 rounded px-2 py-1 text-left text-xs',
                      i === active ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/60',
                    )}
                  >
                    <span className="truncate" title={o.label}>{o.label}</span>
                    <span className="shrink-0 text-[10px] text-muted-foreground/70">{o.group}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            role="combobox"
            aria-expanded={picker.open}
            aria-controls="mention-listbox"
            aria-autocomplete="list"
            placeholder="Ask about the project — type @ to pin a chart or artifact"
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
