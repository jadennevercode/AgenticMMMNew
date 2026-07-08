import { useState } from 'react'
import { CheckCircle2, FileText } from 'lucide-react'
import { useSimStore, type BackendDecision } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { ARTIFACT_MAP } from '../../lib/artifacts-data'
import { Button } from '../ui/button'
import { AgentChip, AssetStateBadge } from '../ui/primitives'
import { cn } from '../../lib/cn'

function EvidenceChips({ decision }: { decision: BackendDecision }) {
  const artifacts = useSimStore((s) => s.artifacts)
  const selectAsset = useSimStore((s) => s.selectAsset)
  return (
    <div className="flex flex-wrap gap-2">
      {decision.evidence.map((ev) => {
        const inst = artifacts.find((a) => a.id === ev.artifactId)
        return (
          <button
            key={ev.artifactId}
            type="button"
            onClick={() => selectAsset(ev.artifactId)}
            className="group inline-flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-xs transition-colors hover:border-primary/40"
          >
            <FileText className="size-3.5 text-muted-foreground" />
            <span className="font-medium group-hover:underline">
              {inst?.name ?? ARTIFACT_MAP.get(ev.artifactId)?.name ?? ev.artifactId}
            </span>
            {inst && <AssetStateBadge state={inst.state} />}
            {ev.note && <span className="text-muted-foreground">· {ev.note}</span>}
          </button>
        )
      })}
    </div>
  )
}

/**
 * One decision card. `decision` is the FULL backend object (blueprint fields
 * + runtime status/resolution); `taskId` ties it to the producing step.
 */
export function DecisionCard({ decision, taskId }: { decision: BackendDecision; taskId: string }) {
  const resolveDecision = useSimStore((s) => s.resolveDecision)
  const task = TASKS.find((t) => t.id === taskId)
  const [choice, setChoice] = useState<string | null>(decision.options.find((o) => o.recommended)?.id ?? null)
  const [note, setNote] = useState('')
  const open = decision.status === 'open'
  const resolution = decision.resolution

  return (
    <article className={cn('rounded-xl border bg-card', open ? 'border-warning/50 shadow-sm' : 'border-border')}>
      <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-3.5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Step {taskId} {task && <>· <AgentChip agent={task.agent} /></>}
          </p>
          <h3 className="mt-1 text-base font-semibold">{decision.title}</h3>
        </div>
        {!open && resolution && (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
            <CheckCircle2 className="size-3" /> day {resolution.decidedAtTick}
          </span>
        )}
      </header>

      <div className="space-y-4 px-5 py-4">
        <p className="text-sm leading-relaxed">{decision.question}</p>

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Look at</p>
          <EvidenceChips decision={decision} />
        </div>

        <div className="rounded-lg border border-border bg-muted/40 px-3.5 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">AI recommendation</p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{decision.recommendation}</p>
        </div>

        <div className="space-y-2">
          {decision.options.map((opt) => {
            const picked = open ? choice === opt.id : resolution?.optionId === opt.id
            return (
              <label
                key={opt.id}
                className={cn(
                  'flex items-start gap-3 rounded-lg border px-3.5 py-2.5 transition-colors',
                  picked ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30',
                  open ? 'cursor-pointer' : 'cursor-default',
                )}
              >
                <input
                  type="radio"
                  name={decision.id}
                  checked={picked}
                  disabled={!open}
                  onChange={() => setChoice(opt.id)}
                  className="mt-1 accent-primary"
                />
                <span className="min-w-0">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    {opt.label}
                    {opt.recommended && (
                      <span className="rounded-full border border-border px-1.5 py-px font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
                        Recommended
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 block text-[12px] text-muted-foreground">{opt.detail}</span>
                  <span className="mt-0.5 block text-[11px] text-muted-foreground/80">Then: {opt.consequence}</span>
                </span>
              </label>
            )
          })}
        </div>

        {open ? (
          <div className="flex items-center gap-2 border-t border-border pt-3">
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add a note for the record (optional, any language)"
              className="min-w-0 flex-1 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none placeholder:text-muted-foreground focus:border-primary/50"
            />
            <Button size="sm" disabled={!choice} onClick={() => choice && void resolveDecision(decision.id, choice, note)}>
              Confirm choice
            </Button>
          </div>
        ) : (
          resolution?.note && (
            <p className="border-t border-border pt-3 text-[12px] text-muted-foreground">Note: {resolution.note}</p>
          )
        )}
      </div>
    </article>
  )
}
