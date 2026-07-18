import { AnomalyReviewPanel } from './AnomalyReviewPanel'
import { OlsStepPanel } from '../ols/OlsStepPanel'
import { QualityScorecardEditor } from '../QualityScorecardEditor'
import { StatScoreEditor } from '../StatScoreEditor'
import type { TaskPanelKind } from '../../../lib/types'

/**
 * The structured input a Process step renders inline (TaskDef.panel).
 *
 * A review step whose editor lives only on the canvas reads as "the AI decided,
 * go find the result somewhere else". Rendering the same editor *inside* the
 * step makes the human's turn part of the process rather than an afterthought —
 * so 2.2d and 2.4d review their scorecards here, exactly where 2.5 confirms its
 * Y / X / parameters.
 *
 * Editors mounted here must guard their drafts against the state poll (see
 * `useOlsDraft`): the store replaces these slices wholesale every tick.
 */
export function TaskStepPanel({ kind }: { kind: TaskPanelKind }) {
  switch (kind) {
    case 'ols-y':
    case 'ols-x':
    case 'ols-params':
      return <OlsStepPanel kind={kind} />
    case 'quality-review':
      return (
        <PanelFrame
          title="Data quality verdicts"
          hint="Accept the passes, drop the unusable, and decide each borderline metric. A drop here is inherited by every later layer — the indicator is not re-scored at 2.4, not offered at 2.5, and never reaches the master table."
        >
          <QualityScorecardEditor />
        </PanelFrame>
      )
    case 'stat-review':
      return (
        <PanelFrame
          title="Statistical verdicts"
          hint="Keep, review or drop each indicator on its CV / Pearson / VIF. Indicators already rejected at 2.2 or 2.3 are not scored here — that call is settled."
        >
          <StatScoreEditor />
        </PanelFrame>
      )
    case 'anomaly-review':
      return <AnomalyReviewPanel />  // brings its own frame + save action
    default:
      return null
  }
}

function PanelFrame({ title, hint, children }: {
  title: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <section className="mt-3 rounded-lg border border-border bg-card p-3">
      <header className="mb-2">
        <h4 className="text-[12.5px] font-semibold">{title}</h4>
        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{hint}</p>
      </header>
      <div className="max-h-[30rem] overflow-auto">{children}</div>
    </section>
  )
}
