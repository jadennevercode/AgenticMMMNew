import { CheckCircle2, ChevronRight, CircleDot, FileText, Lightbulb, Sparkles, TriangleAlert } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { AGENT_COLOR } from '../../lib/profiles'
import { cn } from '../../lib/cn'
import type { SimEvent } from '../../lib/types'

const EVENT_ICON: Record<SimEvent['type'], typeof FileText> = {
  task_start: CircleDot,
  task_done: CheckCircle2,
  artifact: FileText,
  decision_open: TriangleAlert,
  decision_resolved: CheckCircle2,
  suggestion: Sparkles,
  finding: Lightbulb,
  info: ChevronRight,
}

export function ActivityPanel() {
  const events = useSimStore((s) => s.events)
  const selectAsset = useSimStore((s) => s.selectAsset)
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {events.length === 0 && (
        <p className="px-2 py-8 text-center text-xs text-muted-foreground">
          Press “Run” to start. Everything that happens shows up here.
        </p>
      )}
      {events.map((e) => {
        const Icon = EVENT_ICON[e.type]
        const clickable = e.type === 'artifact'
        return (
          <button
            key={e.id}
            type="button"
            disabled={!clickable}
            onClick={() => {
              // jump to the latest produced asset referenced by this line
              const latest = useSimStore.getState().artifacts.at(-1)
              if (latest) selectAsset(latest.id)
            }}
            className={cn('feed-in flex w-full gap-2.5 rounded-md px-2 py-1.5 text-left text-[12px] leading-snug', clickable && 'hover:bg-accent')}
          >
            <Icon className="mt-px size-3.5 shrink-0" style={{ color: AGENT_COLOR[e.agent] }} />
            <span className="min-w-0 flex-1 text-muted-foreground">{e.message}</span>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground/70">d{e.tick}</span>
          </button>
        )
      })}
    </div>
  )
}
