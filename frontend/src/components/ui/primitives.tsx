import { useId, type ReactNode } from 'react'
import type { AgentId, ArtifactState, AutomationClass, DeliverableState, TaskBlueprint, TaskStatus } from '../../lib/types'
import { taskNeed } from '../../lib/types'
import { AGENTS, AGENT_COLOR } from '../../lib/profiles'
import { ARTIFACT_STATE_LABEL, CLASS_LABEL, DELIVERABLE_STATE, EXPORT_BADGE, INPUT_BADGE, STATUS_LABEL } from '../../lib/ui-language'
import { Badge } from './badge'
import { Tooltip } from './misc'
import { cn } from '../../lib/cn'

/** Gemini-style blue-green sparkle — marks AI-generated work */
export function SparkleIcon({ className }: { className?: string }) {
  const id = useId()
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn('ai-sparkle', className)}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="24" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="52%" stopColor="#2dd4bf" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
      </defs>
      <path
        d="M12 0C12 6.627 6.627 12 0 12c6.627 0 12 5.373 12 12 0-6.627 5.373-12 12-12-6.627 0-12-5.373-12-12z"
        fill={`url(#${id})`}
      />
    </svg>
  )
}

/** Behavior badge — how this step runs (never names the internal taxonomy) */
export function BehaviorBadge({ cls }: { cls: AutomationClass }) {
  const meta = CLASS_LABEL[cls]
  const Icon = meta.icon
  if (meta.ai) {
    return (
      <Tooltip content={meta.hint}>
        <Badge variant="outline" className="gap-1 font-medium [border-color:rgba(45,212,191,0.45)]">
          <SparkleIcon className="size-3.5 ai-twinkle" />
          <span className="ai-gradient-text">{meta.label}</span>
        </Badge>
      </Tooltip>
    )
  }
  return (
    <Tooltip content={meta.hint}>
      <Badge variant={cls === 'H' ? 'default' : 'outline'} className="font-normal">
        <Icon />
        {meta.label}
      </Badge>
    </Tooltip>
  )
}

/** Badge for a task — picks "Your input" / "Export & send" / "Your decision" / behavior */
export function TaskBadge({ task }: { task: TaskBlueprint }) {
  const need = taskNeed(task)
  if (need === 'input') {
    const meta = task.assignment?.kind === 'export' ? EXPORT_BADGE : INPUT_BADGE
    const Icon = meta.icon
    return (
      <Tooltip content={meta.hint}>
        <Badge variant="default" className="font-normal">
          <Icon />
          {meta.label}
        </Badge>
      </Tooltip>
    )
  }
  return <BehaviorBadge cls={task.class} />
}

export function AgentChip({ agent, showRole = false }: { agent: AgentId; showRole?: boolean }) {
  const profile = AGENTS[agent]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span aria-hidden className="inline-block size-2 rounded-[2px]" style={{ background: AGENT_COLOR[agent] }} />
      <span className="font-medium text-foreground">{profile.name}</span>
      {showRole && <span className="hidden text-muted-foreground lg:inline">· {profile.role}</span>}
    </span>
  )
}

export function StatusPill({ status }: { status: TaskStatus }) {
  const meta = STATUS_LABEL[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium" style={{ color: meta.color }}>
      <span
        aria-hidden
        className={cn(
          'inline-block size-1.5 rounded-full',
          status === 'running' && 'pulse-running',
          status === 'awaiting_human' && 'pulse-waiting',
        )}
        style={{ background: meta.color }}
      />
      {meta.label}
    </span>
  )
}

const STATE_VARIANT: Record<string, 'muted' | 'outline' | 'default' | 'secondary'> = {
  muted: 'muted',
  outline: 'outline',
  success: 'outline',
  locked: 'secondary',
}

export function AssetStateBadge({ state }: { state: ArtifactState }) {
  const meta = ARTIFACT_STATE_LABEL[state] ?? ARTIFACT_STATE_LABEL.draft
  return (
    <Badge
      variant={STATE_VARIANT[meta.variant]}
      className={cn('font-normal', meta.variant === 'success' && 'border-success/40 text-success')}
    >
      {meta.label}
    </Badge>
  )
}

/** Deliverable lifecycle on the artifact board */
export function DeliverableBadge({ state }: { state: DeliverableState }) {
  const meta = DELIVERABLE_STATE[state]
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium" style={{ color: meta.color }}>
      <span
        aria-hidden
        className={cn(
          'inline-block size-1.5 rounded-full',
          state === 'building' && 'pulse-running',
          state === 'needs-you' && 'pulse-waiting',
        )}
        style={{ background: meta.color }}
      />
      {meta.label}
    </span>
  )
}

export function SectionHeader({ kicker, title, right }: { kicker: string; title: string; right?: ReactNode }) {
  return (
    <header className="mb-5 flex items-end justify-between gap-4">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{kicker}</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">{title}</h2>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </header>
  )
}

/** Tiny markdown renderer (#/##/-/text) for asset previews */
export function MiniMarkdown({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <div className="space-y-1.5 text-[13px] leading-relaxed text-muted-foreground">
      {lines.map((line, i) => {
        if (line.startsWith('## ')) {
          return (
            <p key={i} className="pt-2 text-xs font-semibold uppercase tracking-wider text-foreground">
              {line.slice(3)}
            </p>
          )
        }
        if (line.startsWith('# ')) {
          return (
            <p key={i} className="text-base font-semibold text-foreground">
              {line.slice(2)}
            </p>
          )
        }
        if (line.startsWith('- ')) {
          return (
            <p key={i} className="flex gap-2">
              <span className="text-muted-foreground/60">—</span>
              <span>{line.slice(2)}</span>
            </p>
          )
        }
        if (!line.trim()) return null
        return <p key={i}>{line}</p>
      })}
    </div>
  )
}
