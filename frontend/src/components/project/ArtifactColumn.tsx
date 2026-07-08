import { FileText } from 'lucide-react'
import { useSimStore, currentStage } from '../../store/useSimStore'
import { ARTIFACTS } from '../../lib/artifacts-data'
import { TASKS } from '../../lib/scenario'
import { STAGES } from '../../lib/profiles'
import { deliverableState, chainProgress, buildChain } from '../../lib/artifact-graph'
import { AgentChip, DeliverableBadge } from '../ui/primitives'
import { cn } from '../../lib/cn'

/**
 * Level 2 — the deliverables of the active stage. Each card is an artifact
 * with a lifecycle state that lights up as its build chain runs. Locked
 * cards are still clickable so you can preview what will be built.
 */
export function ArtifactColumn({ focusId, onPick }: { focusId: string | null; onPick: (id: string) => void }) {
  const tasks = useSimStore((s) => s.tasks)
  const artifacts = useSimStore((s) => s.artifacts)
  const viewedStageId = useSimStore((s) => s.viewedStageId)
  const stageId = viewedStageId ?? currentStage(tasks)
  const stage = STAGES[stageId]
  const items = ARTIFACTS.filter((a) => a.stage === stageId && !a.internal)
  const producedById = new Map(artifacts.map((a) => [a.id, a]))
  const readyN = items.filter((a) => {
    const st = deliverableState(a.id, tasks, producedById.get(a.id)?.state)
    return st === 'ready' || st === 'confirmed'
  }).length

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Deliverables</p>
        <h2 className="mt-0.5 text-sm font-semibold leading-tight">{stage.name}</h2>
        <p className="mt-0.5 text-[11px] text-muted-foreground">{readyN}/{items.length} ready</p>
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto px-2.5 py-2.5">
        {items.map((a) => {
          const inst = producedById.get(a.id)
          const state = deliverableState(a.id, tasks, inst?.state)
          const { done, total } = chainProgress(a.id, tasks)
          const producer = buildChain(a.id)[0] ?? TASKS.find((t) => t.id === a.taskRef)
          const selected = focusId === a.id
          const dim = state === 'locked'
          return (
            <button
              key={a.id}
              type="button"
              onClick={() => onPick(a.id)}
              className={cn(
                'flex w-full flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
                selected ? 'border-primary/50 bg-accent' : 'border-border hover:bg-accent/60',
                state === 'needs-you' && !selected && 'border-warning/50',
                dim && !selected && 'opacity-65',
              )}
            >
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 text-[13px] font-medium leading-snug">{a.name}</span>
              </div>
              <div className="flex items-center justify-between gap-2 pl-5">
                {producer ? <AgentChip agent={producer.agent} /> : <span />}
                <DeliverableBadge state={state} />
              </div>
              {total > 1 && (
                <div className="flex items-center gap-1 pl-5">
                  {Array.from({ length: total }).map((_, i) => (
                    <span
                      key={i}
                      className={cn('h-1 flex-1 rounded-full', i < done ? 'bg-success' : 'bg-border')}
                    />
                  ))}
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
