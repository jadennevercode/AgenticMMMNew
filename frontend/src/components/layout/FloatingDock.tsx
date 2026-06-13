import { Activity, MessageSquare, X } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { INSIGHTS } from '../../lib/collab-data'
import { ActivityPanel } from './ActivityPanel'
import { AssistantPanel } from '../assistant/AssistantPanel'
import { cn } from '../../lib/cn'
import type { ReactNode } from 'react'

function FloatingCard({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="feed-in flex h-[min(560px,calc(100vh-7rem))] w-[380px] max-w-[calc(100vw-2rem)] flex-col rounded-xl border border-border bg-card shadow-xl">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="text-sm font-semibold">{title}</p>
        <button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col px-4 py-3">{children}</div>
    </div>
  )
}

function Fab({ onClick, active, badge, label, children }: { onClick: () => void; active: boolean; badge?: number; label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={cn(
        'relative grid size-11 place-items-center rounded-full border shadow-md transition-colors',
        active ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-foreground hover:bg-accent',
      )}
    >
      {children}
      {badge !== undefined && badge > 0 && (
        <span className="absolute -right-1 -top-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 font-mono text-[10px] text-primary-foreground ring-2 ring-card">
          {badge}
        </span>
      )}
    </button>
  )
}

export function FloatingDock() {
  const panels = useSimStore((s) => s.panels)
  const togglePanel = useSimStore((s) => s.togglePanel)
  const newFindings = useSimStore((s) =>
    INSIGHTS.filter((i) => s.insights[i.id]?.status === 'new' && s.insights[i.id]?.surfacedAtTick !== undefined).length,
  )

  return (
    <div className="fixed bottom-5 right-5 z-30 flex flex-col items-end gap-3">
      {panels.activity && (
        <FloatingCard title="Activity" onClose={() => togglePanel('activity', false)}>
          <ActivityPanel />
        </FloatingCard>
      )}
      {panels.assistant && (
        <FloatingCard title="Assistant" onClose={() => togglePanel('assistant', false)}>
          <AssistantPanel />
        </FloatingCard>
      )}
      <div className="flex gap-2.5">
        <Fab onClick={() => togglePanel('activity')} active={panels.activity} label="Activity log">
          <Activity className="size-5" />
        </Fab>
        <Fab onClick={() => togglePanel('assistant')} active={panels.assistant} badge={newFindings} label="Assistant">
          <MessageSquare className="size-5" />
        </Fab>
      </div>
    </div>
  )
}
