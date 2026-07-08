import { useEffect, useState, type CSSProperties, type ReactElement } from 'react'
import { createPortal } from 'react-dom'
import { ArrowRight, ChevronDown, ChevronRight, Download, Eye, FileText, Lock, Maximize2, Minimize2, Pencil, Send } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { ARTIFACT_MAP } from '../../lib/artifacts-data'
import { TASKS } from '../../lib/scenario'
import { STAGES } from '../../lib/profiles'
import { buildChain, drawsOn, feedsInto, deliverableState } from '../../lib/artifact-graph'
import { FORMAT_LABEL, bodyToMarkdown } from '../../lib/artifact-format'
import { exportArtifact, exportDataRequestZip } from '../../lib/export'
import { api } from '../../api/client'
import { DecisionCard } from '../decisions/DecisionCard'
import { AssignmentCard } from '../workbench/AssignmentCard'
import { Field, RunTimeline, Findings } from '../workbench/TaskTrace'
import { ArtifactCanvas } from './canvas/ArtifactCanvas'
import { ProfileEditor } from './ProfileEditor'
import { FactorTreeEditor } from './FactorTreeEditor'
import { QualityScorecardEditor } from './QualityScorecardEditor'
import { ClientQAEditor } from './ClientQAEditor'
import { AgentChip, TaskBadge, StatusPill, DeliverableBadge, SparkleIcon } from '../ui/primitives'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'
import { useMediaQuery, useResizablePane } from '../../hooks/useResizablePane'
import { taskNeed, type ArtifactInstance, type TaskBlueprint } from '../../lib/types'

function downloadArtifact(inst: ArtifactInstance) {
  // The Data Request exports as a ZIP of one .xlsx per L3 (one sheet per L4),
  // built by the backend from the factor tree — not a single workbook.
  if (inst.id === 'a-data-request') {
    const pid = useSimStore.getState().activeProjectId
    if (pid) {
      void exportDataRequestZip(api.dataRequestExportUrl(pid))
      return
    }
  }
  void exportArtifact(inst)
}

/** Chip for an upstream / downstream artifact; click navigates to it */
function ArtifactChip({ id, dir, onPick }: { id: string; dir: 'in' | 'out'; onPick: (id: string) => void }) {
  const artifacts = useSimStore((s) => s.artifacts)
  const bp = ARTIFACT_MAP.get(id)
  if (!bp) return null
  const produced = artifacts.some((a) => a.id === id)
  return (
    <button
      type="button"
      onClick={() => onPick(id)}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors',
        produced ? 'border-border bg-card hover:border-primary/40' : 'border-dashed border-border opacity-60 hover:opacity-100',
      )}
    >
      {dir === 'out' && <ArrowRight className="size-3 text-muted-foreground" />}
      <FileText className="size-3.5 text-muted-foreground" />
      <span className="font-medium">{bp.name}</span>
      {!produced && <span className="font-mono text-[10px] text-muted-foreground">pending</span>}
    </button>
  )
}

/** AI cognitive alternatives — AI picks one, human can switch (non-blocking) */
function AiOptionsCard({ task }: { task: TaskBlueprint }) {
  const set = task.aiOptions
  const status = useSimStore((s) => s.tasks[task.id]?.status) ?? 'pending'
  const choice = useSimStore((s) => (set ? s.aiChoices[set.id] : undefined))
  const chooseAiOption = useSimStore((s) => s.chooseAiOption)
  if (!set || status === 'pending' || status === 'ready') return null
  const running = status === 'running'
  const chosenId = choice?.chosenId ?? set.options.find((o) => o.recommended)?.id ?? set.options[0].id

  return (
    <div className="mt-3 rounded-lg border bg-card px-3 py-2.5 [border-color:rgba(45,212,191,0.4)]">
      <p className="flex items-center gap-1.5 text-[12px] font-semibold">
        <SparkleIcon className="size-3.5 ai-twinkle" />
        <span className="ai-gradient-text">AI weighed {set.options.length} approaches</span>
      </p>
      <p className="mt-0.5 text-[11px] text-muted-foreground">{set.prompt}</p>
      <div className="mt-2 space-y-1.5">
        {set.options.map((o) => {
          const picked = o.id === chosenId
          return (
            <button
              key={o.id}
              type="button"
              disabled={running}
              onClick={() => chooseAiOption(set.id, o.id)}
              className={cn(
                'flex w-full flex-col gap-0.5 rounded-md border px-2.5 py-1.5 text-left transition-colors',
                picked ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40',
                running && 'opacity-60',
              )}
            >
              <span className="flex items-center gap-2 text-[12.5px] font-medium">
                <span className={cn('grid size-3.5 shrink-0 place-items-center rounded-full border', picked ? 'border-primary' : 'border-muted-foreground/40')}>
                  {picked && <span className="size-1.5 rounded-full bg-primary" />}
                </span>
                {o.label}
                {o.recommended && (
                  <span className="rounded-full border border-border px-1.5 py-px font-mono text-[9px] uppercase tracking-wider text-muted-foreground">AI pick</span>
                )}
              </span>
              <span className="pl-5 text-[11px] text-muted-foreground">{o.rationale}</span>
              <span className="pl-5 text-[11px] text-muted-foreground/75">Trade-off: {o.tradeoff}</span>
            </button>
          )
        })}
      </div>
      {!running && <p className="mt-1.5 text-[10px] text-muted-foreground/70">AI applied its pick — switch anytime.</p>}
    </div>
  )
}

/** One process step in the recipe = a task + its trace, findings and inline action */
function BuildStep({ task, index, total }: { task: TaskBlueprint; index: number; total: number }) {
  const tasks = useSimStore((s) => s.tasks)
  const decisions = useSimStore((s) => s.decisions)
  const assignments = useSimStore((s) => s.assignments)
  const findingCount = useSimStore((s) => s.findings[task.id]?.length ?? 0)
  const rt = tasks[task.id]
  const status = rt?.status ?? 'pending'
  const need = taskNeed(task)
  const awaiting = status === 'awaiting_human'
  const started = status === 'running' || status === 'done' || awaiting
  const last = index === total - 1

  // Steps collapse once done/confirmed; the user can fold/unfold any step.
  const [override, setOverride] = useState<boolean | null>(null)
  const open = override ?? status !== 'done'

  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center">
        <span
          className={cn(
            'grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold',
            status === 'done' && 'border-success bg-success text-white',
            awaiting && 'border-warning text-warning',
            status === 'running' && 'border-primary text-primary',
            (status === 'pending' || status === 'ready') && 'border-border text-muted-foreground',
          )}
        >
          {index + 1}
        </span>
        {!last && <span className="mt-1 w-px flex-1 bg-border" style={{ minHeight: open ? 24 : 8 }} />}
      </div>

      <div className={cn('min-w-0 flex-1', !last && (open ? 'pb-5' : 'pb-2.5'))}>
        <button
          type="button"
          onClick={() => setOverride(!open)}
          className="flex w-full flex-wrap items-center justify-between gap-2 rounded-md text-left"
        >
          <div className="flex min-w-0 items-center gap-2">
            {open ? (
              <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
            )}
            <span className="font-mono text-[10px] text-muted-foreground">{task.id}</span>
            <span className="truncate text-[13px] font-medium">{task.name}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <TaskBadge task={task} />
            <StatusPill status={status} />
          </div>
        </button>

        {open && (
          <div className="pl-5">
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground/90">{task.how}</p>

            {awaiting && need === 'decision' && task.decision && decisions[task.decision.id] && (
              <div className="mt-3">
                <DecisionCard decision={decisions[task.decision.id]} taskId={task.id} />
              </div>
            )}
            {awaiting && need === 'input' && task.assignment && assignments[task.assignment.id] && (
              <div className="mt-3">
                <AssignmentCard assignment={assignments[task.assignment.id]} taskId={task.id} />
              </div>
            )}

            {task.aiOptions && <AiOptionsCard task={task} />}

            {started && (
              <div className="mt-3">
                <RunTimeline taskId={task.id} status={status} progress={rt?.progress ?? 0} />
              </div>
            )}

            {started && findingCount > 0 && (
              <div className="mt-2">
                <Findings taskId={task.id} />
              </div>
            )}

            {rt && rt.runs > 1 && (
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">Attempt {rt.runs} (sent back earlier)</p>
            )}
          </div>
        )}
      </div>
    </li>
  )
}

/** Process pane — how the deliverable is built */
function ProcessPane({ artifactId, onPick }: { artifactId: string; onPick: (id: string) => void }) {
  const tasks = useSimStore((s) => s.tasks)
  const artifacts = useSimStore((s) => s.artifacts)
  const inputs = drawsOn(artifactId)
  const outputs = feedsInto(artifactId)
  const chain = buildChain(artifactId)
  const state = deliverableState(artifactId, tasks, artifacts.find((a) => a.id === artifactId)?.state)

  return (
    <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5">
      <Field label="Draws on">
        {inputs.length ? (
          <div className="flex flex-wrap gap-1.5">
            {inputs.map((id) => <ArtifactChip key={id} id={id} dir="in" onPick={onPick} />)}
          </div>
        ) : (
          <p className="text-[12.5px] text-muted-foreground">Nothing — this is a starting point.</p>
        )}
      </Field>

      <Field label={state === 'locked' ? 'How it will be built' : 'Build process'}>
        {chain.length ? (
          <ol className="mt-0.5">
            {chain.map((t, i) => <BuildStep key={t.id} task={t} index={i} total={chain.length} />)}
          </ol>
        ) : (
          <p className="text-[12.5px] text-muted-foreground">—</p>
        )}
      </Field>

      {outputs.length > 0 && (
        <Field label="Feeds into">
          <div className="flex flex-wrap gap-1.5">
            {outputs.map((id) => <ArtifactChip key={id} id={id} dir="out" onPick={onPick} />)}
          </div>
        </Field>
      )}
    </div>
  )
}

/** Document / Edit segmented toggle — shared by the sidebar and the maximized overlay */
function CanvasModeToggle({
  inst,
  mode,
  setMode,
}: {
  inst: ArtifactInstance | undefined
  mode: 'document' | 'edit'
  setMode: (m: 'document' | 'edit') => void
}) {
  return (
    <div className="inline-flex rounded-md border border-border p-0.5">
      <button
        type="button"
        onClick={() => setMode('document')}
        className={cn('inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px]', mode === 'document' ? 'bg-accent font-medium' : 'text-muted-foreground')}
      >
        <Eye className="size-3" /> Document
      </button>
      <button
        type="button"
        disabled={!inst}
        onClick={() => setMode('edit')}
        className={cn('inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-[11px]', mode === 'edit' ? 'bg-accent font-medium' : 'text-muted-foreground', !inst && 'opacity-40')}
      >
        <Pencil className="size-3" /> Edit
      </button>
    </div>
  )
}

type DiffRow = { kind: 'add' | 'remove' | 'keep'; text: string }

/** Compact LCS line diff for the before/after preview card. */
function lineDiff(before: string, after: string): DiffRow[] {
  const a = before.split('\n')
  const b = after.split('\n')
  const m = a.length
  const n = b.length
  const lcs: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const rows: DiffRow[] = []
  let i = 0
  let j = 0
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      rows.push({ kind: 'keep', text: a[i] })
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      rows.push({ kind: 'remove', text: a[i] })
      i++
    } else {
      rows.push({ kind: 'add', text: b[j] })
      j++
    }
  }
  while (i < m) rows.push({ kind: 'remove', text: a[i++] })
  while (j < n) rows.push({ kind: 'add', text: b[j++] })
  return rows
}

/** Before/after preview of a pending chat edit, with Apply / Discard. */
function DiffPreview({ artifactId }: { artifactId: string }) {
  const inst = useSimStore((s) => s.artifacts.find((a) => a.id === artifactId))
  const proposal = useSimStore((s) => s.artifactProposals[artifactId])
  const apply = useSimStore((s) => s.applyArtifactProposal)
  const discard = useSimStore((s) => s.discardArtifactProposal)
  if (!proposal || !inst) return null
  const before = bodyToMarkdown(inst.format, inst.body, inst.content)
  const after = bodyToMarkdown(proposal.format, proposal.body ?? undefined, proposal.content ?? '')
  const rows = lineDiff(before, after).filter((r) => r.text.trim() !== '' || r.kind !== 'keep')
  const changed = rows.some((r) => r.kind !== 'keep')
  return (
    <div className="mr-6 rounded-lg border border-primary/40 bg-primary/[0.03]">
      <div className="flex items-center justify-between border-b border-primary/20 px-3 py-1.5">
        <span className="text-[11px] font-semibold text-primary">Proposed change · review before applying</span>
      </div>
      <div className="max-h-48 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-relaxed">
        {!changed && <p className="text-muted-foreground">No visible change in the rendered document.</p>}
        {rows.map((r, i) => (
          <div
            key={i}
            className={cn(
              'whitespace-pre-wrap break-words',
              r.kind === 'add' && 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
              r.kind === 'remove' && 'bg-rose-500/15 text-rose-700 line-through dark:text-rose-300',
              r.kind === 'keep' && 'text-muted-foreground/70',
            )}
          >
            <span className="select-none opacity-60">{r.kind === 'add' ? '+ ' : r.kind === 'remove' ? '− ' : '  '}</span>
            {r.text || ' '}
          </div>
        ))}
      </div>
      <div className="flex justify-end gap-2 border-t border-primary/20 px-3 py-2">
        <Button size="sm" variant="ghost" onClick={() => discard(artifactId)}>
          Discard
        </Button>
        <Button size="sm" onClick={() => void apply(artifactId)}>
          Apply change
        </Button>
      </div>
    </div>
  )
}

/** Chat to request edits; drafts a proposal, previews a diff, then applies. */
function EditChat({ artifactId, produced, layout = 'docked' }: { artifactId: string; produced: boolean; layout?: 'docked' | 'side' }) {
  const thread = useSimStore((s) => s.artifactChats[artifactId]) ?? []
  const send = useSimStore((s) => s.sendArtifactEdit)
  const drafting = useSimStore((s) => s.artifactDrafting === artifactId)
  const hasProposal = useSimStore((s) => Boolean(s.artifactProposals[artifactId]))
  const [text, setText] = useState('')
  const busy = drafting || hasProposal
  const submit = () => {
    if (!text.trim() || busy) return
    void send(artifactId, text.trim())
    setText('')
  }
  return (
    <div
      className={cn(
        'flex min-h-0 shrink-0 flex-col border-border',
        layout === 'side' ? 'h-full w-80 border-l' : 'h-64 border-t',
      )}
    >
      <div className="border-b border-border px-4 py-2">
        <p className="text-[12.5px] font-semibold">Chat</p>
        <p className="text-[11px] text-muted-foreground">Ask the AI to change this document — preview the diff, then apply</p>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {thread.length === 0 && (
          <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[12px] text-muted-foreground">
            {produced
              ? 'e.g. “加一条数据局限说明” or “把批发并入TT的理由写得更清楚”. Any language is fine.'
              : 'This deliverable isn’t produced yet — run its steps first, then edit it here.'}
          </p>
        )}
        {thread.map((m, i) => (
          <div
            key={i}
            className={cn(
              'rounded-lg px-3 py-2 text-[12.5px] leading-relaxed',
              m.role === 'user' ? 'ml-6 bg-primary text-primary-foreground' : 'mr-6 border border-border bg-muted/40 text-muted-foreground',
            )}
          >
            {m.text}
          </div>
        ))}
        {drafting && (
          <p className="mr-6 rounded-lg border border-border bg-muted/40 px-3 py-2 text-[12.5px] text-muted-foreground">
            Drafting a change…
          </p>
        )}
        {hasProposal && <DiffPreview artifactId={artifactId} />}
      </div>
      <div className="flex gap-2 border-t border-border px-4 py-2.5">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder={hasProposal ? 'Apply or discard the pending change first…' : 'Ask AI to change this…'}
          disabled={busy}
          className="min-w-0 flex-1 rounded-md border border-border bg-card px-3 py-1.5 text-[13px] outline-none placeholder:text-muted-foreground focus:border-primary/50 disabled:opacity-50"
        />
        <Button size="sm" onClick={submit} disabled={!text.trim() || busy}>
          <Send />
        </Button>
      </div>
    </div>
  )
}

/**
 * Bespoke structured editors that replace the generic grid in the canvas's
 * Edit mode. Other editable artifacts (interview, merged data request) fall
 * through to the generic editable renderer in ArtifactCanvas.
 */
const STRUCTURED_EDITORS: Record<string, () => ReactElement> = {
  'a-scope': () => <ProfileEditor />,
  'a-factor-tree': () => <FactorTreeEditor />,
  'a-quality-scorecard': () => <QualityScorecardEditor />,
  'a-client-qa': () => <ClientQAEditor />,
}

/** The canvas surface (document/edit renderer or placeholder) */
function CanvasSurface({ inst, mode }: { inst: ArtifactInstance | undefined; mode: 'document' | 'edit' }) {
  if (inst) {
    const Editor = mode === 'edit' ? STRUCTURED_EDITORS[inst.id] : undefined
    if (Editor) {
      return (
        <div className="min-h-0 flex-1 overflow-auto p-4">
          <Editor />
        </div>
      )
    }
    return <ArtifactCanvas inst={inst} editing={mode === 'edit'} />
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
      <div className="flex items-center gap-2 rounded-lg border border-dashed border-border px-4 py-6 text-[12.5px] text-muted-foreground">
        <Lock className="size-3.5" />
        Not produced yet — it appears here once its steps run. You can still ask about it in the chat.
      </div>
    </div>
  )
}

/** Full-screen focus overlay for the canvas */
function CanvasOverlay({
  inst,
  artifactId,
  mode,
  setMode,
  onClose,
}: {
  inst: ArtifactInstance | undefined
  artifactId: string
  mode: 'document' | 'edit'
  setMode: (m: 'document' | 'edit') => void
  onClose: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const name = ARTIFACT_MAP.get(artifactId)?.name ?? 'Canvas'
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex bg-foreground/30 p-[2.5%] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <span className="truncate text-sm font-semibold">Canvas · {name}</span>
            <CanvasModeToggle inst={inst} mode={mode} setMode={setMode} />
            {inst?.editedAtTick !== undefined && (
              <span className="font-mono text-[10px] text-muted-foreground">Edited · day {inst.editedAtTick}</span>
            )}
          </div>
          <Button size="sm" variant="outline" onClick={onClose}>
            <Minimize2 />
            Close
          </Button>
        </header>
        <div className="flex min-h-0 flex-1">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            <CanvasSurface inst={inst} mode={mode} />
          </div>
          <EditChat artifactId={artifactId} produced={!!inst} layout="side" />
        </div>
      </div>
    </div>,
    document.body,
  )
}

/** Canvas as a right sidebar — editable document on top, chat to modify it below */
function CanvasSidebar({
  inst,
  artifactId,
  style,
}: {
  inst: ArtifactInstance | undefined
  artifactId: string
  style?: CSSProperties
}) {
  const [mode, setMode] = useState<'document' | 'edit'>('document')
  const [maximized, setMaximized] = useState(false)

  return (
    <>
      <aside
        style={style}
        className="flex min-h-[560px] shrink-0 flex-col border-t border-border lg:min-h-0 lg:border-l lg:border-t-0"
      >
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="text-[12.5px] font-semibold">Canvas</span>
            <CanvasModeToggle inst={inst} mode={mode} setMode={setMode} />
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {inst?.editedAtTick !== undefined && (
              <span className="font-mono text-[10px] text-muted-foreground">Edited · day {inst.editedAtTick}</span>
            )}
            <button
              type="button"
              onClick={() => setMaximized(true)}
              aria-label="Maximize canvas"
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <Maximize2 className="size-3.5" />
            </button>
          </div>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <CanvasSurface inst={inst} mode={mode} />
        </div>

        <EditChat artifactId={artifactId} produced={!!inst} />
      </aside>

      {maximized && (
        <CanvasOverlay inst={inst} artifactId={artifactId} mode={mode} setMode={setMode} onClose={() => setMaximized(false)} />
      )}
    </>
  )
}

/**
 * Level 3 — one deliverable, laid out as Process (main) + Canvas (right sidebar):
 *  Process — what it draws on and the steps that build it (with inline actions)
 *  Canvas  — the editable document + a chat to request changes
 */
export function ArtifactDetail({ artifactId, onPick }: { artifactId: string; onPick: (id: string) => void }) {
  const tasks = useSimStore((s) => s.tasks)
  const artifacts = useSimStore((s) => s.artifacts)

  // Process | Canvas split: Canvas defaults to half the pane and is drag-resizable.
  // The divider only exists on the lg side-by-side layout (below lg the panes stack).
  const isWide = useMediaQuery('(min-width: 1024px)')
  const { containerRef, ratio, onHandleMouseDown, dragging } = useResizablePane({ initialRatio: 0.5 })

  const bp = ARTIFACT_MAP.get(artifactId)
  const inst = artifacts.find((a) => a.id === artifactId)
  const state = deliverableState(artifactId, tasks, inst?.state)
  if (!bp) return null

  const producer = buildChain(artifactId)[0] ?? TASKS.find((t) => t.id === bp.taskRef)
  // Every produced artifact is exportable (sheets -> .xlsx, others -> .md).
  const canExport = Boolean(inst)

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-3.5">
        <div className="min-w-0">
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            {STAGES[bp.stage].name}
            {producer && <> · <AgentChip agent={producer.agent} /></>}
          </p>
          <h2 className="mt-1 truncate text-lg font-semibold">{bp.name}</h2>
        </div>
        <div className="flex shrink-0 items-center gap-2.5">
          <span className="rounded-md border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{FORMAT_LABEL[bp.format]}</span>
          <DeliverableBadge state={state} />
          {canExport && inst && (
            <Button size="sm" variant="outline" onClick={() => downloadArtifact(inst)}>
              <Download />
              Export
            </Button>
          )}
        </div>
      </div>

      <div
        ref={containerRef}
        className={cn('flex min-h-0 flex-1 flex-col lg:flex-row', dragging && 'cursor-col-resize select-none')}
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <ProcessPane artifactId={artifactId} onPick={onPick} />
        </div>
        {isWide && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize canvas"
            onMouseDown={onHandleMouseDown}
            className="group relative w-1.5 shrink-0 cursor-col-resize touch-none"
          >
            <span
              className={cn(
                'absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-colors group-hover:bg-primary/50',
                dragging && 'bg-primary/60',
              )}
            />
          </div>
        )}
        <CanvasSidebar
          inst={inst}
          artifactId={artifactId}
          style={isWide ? { width: `${ratio * 100}%`, flex: '0 0 auto' } : undefined}
        />
      </div>
    </div>
  )
}
