import { Check } from 'lucide-react'
import { useSimStore, stageProgress, currentStage } from '../../store/useSimStore'
import { STAGES, STAGE_ORDER } from '../../lib/profiles'
import { cn } from '../../lib/cn'

/**
 * Level 1 — the project backbone. A horizontal stepper across the five
 * stages; click to move the workspace to that stage. Replaces the cramped
 * stage dots with something readable.
 */
export function StageSpine() {
  const tasks = useSimStore((s) => s.tasks)
  const viewedStageId = useSimStore((s) => s.viewedStageId)
  const setViewedStage = useSimStore((s) => s.setViewedStage)
  const live = currentStage(tasks)
  const shown = viewedStageId ?? live

  return (
    <nav aria-label="Stages" className="flex items-stretch gap-1 overflow-x-auto px-4 py-2.5">
      {STAGE_ORDER.map((sid, i) => {
        const stage = STAGES[sid]
        const pct = stageProgress(tasks, sid)
        const done = pct === 100
        const isShown = sid === shown
        const isLive = sid === live
        return (
          <button
            key={sid}
            type="button"
            onClick={() => setViewedStage(sid === live ? null : sid)}
            aria-current={isShown ? 'step' : undefined}
            className={cn(
              'group flex min-w-0 flex-1 items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors',
              isShown ? 'border-primary/50 bg-accent' : 'border-transparent hover:bg-accent/60',
            )}
          >
            <span
              className={cn(
                'grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold',
                done && 'border-success bg-success text-white',
                !done && isLive && 'border-primary text-primary',
                !done && !isLive && 'border-border text-muted-foreground',
              )}
            >
              {done ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className={cn('truncate text-[12.5px] font-medium', !isShown && 'text-muted-foreground')}>
                  {stage.name}
                </span>
                {isLive && !done && (
                  <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-status-running pulse-running" />
                )}
              </span>
              <span className="mt-1 block h-1 overflow-hidden rounded-full bg-border">
                <span
                  className={cn('block h-full rounded-full transition-[width]', done ? 'bg-success' : 'bg-status-running')}
                  style={{ width: `${pct}%` }}
                />
              </span>
            </span>
          </button>
        )
      })}
    </nav>
  )
}
