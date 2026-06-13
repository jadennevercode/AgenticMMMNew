import { useState } from 'react'
import { CheckCircle2, Download, FileUp, Paperclip, X } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { Button } from '../ui/button'
import { AgentChip } from '../ui/primitives'
import { cn } from '../../lib/cn'
import type { AssignmentBlueprint, AssignmentRuntime } from '../../lib/types'

export function AssignmentCard({
  assignment,
  runtime,
  taskId,
}: {
  assignment: AssignmentBlueprint
  runtime: AssignmentRuntime
  taskId: string
}) {
  const submitAssignment = useSimStore((s) => s.submitAssignment)
  const task = TASKS.find((t) => t.id === taskId)
  const open = runtime.status === 'open'
  const isExport = assignment.kind === 'export'
  // Which items the person has attached (upload) / downloaded (export)
  const [done, setDone] = useState<string[]>([])
  const [note, setNote] = useState('')
  const allDone = done.length === assignment.items.length

  const actionLabel = isExport ? 'Download' : 'Attach'
  const ActionIcon = isExport ? Download : FileUp

  return (
    <article className={cn('rounded-xl border bg-card', open ? 'border-warning/50 shadow-sm' : 'border-border')}>
      <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-3.5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Step {taskId} {task && <>· {isExport ? 'owner' : 'requested by'} <AgentChip agent={task.agent} /></>}
          </p>
          <h3 className="mt-1 text-base font-semibold">{assignment.title}</h3>
        </div>
        {!open && runtime.submittedAtTick !== undefined && (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
            <CheckCircle2 className="size-3" /> day {runtime.submittedAtTick}
          </span>
        )}
      </header>

      <div className="space-y-4 px-5 py-4">
        <p className="text-sm leading-relaxed">{assignment.prompt}</p>

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {open ? (isExport ? 'Files to send' : 'Attach files') : isExport ? 'Sent' : 'Provided'}
          </p>
          <div className="space-y-1.5">
            {assignment.items.map((item) => {
              const isDone = !open || done.includes(item)
              return (
                <div
                  key={item}
                  className={cn(
                    'flex items-center gap-2.5 rounded-md border px-3 py-2 text-[13px]',
                    isDone ? 'border-border bg-muted/40' : 'border-dashed border-border',
                  )}
                >
                  <Paperclip className="size-3.5 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{item}</span>
                  {open &&
                    (isDone ? (
                      isExport ? (
                        <CheckCircle2 className="size-3.5 text-success" />
                      ) : (
                        <button
                          type="button"
                          onClick={() => setDone((a) => a.filter((x) => x !== item))}
                          className="text-muted-foreground hover:text-foreground"
                        >
                          <X className="size-3.5" />
                        </button>
                      )
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => setDone((a) => [...a, item])}>
                        <ActionIcon />
                        {actionLabel}
                      </Button>
                    ))}
                  {!open && <CheckCircle2 className="size-3.5 text-success" />}
                </div>
              )
            })}
          </div>
        </div>

        {open ? (
          <div className="space-y-2 border-t border-border pt-3">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add a note (optional, any language)"
              className="w-full rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none placeholder:text-muted-foreground focus:border-primary/50"
            />
            <div className="flex items-center justify-between gap-2">
              <span className="text-[11px] text-muted-foreground">
                {done.length}/{assignment.items.length} {isExport ? 'downloaded' : 'attached'}
              </span>
              <Button size="sm" disabled={!allDone} onClick={() => submitAssignment(taskId, note)}>
                <ActionIcon />
                {assignment.submitLabel}
              </Button>
            </div>
          </div>
        ) : (
          runtime.note && <p className="border-t border-border pt-3 text-[12px] text-muted-foreground">Note: {runtime.note}</p>
        )}
      </div>
    </article>
  )
}
