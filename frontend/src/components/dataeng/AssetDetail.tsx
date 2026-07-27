import { useEffect, useRef, useState } from 'react'
import {
  Download, Eye, FileSpreadsheet, Loader2, RefreshCw, Trash2, Upload, X,
} from 'lucide-react'
import type {
  DataAsset, DataAssetStatus, DbtWorkspaceInfo, RawSourceTable, StepPreview,
} from '../../lib/types'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'
import { DataGrid } from './grid/DataGrid'
import { ReviewPanel } from './ReviewPanel'
import { TransformPanel } from './pipeline/TransformPanel'
import { PublishPanel } from './pipeline/PublishPanel'

type Step = 'source' | 'review' | 'workspace' | 'publish'
const STEPS: { id: Step; label: string }[] = [
  { id: 'source', label: '1 · Sources' },
  { id: 'review', label: '2 · Review' },
  { id: 'workspace', label: '3 · Transform' },
  { id: 'publish', label: '4 · Publish' },
]

const errorText = (e: unknown): string =>
  e instanceof Error ? e.message : 'Preview failed — the backend did not respond.'

const STATUS_LABEL: Record<DataAssetStatus, string> = {
  raw: 'Raw', reviewed: 'Reviewed', published: 'Published',
}
const STATUS_STYLE: Record<DataAssetStatus, string> = {
  raw: 'bg-muted text-muted-foreground',
  reviewed: 'bg-primary/10 text-primary',
  published: 'bg-emerald-500/15 text-emerald-700',
}

export function AssetDetail({ asset }: { asset: DataAsset }) {
  const files = useSimStore((s) => s.files)
  const busyId = useSimStore((s) => s.dataAssetBusy)
  const pid = useSimStore((s) => s.activeProjectId)
  const { reviewDataAsset, uploadRawForAsset, deleteDataAsset, updateDataAsset, dbtStatus } =
    useSimStore.getState()
  const [step, setStep] = useState<Step>('source')
  const [rawPrev, setRawPrev] = useState<{ table: string; data: StepPreview | null } | null>(null)
  const [info, setInfo] = useState<DbtWorkspaceInfo | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const busy = busyId === asset.id

  const sourceFiles = files.filter((f) => asset.sourceFileIds.includes(f.id))
  const hasSource = sourceFiles.length > 0

  // The tables a file actually yields are decided by the backend (a workbook can
  // hold several sheets, and non-ASCII names are given derived identifiers), so the
  // names are read from it rather than guessed from the filename here.
  useEffect(() => { void dbtStatus(asset.id).then(setInfo) }, [dbtStatus, asset.id, asset.updatedAt])
  const tablesByFile = new Map<string, RawSourceTable[]>()
  for (const t of info?.sourceTables ?? []) {
    tablesByFile.set(t.fileId, [...(tablesByFile.get(t.fileId) ?? []), t])
  }
  const issueByFile = new Map((info?.sourceIssues ?? []).map((i) => [i.fileId, i.reason]))

  async function previewRaw(table: string) {
    if (!pid) return
    setRawPrev({ table, data: null })
    try {
      // The same sandbox call the transform screen uses, so a raw table is profiled
      // exactly like a transformed one.
      setRawPrev({ table, data: await api.previewPipeline(pid, asset.id, null, `source:${table}`) })
    } catch (e) {
      setRawPrev({ table, data: { ok: false, error: errorText(e), columns: [], rows: [], rowCount: 0, stats: [] } })
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const list = e.target.files
    if (!list) return
    for (const file of Array.from(list)) await uploadRawForAsset(asset.id, file)
    if (fileInput.current) fileInput.current.value = ''
  }

  async function removeSource(fileId: string) {
    setRawPrev(null)
    await updateDataAsset(asset.id, {
      sourceFileIds: asset.sourceFileIds.filter((id) => id !== fileId),
    })
  }

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-base font-semibold">{asset.name}</h2>
            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', STATUS_STYLE[asset.status])}>
              {STATUS_LABEL[asset.status]}
            </span>
            {asset.latestVersion > 0 && <Badge>v{asset.latestVersion}</Badge>}
          </div>
          {asset.description && <p className="mt-0.5 truncate text-[12px] text-muted-foreground">{asset.description}</p>}
        </div>
        {/* Deleting an asset discards its pipeline, workspace and published versions,
            so it asks once rather than firing on a stray click of a bare icon. */}
        {confirmDelete ? (
          <div className="flex shrink-0 items-center gap-1">
            <span className="text-[11px] text-muted-foreground">Delete this asset?</span>
            <Button size="sm" variant="outline" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button size="sm" onClick={() => void deleteDataAsset(asset.id)}>
              <Trash2 className="size-3.5" />Delete
            </Button>
          </div>
        ) : (
          <Button size="icon" variant="ghost" onClick={() => setConfirmDelete(true)} aria-label="Delete asset">
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>

      {/* step nav */}
      <div className="flex shrink-0 gap-1 border-b border-border px-5 py-2">
        {STEPS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setStep(s.id)}
            className={cn(
              'rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors',
              step === s.id ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-accent',
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* The transform screen manages its own scrolling so the grid can fill the
          viewport; every other step is a normal scrolling document. */}
      <div className={cn('min-h-0 flex-1',
        step === 'workspace' ? 'flex overflow-hidden p-4' : 'overflow-auto p-5')}>
        {step === 'source' && (
          <div className="space-y-4">
            <Card className="space-y-3 p-4">
              <h3 className="text-sm font-semibold">Raw sources</h3>
              <p className="text-[11px] text-muted-foreground">
                Upload the client's raw files (.xlsx/.xlsm/.csv — non-standard shapes are fine). They become this asset's cleaning input.
              </p>
              {sourceFiles.length > 0 ? (
                <div className="space-y-1">
                  {sourceFiles.map((f) => {
                    const tables = tablesByFile.get(f.id) ?? []
                    const issue = issueByFile.get(f.id)
                    return (
                      <div key={f.id} className="rounded-md border border-border px-3 py-2 text-[12px]">
                        <div className="flex items-center gap-2">
                          <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                          <span className="truncate font-medium">{f.filename}</span>
                          <span className="ml-auto flex shrink-0 gap-1">
                            {pid && (
                              <a href={api.fileDownloadUrl(pid, f.id)} download
                                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground">
                                <Download className="size-3.5" />Download
                              </a>
                            )}
                            <Button size="sm" variant="ghost" onClick={() => void removeSource(f.id)}
                              disabled={busy} aria-label={`Remove ${f.filename}`}>
                              <X className="size-3.5" />Remove
                            </Button>
                          </span>
                        </div>
                        {issue ? (
                          <p className="mt-1 text-[11px] text-amber-700">⚠ {issue}</p>
                        ) : (
                          <div className="mt-1 flex flex-wrap items-center gap-1">
                            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                              {tables.length > 1 ? `${tables.length} tables` : 'table'}
                            </span>
                            {tables.length > 0 && (
                              <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                title="Every row from this file carries this in the `source` column, which the Data module filters on">
                                source: {tables.length > 1
                                  ? `${f.filename} › <sheet>`
                                  : tables[0].sourceLabel}
                              </span>
                            )}
                            {tables.map((t) => (
                              <button key={t.name} type="button" onClick={() => void previewRaw(t.name)}
                                title={`Rows from this table are tagged source = "${t.sourceLabel}"`}
                                className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 font-mono text-[10px] transition-colors hover:border-primary/50 hover:bg-primary/5 hover:text-primary">
                                <Eye className="size-3" />{t.name}
                                <span className="text-muted-foreground">{t.rowCount.toLocaleString()} rows</span>
                              </button>
                            ))}
                            {tables.length === 0 && (
                              <span className="text-[11px] text-muted-foreground">reading…</span>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-[12px] text-muted-foreground">
                  No raw files yet.
                </p>
              )}
              <input ref={fileInput} type="file" multiple accept=".xlsx,.xlsm,.csv" hidden onChange={onUpload} />
              <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}Upload raw data
              </Button>
            </Card>
            {rawPrev && (
              <section className="space-y-1.5">
                <h4 className="text-[13px] font-semibold">
                  Preview · <span className="font-mono text-primary">{rawPrev.table}</span>
                </h4>
                <DataGrid
                  className="h-80"
                  columns={rawPrev.data?.columns ?? []}
                  rows={rawPrev.data?.rows ?? []}
                  stats={rawPrev.data?.stats ?? []}
                  totalRows={rawPrev.data?.rowCount}
                  loading={rawPrev.data === null}
                  error={rawPrev.data && !rawPrev.data.ok ? rawPrev.data.error : ''}
                />
              </section>
            )}
            {hasSource && (
              <Button onClick={() => { void reviewDataAsset(asset.id); setStep('review') }} disabled={busy}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}Run review →
              </Button>
            )}
          </div>
        )}

        {step === 'review' && (
          <div className="space-y-4">
            <Button size="sm" variant="outline" onClick={() => void reviewDataAsset(asset.id)} disabled={busy || !hasSource}>
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}Re-run review
            </Button>
            <ReviewPanel asset={asset} />
          </div>
        )}

        {step === 'workspace' && <TransformPanel asset={asset} />}

        {step === 'publish' && <PublishPanel asset={asset} />}
      </div>
    </div>
  )
}
