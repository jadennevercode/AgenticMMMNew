import { CheckCircle2, Circle, Database, Plus, Target, XCircle } from 'lucide-react'
import type { StepKind, TransformPipeline } from '../../../lib/types'
import { cn } from '../../../lib/cn'
import { KIND_META } from './StepInspector'

/**
 * Sources and applied steps, in the order the data flows through them.
 *
 * This is the spine of the transform screen, the way the "Applied steps" rail is in
 * every mainstream data-prep tool: the pipeline reads top to bottom, selecting an
 * entry shows that stage of the data in the grid, and each entry says in plain
 * words what it does. The DAG view still exists for wiring branches — it is just no
 * longer the only way to understand the pipeline.
 */

export interface StepListProps {
  pipeline: TransformPipeline
  sources: string[]
  /** step id → 'success' | 'error', from the last dbt build. */
  statusByStep: Record<string, string>
  selected: string | null
  outputId: string
  onSelect: (id: string) => void
  onAdd: (kind: StepKind) => void
}

export function StepList({
  pipeline, sources, statusByStep, selected, outputId, onSelect, onAdd,
}: StepListProps) {
  return (
    <div className="flex min-h-0 flex-col">
      <Heading>Sources</Heading>
      <ul className="px-1.5">
        {sources.length === 0 && (
          <li className="px-2 py-2 text-[10px] text-muted-foreground">
            No raw tables yet — upload files in step 1.
          </li>
        )}
        {sources.map((table) => (
          <li key={table}>
            <Row
              active={selected === `source:${table}`}
              onClick={() => onSelect(`source:${table}`)}
              icon={<Database className="size-3 text-muted-foreground" />}
              title={table}
              subtitle="raw table"
            />
          </li>
        ))}
      </ul>

      <Heading>Applied steps</Heading>
      <ul className="min-h-0 flex-1 overflow-auto px-1.5 pb-2">
        {pipeline.steps.length === 0 && (
          <li className="px-2 py-2 text-[10px] leading-relaxed text-muted-foreground">
            No steps yet. Describe the shape you need and let the AI draft them, or add one below.
          </li>
        )}
        {pipeline.steps.map((step, i) => {
          const status = statusByStep[step.id]
          return (
            <li key={step.id}>
              <Row
                active={selected === step.id}
                onClick={() => onSelect(step.id)}
                icon={
                  status === 'success' ? <CheckCircle2 className="size-3 text-emerald-500" />
                    : status === 'error' ? <XCircle className="size-3 text-rose-500" />
                      : <Circle className="size-3 text-muted-foreground/40" />
                }
                index={i + 1}
                title={step.name || KIND_META[step.kind].label}
                subtitle={step.note || KIND_META[step.kind].hint}
                badge={step.id === outputId ? <Target className="size-3 text-primary" /> : null}
                kind={KIND_META[step.kind].label}
              />
            </li>
          )
        })}
      </ul>

      <div className="shrink-0 space-y-1 border-t border-border px-3 py-2">
        <span className="text-[9px] font-medium uppercase tracking-wide text-muted-foreground">Add step</span>
        <div className="flex flex-wrap gap-1">
          {(Object.keys(KIND_META) as StepKind[]).map((k) => (
            <button key={k} type="button" onClick={() => onAdd(k)}
              className="flex items-center gap-0.5 rounded-full border border-border px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:bg-primary/5 hover:text-primary">
              <Plus className="size-2.5" />{KIND_META[k].label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function Heading({ children }: { children: React.ReactNode }) {
  return (
    <p className="shrink-0 px-3 pb-1 pt-2.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground/70">
      {children}
    </p>
  )
}

interface RowProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  title: string
  subtitle: string
  index?: number
  badge?: React.ReactNode
  kind?: string
}

function Row({ active, onClick, icon, title, subtitle, index, badge, kind }: RowProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors',
        active ? 'bg-secondary' : 'hover:bg-accent/60',
      )}
    >
      <span className="mt-0.5 flex shrink-0 items-center gap-1">
        {index !== undefined && (
          <span className="w-3 text-right font-mono text-[9px] tabular-nums text-muted-foreground/60">{index}</span>
        )}
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className={cn('truncate text-[11px]', active ? 'font-semibold' : 'font-medium')}>{title}</span>
          {badge}
        </span>
        <span className="mt-0.5 flex items-baseline gap-1">
          {kind && (
            <span className="shrink-0 font-mono text-[9px] uppercase tracking-wide text-primary/70">{kind}</span>
          )}
          <span className="truncate text-[10px] text-muted-foreground">{subtitle}</span>
        </span>
      </span>
    </button>
  )
}
