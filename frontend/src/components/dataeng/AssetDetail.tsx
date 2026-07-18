import { useRef, useState } from 'react'
import {
  Download, Eye, FileSpreadsheet, Loader2, RefreshCw, Trash2, Upload,
} from 'lucide-react'
import type { DataAsset, DataAssetStatus, DbtPreview } from '../../lib/types'
import { api } from '../../api/client'
import { useSimStore } from '../../store/useSimStore'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'
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

const STATUS_LABEL: Record<DataAssetStatus, string> = {
  raw: 'Raw', reviewed: 'Reviewed', spec: 'Spec', cleaned: 'Cleaned', published: 'Published',
}
const STATUS_STYLE: Record<DataAssetStatus, string> = {
  raw: 'bg-muted text-muted-foreground',
  reviewed: 'bg-primary/10 text-primary',
  spec: 'bg-primary/10 text-primary',
  cleaned: 'bg-amber-500/15 text-amber-700',
  published: 'bg-emerald-500/15 text-emerald-700',
}

export function AssetDetail({ asset }: { asset: DataAsset }) {
  const files = useSimStore((s) => s.files)
  const busyId = useSimStore((s) => s.dataAssetBusy)
  const pid = useSimStore((s) => s.activeProjectId)
  const { reviewDataAsset, uploadRawForAsset, deleteDataAsset } = useSimStore.getState()
  const [step, setStep] = useState<Step>('source')
  const [rawPrev, setRawPrev] = useState<{ table: string; data: DbtPreview } | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const busy = busyId === asset.id

  const sourceFiles = files.filter((f) => asset.sourceFileIds.includes(f.id))
  const hasSource = sourceFiles.length > 0

  async function previewRaw(table: string) {
    if (!pid) return
    try {
      setRawPrev({ table, data: await api.rawPreview(pid, asset.id, table) })
    } catch { setRawPrev(null) }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const list = e.target.files
    if (!list) return
    for (const file of Array.from(list)) await uploadRawForAsset(asset.id, file)
    if (fileInput.current) fileInput.current.value = ''
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
        <Button size="icon" variant="ghost" onClick={() => void deleteDataAsset(asset.id)} aria-label="Delete asset">
          <Trash2 className="size-4" />
        </Button>
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

      <div className="min-h-0 flex-1 overflow-auto p-5">
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
                    const table = asset.rawTables.find((t) => t.fileId === f.id)?.name
                      ?? f.filename.replace(/\.[^.]+$/, '').replace(/[^0-9a-zA-Z_]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase()
                    return (
                      <div key={f.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-[12px]">
                        <FileSpreadsheet className="size-4 shrink-0 text-muted-foreground" />
                        <span className="truncate font-medium">{f.filename}</span>
                        <span className="text-[11px] text-muted-foreground">
                          {f.parsed ? '✓' : `⚠ ${f.parseError ?? 'parse failed'}`}
                        </span>
                        <span className="ml-auto flex shrink-0 gap-1">
                          <Button size="sm" variant="ghost" onClick={() => void previewRaw(table)}>
                            <Eye className="size-3.5" />Preview
                          </Button>
                          {pid && (
                            <a href={api.fileDownloadUrl(pid, f.id)} download
                              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground hover:bg-accent hover:text-foreground">
                              <Download className="size-3.5" />Download
                            </a>
                          )}
                        </span>
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
              <Card className="overflow-hidden p-0">
                <div className="flex items-center justify-between border-b border-border px-4 py-2">
                  <h4 className="text-[13px] font-semibold">Preview · <span className="font-mono text-primary">{rawPrev.table}</span></h4>
                  <span className="text-[11px] text-muted-foreground">{rawPrev.data.rowCount.toLocaleString()} rows</span>
                </div>
                <div className="max-h-72 overflow-auto">
                  <table className="w-full border-collapse text-[11px]">
                    <thead className="sticky top-0 bg-muted/80 text-left text-muted-foreground backdrop-blur">
                      <tr>{rawPrev.data.columns.map((c) => <th key={c} className="whitespace-nowrap px-3 py-1.5 font-medium">{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      {rawPrev.data.rows.map((row, ri) => (
                        <tr key={ri} className="border-t border-border">
                          {row.map((cell, ci) => <td key={ci} className="whitespace-nowrap px-3 py-1">{cell}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
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
