import { AlertTriangle, ArrowRight, ArrowUpRight, Check, CheckCircle2, Download, FileText, Loader2 } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { ARTIFACT_MAP } from '../../lib/artifacts-data'
import { TASK_TRACE, TASK_FINDINGS } from '../../lib/task-detail'
import { AGENTS } from '../../lib/profiles'
import { DecisionCard } from '../decisions/DecisionCard'
import { AssignmentCard } from './AssignmentCard'
import { AgentChip, TaskBadge, StatusPill } from '../ui/primitives'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'
import { taskNeed, type EvidenceRef, type TaskBlueprint, type TaskStatus } from '../../lib/types'

function pendingHumanTasks(tasks: Record<string, { status: string }>): TaskBlueprint[] {
  return TASKS.filter((t) => taskNeed(t) && tasks[t.id]?.status === 'awaiting_human')
}

/** Chips for upstream/downstream artifacts; click selects in the right panel */
function ArtifactRefs({ ids, kind }: { ids: string[]; kind: 'in' | 'out' }) {
  const artifacts = useSimStore((s) => s.artifacts)
  const selectAsset = useSimStore((s) => s.selectAsset)
  if (ids.length === 0) return <p className="text-[12.5px] text-muted-foreground">—</p>
  return (
    <div className="flex flex-wrap gap-1.5">
      {ids.map((id) => {
        const bp = ARTIFACT_MAP.get(id)
        if (!bp) return null
        const produced = artifacts.find((a) => a.id === id)
        const exportable = kind === 'out' && bp.exportable && produced
        return (
          <span key={id} className="inline-flex items-center">
            <button
              type="button"
              disabled={!produced}
              onClick={() => selectAsset(id)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs',
                produced ? 'border-border bg-card hover:border-primary/40' : 'border-dashed border-border opacity-50',
              )}
            >
              <FileText className="size-3.5 text-muted-foreground" />
              <span className="font-medium">{bp.name}</span>
              {!produced && <span className="font-mono text-[10px] text-muted-foreground">pending</span>}
            </button>
            {exportable && (
              <span className="ml-1 inline-flex items-center gap-1 rounded-md border border-border px-1.5 py-1 text-[10px] text-muted-foreground">
                <Download className="size-3" /> exportable
              </span>
            )}
          </span>
        )
      })}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      {children}
    </div>
  )
}

function EvidenceChips({ evidence }: { evidence?: EvidenceRef[] }) {
  const artifacts = useSimStore((s) => s.artifacts)
  const selectAsset = useSimStore((s) => s.selectAsset)
  if (!evidence?.length) return null
  return (
    <span className="mt-1 flex flex-wrap gap-1.5">
      {evidence.map((ev) => {
        const produced = artifacts.some((a) => a.id === ev.artifactId)
        const name = ARTIFACT_MAP.get(ev.artifactId)?.name ?? ev.artifactId
        return (
          <button
            key={ev.artifactId}
            type="button"
            disabled={!produced}
            onClick={() => selectAsset(ev.artifactId)}
            className={cn(
              'inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px]',
              produced ? 'border-border bg-card text-muted-foreground hover:border-primary/40' : 'border-dashed border-border text-muted-foreground/60',
            )}
          >
            <FileText className="size-3" />
            {name}
            {ev.note && <span className="opacity-70">· {ev.note}</span>}
          </button>
        )
      })}
    </span>
  )
}

/** Process trace — sub-steps that light up with the run */
function RunTimeline({ taskId, status, progress }: { taskId: string; status: TaskStatus; progress: number }) {
  const steps = TASK_TRACE[taskId]
  if (!steps?.length) return null
  const n = steps.length
  let doneCount = 0
  let activeIdx = -1
  if (status === 'done' || status === 'awaiting_human') {
    doneCount = n
  } else if (status === 'running') {
    doneCount = Math.min(n - 1, Math.floor((progress / 100) * n))
    activeIdx = doneCount
  }
  return (
    <ol className="space-y-0">
      {steps.map((step, i) => {
        const done = i < doneCount
        const active = i === activeIdx
        const last = i === n - 1
        return (
          <li key={i} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  'mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border',
                  done && 'border-success bg-success text-white',
                  active && 'border-primary pulse-running',
                  !done && !active && 'border-border',
                )}
                style={active ? { background: 'var(--color-primary)' } : undefined}
              >
                {done && <Check className="size-2.5" />}
              </span>
              {!last && <span className={cn('w-px flex-1', done ? 'bg-success/40' : 'bg-border')} style={{ minHeight: 14 }} />}
            </div>
            <div className={cn('pb-3', !done && !active && 'opacity-60')}>
              <p className="text-[12.5px] leading-tight">{step.label}</p>
              {step.detail && <p className="mt-0.5 text-[11px] text-muted-foreground">{step.detail}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** Grounded findings — results tied to evidence */
function Findings({ taskId }: { taskId: string }) {
  const findings = TASK_FINDINGS[taskId]
  if (!findings?.length) return null
  return (
    <div className="space-y-2">
      {findings.map((f, i) => {
        const flag = f.tone === 'flag'
        return (
          <div
            key={i}
            className={cn(
              'rounded-md border px-3 py-2',
              flag ? 'border-warning/40 bg-warning/5' : 'border-border bg-card',
            )}
          >
            <p className="flex gap-2 text-[12.5px] leading-relaxed">
              {flag && <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />}
              <span className={flag ? 'text-foreground' : 'text-muted-foreground'}>{f.text}</span>
            </p>
            <EvidenceChips evidence={f.evidence} />
          </div>
        )
      })}
    </div>
  )
}

function TaskDetail({ task }: { task: TaskBlueprint }) {
  const tasks = useSimStore((s) => s.tasks)
  const decisions = useSimStore((s) => s.decisions)
  const assignments = useSimStore((s) => s.assignments)
  const rt = tasks[task.id]
  const need = taskNeed(task)
  const awaiting = rt?.status === 'awaiting_human'

  const status = rt?.status ?? 'pending'
  const started = status === 'running' || status === 'done' || awaiting
  const hasFindings = (TASK_FINDINGS[task.id]?.length ?? 0) > 0
  const upstreamIds = task.dependsOn.flatMap((d) => TASKS.find((t) => t.id === d)?.produces ?? [])

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Step {task.id} · <AgentChip agent={task.agent} />
          </p>
          <h3 className="mt-1 text-lg font-semibold">{task.name}</h3>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{task.summary}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <TaskBadge task={task} />
          <StatusPill status={status} />
        </div>
      </div>

      {/* The actionable card when this task is waiting on a person */}
      {awaiting && need === 'decision' && task.decision && (
        <DecisionCard decision={task.decision} runtime={decisions[task.decision.id]} taskId={task.id} />
      )}
      {awaiting && need === 'input' && task.assignment && (
        <AssignmentCard assignment={task.assignment} runtime={assignments[task.assignment.id]} taskId={task.id} />
      )}

      {/* Process — what the step actually does, lighting up with the run */}
      <Field label={status === 'pending' || status === 'ready' ? 'What it will do' : 'Process'}>
        <p className="mb-2 text-[12.5px] leading-relaxed text-muted-foreground/90">{task.how}</p>
        <RunTimeline taskId={task.id} status={status} progress={rt?.progress ?? 0} />
      </Field>

      {/* Grounded results tied to their source */}
      {started && hasFindings && (
        <Field label="What it found">
          <Findings taskId={task.id} />
        </Field>
      )}
      {started && !hasFindings && (
        <Field label={status === 'done' ? 'Outcome' : 'Working note'}>
          <p className="border-l-2 border-border pl-3 text-[12.5px] leading-relaxed text-muted-foreground/90">{task.workNote}</p>
        </Field>
      )}

      <Field label="Draws on">
        <ArtifactRefs ids={upstreamIds} kind="in" />
        {task.basisNote && <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground/90">{task.basisNote}</p>}
      </Field>

      <Field label="Produces">
        <ArtifactRefs ids={task.produces} kind="out" />
      </Field>

      {rt && rt.runs > 1 && (
        <p className="font-mono text-[11px] text-muted-foreground">Attempt {rt.runs} (sent back earlier)</p>
      )}
    </div>
  )
}

function CalmHint({ pendingCount }: { pendingCount: number }) {
  const tasks = useSimStore((s) => s.tasks)
  const playing = useSimStore((s) => s.playing)
  const running = TASKS.find((t) => tasks[t.id]?.status === 'running')
  const allDone = TASKS.every((t) => tasks[t.id]?.status === 'done')
  if (allDone) {
    return (
      <div className="grid h-full place-items-center px-6 text-center">
        <div className="max-w-sm">
          <CheckCircle2 className="mx-auto size-10 text-success" />
          <p className="mt-3 text-lg font-semibold">Project delivered</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Every step is done. Head to Knowledge to capture what this project taught the team.
          </p>
        </div>
      </div>
    )
  }
  return (
    <div className="grid h-full place-items-center px-6 text-center">
      <div className="max-w-sm">
        {running ? (
          <>
            <Loader2 className="mx-auto size-8 animate-spin text-primary" />
            <p className="mt-3 text-base font-semibold">You’re all caught up</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {AGENTS[running.agent].name} is working on <span className="font-medium text-foreground">{running.name}</span>.
              Click any task on the left to see how it runs and what it draws on.
            </p>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {pendingCount > 0 ? 'Select a task that needs you on the left.' : playing ? 'Lining up the next step…' : 'Press Run to start.'}
          </p>
        )}
      </div>
    </div>
  )
}

export function TaskWorkbench() {
  const tasks = useSimStore((s) => s.tasks)
  const selectedTaskId = useSimStore((s) => s.selectedTaskId)
  const selectTask = useSimStore((s) => s.selectTask)
  const pending = pendingHumanTasks(tasks)

  // Focus: explicit selection → first pending human task → running task
  const running = TASKS.find((t) => tasks[t.id]?.status === 'running')
  const autoFocus = pending[0] ?? running ?? null
  const focusId = selectedTaskId ?? autoFocus?.id ?? null
  const focus = TASKS.find((t) => t.id === focusId) ?? null
  const focusAwaiting = focus && tasks[focus.id]?.status === 'awaiting_human'
  const nextPending = pending.find((t) => t.id !== focusId)

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Your workbench</p>
          <h2 className="text-base font-semibold tracking-tight">
            {focusAwaiting ? 'What needs you' : 'Task detail'}
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {selectedTaskId && pending.length > 0 && !focusAwaiting && (
            <Button size="sm" variant="outline" onClick={() => selectTask(null)}>
              What needs you
              <ArrowRight />
            </Button>
          )}
          {pending.length > 0 && (
            <span className="rounded-full bg-warning/15 px-2.5 py-0.5 text-[11px] font-medium text-foreground">
              {pending.length} need{pending.length === 1 ? 's' : ''} you
            </span>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        {focus ? (
          <>
            <TaskDetail key={focus.id} task={focus} />
            {focusAwaiting && nextPending && (
              <button
                type="button"
                onClick={() => selectTask(nextPending.id)}
                className="mt-5 inline-flex items-center gap-1.5 text-[12px] text-primary hover:underline"
              >
                Next: {nextPending.name}
                <ArrowUpRight className="size-3.5" />
              </button>
            )}
          </>
        ) : (
          <CalmHint pendingCount={pending.length} />
        )}
      </div>
    </div>
  )
}
