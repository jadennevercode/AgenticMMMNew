import { AlertTriangle, Check, FileText } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { ARTIFACT_MAP } from '../../lib/artifacts-data'
import { cn } from '../../lib/cn'
import type { EvidenceRef, TaskStatus } from '../../lib/types'

/** Labelled block */
export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      {children}
    </div>
  )
}

/** Chips linking a conclusion to the source artifact it came from */
export function EvidenceChips({ evidence }: { evidence?: EvidenceRef[] }) {
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

/** Whether the backend has surfaced findings for a task (store-aware) */
export function hasFindings(taskId: string): boolean {
  return (useSimStore.getState().findings[taskId]?.length ?? 0) > 0
}

/**
 * Process trace — derived from the live event stream for this task. Each
 * activity event the backend logged against the task becomes a completed step;
 * the last one pulses while the task is still running.
 */
export function RunTimeline({ taskId, status, progress }: { taskId: string; status: TaskStatus; progress: number }) {
  void progress
  const events = useSimStore((s) => s.events)
  const steps = [...events].filter((e) => e.taskId === taskId).reverse()
  if (!steps.length) return null
  const n = steps.length
  const running = status === 'running'
  const activeIdx = running ? n - 1 : -1
  return (
    <ol className="space-y-0">
      {steps.map((step, i) => {
        const active = i === activeIdx
        const done = !active
        const last = i === n - 1
        return (
          <li key={step.id} className="flex gap-3">
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
              <p className="text-[12.5px] leading-tight">{step.message}</p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** Grounded findings — results tied to evidence (from /api/state) */
export function Findings({ taskId }: { taskId: string }) {
  const findings = useSimStore((s) => s.findings[taskId])
  if (!findings?.length) return null
  return (
    <div className="space-y-2">
      {findings.map((f, i) => {
        const flag = f.tone === 'flag'
        return (
          <div
            key={i}
            className={cn('rounded-md border px-3 py-2', flag ? 'border-warning/40 bg-warning/5' : 'border-border bg-card')}
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
