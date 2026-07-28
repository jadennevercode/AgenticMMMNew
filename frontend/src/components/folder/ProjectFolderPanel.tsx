import { useRef, useState } from 'react'
import { CheckCircle2, Download, FileText, Loader2, Mic, Trash2, Upload, AlertCircle } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { FILE_CATEGORIES, INTERVIEW_ACCEPT, type FileCategory, type ProjectFile } from '../../lib/types'
import { api } from '../../api/client'
import { cn } from '../../lib/cn'
import { DataRequestChecklist } from './DataRequestChecklist'

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function acceptFor(category: FileCategory): string | undefined {
  return category === 'interview_minutes' ? INTERVIEW_ACCEPT : undefined
}

/** Audio interview uploads show ASR transcription state instead of parse state. */
function AsrBadge({ file }: { file: ProjectFile }) {
  switch (file.asrStatus) {
    case 'pending':
      return <span className="inline-flex items-center gap-0.5 text-amber-600"><Mic className="size-2.5" /> audio · awaiting transcription</span>
    case 'transcribing':
      return <span className="inline-flex items-center gap-0.5 text-sky-600"><Loader2 className="size-2.5 animate-spin" /> transcribing…</span>
    case 'done':
      return <span className="inline-flex items-center gap-0.5 text-emerald-600"><CheckCircle2 className="size-2.5" /> transcribed</span>
    case 'error':
      return <span className="inline-flex items-center gap-0.5 text-destructive" title={file.asrError ?? ''}><AlertCircle className="size-2.5" /> ASR failed</span>
    default:
      return null
  }
}

function FileRow({ file }: { file: ProjectFile }) {
  const projectId = useSimStore((s) => s.activeProjectId)
  const deleteFile = useSimStore((s) => s.deleteFile)
  const isAudio = !!file.asrStatus
  return (
    <div className="group flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5">
      {isAudio ? <Mic className="size-3.5 shrink-0 text-muted-foreground" /> : <FileText className="size-3.5 shrink-0 text-muted-foreground" />}
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium" title={file.filename}>{file.filename}</p>
        <p className="flex items-center gap-1 text-[10px] text-muted-foreground">
          {formatSize(file.size)}
          {isAudio ? (
            <AsrBadge file={file} />
          ) : file.parsed ? (
            <span className="inline-flex items-center gap-0.5 text-emerald-600">
              <CheckCircle2 className="size-2.5" /> parsed · {file.parseChars.toLocaleString()} chars
            </span>
          ) : (
            <span className="inline-flex items-center gap-0.5 text-amber-600" title={file.parseError ?? ''}>
              <AlertCircle className="size-2.5" /> not parsed
            </span>
          )}
        </p>
      </div>
      {projectId && (
        <a
          href={api.fileDownloadUrl(projectId, file.id)}
          className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100"
          title="Download"
        >
          <Download className="size-3.5" />
        </a>
      )}
      <button
        type="button"
        onClick={() => void deleteFile(file.id)}
        className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
        title="Delete"
      >
        <Trash2 className="size-3.5" />
      </button>
    </div>
  )
}

function CategorySection({ category, files }: { category: (typeof FILE_CATEGORIES)[number]; files: ProjectFile[] }) {
  const uploadFile = useSimStore((s) => s.uploadFile)
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleFiles(list: FileList | null) {
    if (!list || !list.length) return
    setBusy(true)
    try {
      for (const file of Array.from(list)) {
        await uploadFile(category.id as FileCategory, file)
      }
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <section className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-semibold">{category.label}</h3>
        <span className="font-mono text-[10px] text-muted-foreground">{files.length}</span>
      </div>
      <p className="text-[10px] text-muted-foreground">{category.hint}</p>
      <div className="space-y-1">
        {files.map((f) => <FileRow key={f.id} file={f} />)}
      </div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void handleFiles(e.dataTransfer.files) }}
        className={cn(
          'flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed py-2 text-[11px] transition-colors',
          dragging ? 'border-primary bg-primary/5 text-primary' : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground',
        )}
      >
        {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
        {busy ? 'Uploading…' : 'Drop files or click to upload'}
      </button>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={acceptFor(category.id as FileCategory)}
        className="hidden"
        onChange={(e) => void handleFiles(e.target.files)}
      />
    </section>
  )
}

export function ProjectFolderPanel() {
  const files = useSimStore((s) => s.files)
  const filesLoading = useSimStore((s) => s.filesLoading)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <p className="mb-3 text-xs text-muted-foreground">
        Upload the project's source materials. The AI parses them to ground the Business Understanding deliverables.
      </p>
      {filesLoading && files.length === 0 ? (
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
          {FILE_CATEGORIES.map((cat) => {
            if (cat.id === 'data') {
              // BU-derived L3 checklist is the primary path; the generic drop
              // zone below it only holds raw/unslotted fallback files.
              const raw = files.filter((f) => f.category === 'data' && !f.slot)
              return (
                <div key={cat.id} className="space-y-2">
                  <DataRequestChecklist />
                  {raw.length > 0 && (
                    <CategorySection category={{ ...cat, label: '其它原始数据（未绑定 L3）' }} files={raw} />
                  )}
                </div>
              )
            }
            return (
              <CategorySection key={cat.id} category={cat} files={files.filter((f) => f.category === cat.id)} />
            )
          })}
        </div>
      )}
    </div>
  )
}
