import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileUp,
  FolderOpen,
  Loader2,
  Paperclip,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react'
import { useSimStore, type BackendAssignment } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { FILE_CATEGORIES, INTERVIEW_ACCEPT, type FileCategory } from '../../lib/types'
import { Button } from '../ui/button'
import { AgentChip } from '../ui/primitives'
import { cn } from '../../lib/cn'

/** `assignment` is the FULL backend object (prompt/items + status/note). */
export function AssignmentCard({
  assignment,
  taskId,
}: {
  assignment: BackendAssignment
  taskId: string
}) {
  const task = TASKS.find((t) => t.id === taskId)
  const open = assignment.status === 'open'
  // S1 upload gates carry a Project-Folder category and require REAL parsed files.
  const isUploadGate = assignment.kind === 'upload' && !!assignment.category

  return (
    <article className={cn('rounded-xl border bg-card', open ? 'border-warning/50 shadow-sm' : 'border-border')}>
      <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-3.5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Step {taskId}{' '}
            {task && (
              <>
                · {assignment.kind === 'export' ? 'owner' : 'requested by'} <AgentChip agent={task.agent} />
              </>
            )}
          </p>
          <h3 className="mt-1 text-base font-semibold">{assignment.title}</h3>
        </div>
        {!open && assignment.submittedAtTick !== undefined && (
          <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
            <CheckCircle2 className="size-3" /> day {assignment.submittedAtTick}
          </span>
        )}
      </header>

      {isUploadGate ? (
        <UploadGateBody assignment={assignment} taskId={taskId} />
      ) : (
        <MockAssignmentBody assignment={assignment} taskId={taskId} />
      )}
    </article>
  )
}

/* ── Real upload gate (S1: SOW / materials / minutes) ────────────────────── */

function UploadGateBody({ assignment, taskId }: { assignment: BackendAssignment; taskId: string }) {
  const submitAssignment = useSimStore((s) => s.submitAssignment)
  const files = useSimStore((s) => s.files)
  const uploadFile = useSimStore((s) => s.uploadFile)
  const deleteFile = useSimStore((s) => s.deleteFile)
  const togglePanel = useSimStore((s) => s.togglePanel)

  const open = assignment.status === 'open'
  const category = assignment.category as FileCategory
  const catMeta = FILE_CATEGORIES.find((c) => c.id === category)
  const catFiles = files.filter((f) => f.category === category)
  const parsedCount = catFiles.filter((f) => f.parsed).length

  // Optional source-choice gate (e.g. 1.1a: industry template vs. upload own tree).
  const choiceOptions = assignment.choiceOptions ?? []
  const hasChoice = choiceOptions.length > 0
  const recommendedId = choiceOptions.find((o) => o.recommended)?.id ?? choiceOptions[0]?.id
  // The non-default branch is the one that requires an uploaded file.
  const uploadOptionId = choiceOptions.find((o) => o.id !== recommendedId)?.id
  const [choice, setChoice] = useState<string | undefined>(assignment.chosenSource ?? recommendedId)
  const factorCat = assignment.choiceUploadCategory as FileCategory | undefined
  const factorMeta = factorCat ? FILE_CATEGORIES.find((c) => c.id === factorCat) : undefined
  const factorFiles = factorCat ? files.filter((f) => f.category === factorCat) : []
  const needsFactorUpload = hasChoice && !!factorCat && choice === uploadOptionId
  const factorReady = factorFiles.some((f) => f.parsed)
  const canSubmit = parsedCount > 0 && (!needsFactorUpload || factorReady)

  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  async function uploadTo(cat: FileCategory, e: React.ChangeEvent<HTMLInputElement>) {
    const list = e.currentTarget.files
    if (!list || list.length === 0) return
    setBusy(true)
    try {
      for (const file of Array.from(list)) await uploadFile(cat, file)
    } finally {
      setBusy(false)
      e.currentTarget.value = ''
    }
  }

  return (
    <div className="space-y-4 px-5 py-4">
      <p className="text-sm leading-relaxed">{assignment.prompt}</p>

      {/* Source-choice gate (e.g. factor-tree origin: template vs. upload your own) */}
      {hasChoice && (
        <fieldset className="space-y-2">
          {assignment.choicePrompt && (
            <legend className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              {assignment.choicePrompt}
            </legend>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            {choiceOptions.map((o) => {
              const selected = choice === o.id
              return (
                <button
                  key={o.id}
                  type="button"
                  disabled={!open}
                  onClick={() => setChoice(o.id)}
                  className={cn(
                    'rounded-lg border px-3 py-2.5 text-left transition-colors',
                    selected ? 'border-primary bg-primary/5 ring-1 ring-primary/40' : 'border-border hover:border-primary/40',
                    !open && 'cursor-default opacity-80',
                  )}
                >
                  <span className="flex items-center gap-1.5 text-[13px] font-medium">
                    {selected && <CheckCircle2 className="size-3.5 text-primary" />}
                    {o.label}
                    {o.recommended && (
                      <span className="rounded-full bg-muted px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
                        recommended
                      </span>
                    )}
                  </span>
                  {o.detail && <span className="mt-0.5 block text-[11px] text-muted-foreground">{o.detail}</span>}
                </button>
              )
            })}
          </div>
        </fieldset>
      )}

      {open && (
        <label
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors',
            'border-border hover:border-primary/50 hover:bg-accent/40',
            busy && 'pointer-events-none opacity-60',
          )}
        >
          <input
            type="file"
            multiple
            accept={category === 'interview_minutes' ? INTERVIEW_ACCEPT : undefined}
            className="hidden"
            onChange={(e) => void uploadTo(category, e)}
            disabled={busy}
          />
          {busy ? <Loader2 className="size-5 animate-spin text-primary" /> : <UploadCloud className="size-5 text-primary" />}
          <span className="text-[13px] font-medium">
            {busy ? 'Uploading…' : `Click to upload to ${catMeta?.label ?? category}`}
          </span>
          {catMeta && <span className="text-[11px] text-muted-foreground">{catMeta.hint}</span>}
        </label>
      )}

      {/* Conditional second upload: your own factor-tree workbook */}
      {open && needsFactorUpload && factorCat && (
        <div className="space-y-1.5">
          <label
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors',
              factorReady ? 'border-success/50 bg-success/5' : 'border-warning/50 hover:border-primary/50 hover:bg-accent/40',
              busy && 'pointer-events-none opacity-60',
            )}
          >
            <input
              type="file"
              multiple
              accept=".xlsx,.xlsm"
              className="hidden"
              onChange={(e) => void uploadTo(factorCat, e)}
              disabled={busy}
            />
            <UploadCloud className="size-5 text-primary" />
            <span className="text-[13px] font-medium">
              {`Upload your factor tree to ${factorMeta?.label ?? factorCat}`}
            </span>
            <span className="text-[11px] text-muted-foreground">
              Columns: L1 · L2 · L3 · L4 · Indicator (.xlsx). AI supplements it from the industry template + your materials.
            </span>
          </label>
          {factorFiles.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-2.5 rounded-md border border-border bg-muted/40 px-3 py-2 text-[13px]"
            >
              <Paperclip className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{f.filename}</span>
              {f.parsed ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-success">
                  <CheckCircle2 className="size-3.5" /> parsed
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] text-warning" title={f.parseError ?? 'Could not parse this file'}>
                  <AlertTriangle className="size-3.5" /> not parsed
                </span>
              )}
              <button
                type="button"
                onClick={() => void deleteFile(f.id)}
                className="text-muted-foreground hover:text-destructive"
                aria-label={`Remove ${f.filename}`}
              >
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Real uploaded files in this category */}
      <div>
        <p className="mb-1.5 flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <span>{open ? 'Uploaded to Project Folder' : 'Provided'}</span>
          {open && (
            <button
              type="button"
              onClick={() => togglePanel('folder', true)}
              className="inline-flex items-center gap-1 normal-case tracking-normal text-primary hover:underline"
            >
              <FolderOpen className="size-3.5" /> Open Project Folder
            </button>
          )}
        </p>
        <div className="space-y-1.5">
          {catFiles.length === 0 && (
            <p className="rounded-md border border-dashed border-border px-3 py-3 text-[12px] text-muted-foreground">
              No files yet — upload your {catMeta?.label.toLowerCase() ?? 'files'} above. This deliverable is parsed
              only from your real materials.
            </p>
          )}
          {catFiles.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-2.5 rounded-md border border-border bg-muted/40 px-3 py-2 text-[13px]"
            >
              <Paperclip className="size-3.5 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{f.filename}</span>
              {f.parsed ? (
                <span className="inline-flex items-center gap-1 text-[11px] text-success">
                  <CheckCircle2 className="size-3.5" /> parsed
                </span>
              ) : (
                <span
                  className="inline-flex items-center gap-1 text-[11px] text-warning"
                  title={f.parseError ?? 'Could not parse this file'}
                >
                  <AlertTriangle className="size-3.5" /> not parsed
                </span>
              )}
              {open && (
                <button
                  type="button"
                  onClick={() => void deleteFile(f.id)}
                  className="text-muted-foreground hover:text-destructive"
                  aria-label={`Remove ${f.filename}`}
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
        {assignment.items.length > 0 && open && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            Example files: <span className="font-mono">{assignment.items.join(', ')}</span>
          </p>
        )}
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
              {needsFactorUpload && !factorReady
                ? 'Upload your factor-tree workbook to continue'
                : parsedCount > 0
                  ? `${parsedCount} file${parsedCount > 1 ? 's' : ''} ready`
                  : 'Upload at least one readable file to continue'}
            </span>
            <Button
              size="sm"
              disabled={!canSubmit}
              onClick={() => void submitAssignment(taskId, note, hasChoice ? choice : undefined)}
            >
              <FileUp />
              {assignment.submitLabel}
            </Button>
          </div>
        </div>
      ) : (
        assignment.note && (
          <p className="border-t border-border pt-3 text-[12px] text-muted-foreground">Note: {assignment.note}</p>
        )
      )}
    </div>
  )
}

/* ── Legacy / mock body (exports, and uploads without a folder category) ─── */

function MockAssignmentBody({ assignment, taskId }: { assignment: BackendAssignment; taskId: string }) {
  const submitAssignment = useSimStore((s) => s.submitAssignment)
  const open = assignment.status === 'open'
  const isExport = assignment.kind === 'export'
  const [done, setDone] = useState<string[]>([])
  const [note, setNote] = useState('')
  const allDone = done.length === assignment.items.length

  const actionLabel = isExport ? 'Download' : 'Attach'
  const ActionIcon = isExport ? Download : FileUp

  return (
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
            <Button size="sm" disabled={!allDone} onClick={() => void submitAssignment(taskId, note)}>
              <ActionIcon />
              {assignment.submitLabel}
            </Button>
          </div>
        </div>
      ) : (
        assignment.note && (
          <p className="border-t border-border pt-3 text-[12px] text-muted-foreground">Note: {assignment.note}</p>
        )
      )}
    </div>
  )
}
