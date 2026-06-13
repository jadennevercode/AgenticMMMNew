import { useSimStore, stageProgress, currentStage } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { STAGES, STAGE_ORDER } from '../../lib/profiles'
import { TaskBadge, StatusPill } from '../ui/primitives'
import { cn } from '../../lib/cn'

function StageDots() {
  const tasks = useSimStore((s) => s.tasks)
  const viewedStageId = useSimStore((s) => s.viewedStageId)
  const setViewedStage = useSimStore((s) => s.setViewedStage)
  const live = currentStage(tasks)
  const shown = viewedStageId ?? live
  return (
    <div className="flex items-center gap-1.5">
      {STAGE_ORDER.map((sid) => {
        const pct = stageProgress(tasks, sid)
        const isShown = sid === shown
        const isLive = sid === live
        const done = pct === 100
        return (
          <button
            key={sid}
            type="button"
            title={`${STAGES[sid].name} · ${pct}%`}
            onClick={() => setViewedStage(sid === live ? null : sid)}
            className={cn(
              'h-1.5 flex-1 rounded-full transition-colors',
              isShown ? 'ring-2 ring-primary/40' : '',
              done ? 'bg-status-done' : isLive ? 'bg-status-running' : 'bg-border',
            )}
          />
        )
      })}
    </div>
  )
}

export function StageTasksSidebar() {
  const tasks = useSimStore((s) => s.tasks)
  const viewedStageId = useSimStore((s) => s.viewedStageId)
  const selectedTaskId = useSimStore((s) => s.selectedTaskId)
  const selectTask = useSimStore((s) => s.selectTask)
  const setViewedStage = useSimStore((s) => s.setViewedStage)
  const live = currentStage(tasks)
  const stageId = viewedStageId ?? live
  const stage = STAGES[stageId]
  const stageTasks = TASKS.filter((t) => t.stage === stageId)
  const doneN = stageTasks.filter((t) => tasks[t.id]?.status === 'done').length

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-baseline justify-between">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Stage {stage.index} of {STAGE_ORDER.length}
          </p>
          {viewedStageId && viewedStageId !== live && (
            <button type="button" onClick={() => setViewedStage(null)} className="text-[10px] text-primary hover:underline">
              Back to current
            </button>
          )}
        </div>
        <h2 className="mt-0.5 text-sm font-semibold leading-tight">{stage.name}</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{doneN}/{stageTasks.length} done</p>
        <div className="mt-2.5">
          <StageDots />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {stageTasks.map((t) => {
          const rt = tasks[t.id]
          const selected = selectedTaskId === t.id
          const waiting = rt?.status === 'awaiting_human'
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => selectTask(t.id)}
              className={cn(
                'mb-1 flex w-full flex-col gap-1.5 rounded-md border px-3 py-2.5 text-left transition-colors',
                selected ? 'border-primary/50 bg-accent' : 'border-transparent hover:bg-accent',
                waiting && !selected && 'border-warning/40',
              )}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-muted-foreground">{t.id}</span>
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{t.name}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <TaskBadge task={t} />
                <StatusPill status={rt?.status ?? 'pending'} />
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
