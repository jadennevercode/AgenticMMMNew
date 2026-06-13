import { ArrowUpRight, BookMarked, GitMerge, Lock, MinusCircle, PlusCircle, ScrollText } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import {
  FACTOR_TREE,
  INDUSTRY_PACKS,
  REFLOW_CANDIDATES,
  SOLUTION_LIBRARY,
  type FactorNode,
  type LedgerEntry,
} from '../../lib/knowledge-data'
import { SectionHeader } from '../ui/primitives'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../ui/tabs'
import { cn } from '../../lib/cn'

const SOURCE_LABEL: Record<FactorNode['source'], { label: string; cls: string }> = {
  pack: { label: 'Industry pack', cls: 'text-muted-foreground' },
  interview: { label: 'From interview', cls: 'text-agent-business' },
  report: { label: 'From report', cls: 'text-agent-report' },
  ai: { label: 'AI suggested', cls: 'text-primary' },
}

function IndustryPackTab() {
  const grouped = FACTOR_TREE.reduce<Record<string, FactorNode[]>>((acc, n) => {
    ;(acc[n.l1] ??= []).push(n)
    return acc
  }, {})
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-3">
        {INDUSTRY_PACKS.map((p) => (
          <Card key={p.id} className={cn('flex-1 p-4', p.active ? 'border-primary/40' : 'opacity-70')}>
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">{p.name}</p>
              {p.active ? <Badge>Active</Badge> : <Badge variant="muted">Available</Badge>}
            </div>
            <p className="mt-2 flex gap-4 font-mono text-[11px] text-muted-foreground">
              <span>{p.version}</span>
              <span>L1/L2 locked · {p.l1l2Locked}</span>
              <span>L3/L4 · {p.l3l4Count}</span>
              <span>metrics · {p.metricCount}</span>
            </p>
          </Card>
        ))}
      </div>

      <div className="space-y-4">
        {Object.entries(grouped).map(([l1, nodes]) => (
          <div key={l1}>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">{l1}</h4>
            <Card className="overflow-hidden p-0">
              {nodes.map((n, i) => {
                const src = SOURCE_LABEL[n.source]
                return (
                  <div
                    key={`${n.l2}-${n.l3}`}
                    className={cn('flex items-center gap-3 px-4 py-2.5 text-[13px]', i > 0 && 'border-t border-border')}
                  >
                    <span className="w-40 shrink-0 truncate text-muted-foreground">{n.l2}</span>
                    <span className="min-w-0 flex-1">{n.l3}</span>
                    {n.locked ? (
                      <Badge variant="muted" className="font-normal">
                        <Lock />
                        Locked
                      </Badge>
                    ) : (
                      <span className={cn('font-mono text-[10px] uppercase tracking-wider', src.cls)}>{src.label}</span>
                    )}
                  </div>
                )
              })}
            </Card>
          </div>
        ))}
      </div>
    </div>
  )
}

const LEDGER_ICON: Record<LedgerEntry['action'], { icon: typeof PlusCircle; cls: string }> = {
  add: { icon: PlusCircle, cls: 'text-success' },
  remove: { icon: MinusCircle, cls: 'text-destructive' },
  merge: { icon: GitMerge, cls: 'text-primary' },
}

function ChangeLedgerTab() {
  const ledger = useSimStore((s) => s.ledger)
  return (
    <div className="space-y-3">
      <p className="text-[13px] text-muted-foreground">
        Every factor or metric we add, drop or merge is logged here with the reason and who confirmed it —
        so the next project knows why this one looks the way it does.
      </p>
      {ledger.length === 0 && (
        <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-xs text-muted-foreground">
          No changes yet. Accepting a suggested change records it here.
        </p>
      )}
      <div className="space-y-2">
        {ledger.map((entry) => {
          const { icon: Icon, cls } = LEDGER_ICON[entry.action]
          return (
            <Card key={entry.id} className="flex gap-3 p-3.5">
              <Icon className={cn('mt-0.5 size-4 shrink-0', cls)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{entry.target}</p>
                  <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {entry.action}
                    {entry.day !== undefined ? ` · day ${entry.day}` : ' · seeded'}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{entry.reason}</p>
                <p className="mt-1 flex gap-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground/80">
                  <span>source · {entry.source}</span>
                  <span>confirmed by · {entry.confirmedBy}</span>
                </p>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

function SolutionLibraryTab() {
  return (
    <div>
      <p className="mb-3 text-[13px] text-muted-foreground">
        Reusable across every project — rule sets and templates the team maintains centrally.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {SOLUTION_LIBRARY.map((a) => (
          <Card key={a.id} className="p-4">
            <div className="flex items-center gap-2">
              {a.kind === 'rule' ? (
                <ScrollText className="size-4 text-agent-data" />
              ) : (
                <BookMarked className="size-4 text-agent-report" />
              )}
              <p className="text-sm font-semibold">{a.name}</p>
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">{a.detail}</p>
          </Card>
        ))}
      </div>
    </div>
  )
}

function ReflowTab() {
  return (
    <div>
      <p className="mb-3 text-[13px] text-muted-foreground">
        At wrap-up, decide which of this project’s customizations are worth promoting into the shared library
        for future projects.
      </p>
      <div className="space-y-2">
        {REFLOW_CANDIDATES.map((c) => (
          <Card key={c.id} className="flex items-start gap-3 p-4">
            <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{c.name}</p>
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">{c.detail}</p>
            </div>
            <Button size="sm" variant="outline">
              Promote
            </Button>
          </Card>
        ))}
      </div>
    </div>
  )
}

export default function KnowledgeView() {
  return (
    <div className="mx-auto max-w-[1200px] px-6 py-6">
      <SectionHeader kicker="What the team knows" title="Knowledge" />
      <Tabs defaultValue="pack">
        <TabsList>
          <TabsTrigger value="pack">Industry pack</TabsTrigger>
          <TabsTrigger value="ledger">Change ledger</TabsTrigger>
          <TabsTrigger value="library">Solution library</TabsTrigger>
          <TabsTrigger value="reflow">Promote to library</TabsTrigger>
        </TabsList>
        <TabsContent value="pack" className="mt-5">
          <IndustryPackTab />
        </TabsContent>
        <TabsContent value="ledger" className="mt-5">
          <ChangeLedgerTab />
        </TabsContent>
        <TabsContent value="library" className="mt-5">
          <SolutionLibraryTab />
        </TabsContent>
        <TabsContent value="reflow" className="mt-5">
          <ReflowTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
