import { useRef, useState } from 'react'
import {
  CheckCircle2, FileSpreadsheet, Loader2, RefreshCw, Rocket, Trash2, Upload,
} from 'lucide-react'
import type { CleaningSpec, DataAsset, DataAssetStatus } from '../../lib/types'
import { useSimStore } from '../../store/useSimStore'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'
import { cn } from '../../lib/cn'
import { ReviewPanel } from './ReviewPanel'
import { CleaningSpecEditor } from './CleaningSpecEditor'
import { SqlPanel } from './SqlPanel'

type Step = 'source' | 'review' | 'clean' | 'sql' | 'publish'
const STEPS: { id: Step; label: string }[] = [
  { id: 'source', label: '① 数据源' },
  { id: 'review', label: '② 快速 Review' },
  { id: 'clean', label: '③ 清洗要求' },
  { id: 'sql', label: '④ 生成 SQL' },
  { id: 'publish', label: '⑤ 发布资产' },
]

const STATUS_LABEL: Record<DataAssetStatus, string> = {
  raw: '原始', reviewed: '已体检', spec: '已定义清洗', cleaned: '已清洗', published: '已发布',
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
  const {
    reviewDataAsset, updateCleaningSpec, generateAssetSql, runAssetSql,
    publishDataAsset, uploadRawForAsset, deleteDataAsset,
  } = useSimStore.getState()
  const [step, setStep] = useState<Step>('source')
  const fileInput = useRef<HTMLInputElement>(null)
  const busy = busyId === asset.id

  const sourceFiles = files.filter((f) => asset.sourceFileIds.includes(f.id))
  const hasSource = sourceFiles.length > 0

  function onSpec(spec: CleaningSpec) {
    void updateCleaningSpec(asset.id, spec)
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
              <h3 className="text-sm font-semibold">原始数据源</h3>
              <p className="text-[11px] text-muted-foreground">
                上传客户交来的原始文件(.xlsx/.xlsm/.csv,非标准格式也可)。它们将作为该资产的清洗输入。
              </p>
              {sourceFiles.length > 0 ? (
                <div className="space-y-1">
                  {sourceFiles.map((f) => (
                    <div key={f.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-[12px]">
                      <FileSpreadsheet className="size-4 text-muted-foreground" />
                      <span className="truncate font-medium">{f.filename}</span>
                      <span className="ml-auto text-[11px] text-muted-foreground">
                        {f.parsed ? `✓ ${f.parseChars} chars` : `⚠ ${f.parseError ?? '解析失败'}`}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-[12px] text-muted-foreground">
                  还没有原始文件。
                </p>
              )}
              <input ref={fileInput} type="file" multiple accept=".xlsx,.xlsm,.csv" hidden onChange={onUpload} />
              <Button size="sm" variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
                {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}上传原始数据
              </Button>
            </Card>
            {hasSource && (
              <Button onClick={() => { void reviewDataAsset(asset.id); setStep('review') }} disabled={busy}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}运行快速 Review →
              </Button>
            )}
          </div>
        )}

        {step === 'review' && (
          <div className="space-y-4">
            <Button size="sm" variant="outline" onClick={() => void reviewDataAsset(asset.id)} disabled={busy || !hasSource}>
              {busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}重新 Review
            </Button>
            <ReviewPanel asset={asset} />
          </div>
        )}

        {step === 'clean' && <CleaningSpecEditor asset={asset} onChange={onSpec} />}

        {step === 'sql' && (
          <SqlPanel
            asset={asset}
            busy={busy}
            onGenerate={() => void generateAssetSql(asset.id)}
            onRun={(sql) => void runAssetSql(asset.id, sql)}
          />
        )}

        {step === 'publish' && (
          <div className="space-y-4">
            <Card className="space-y-3 p-4">
              <h3 className="text-sm font-semibold">发布为数据资产</h3>
              <p className="text-[11px] text-muted-foreground">
                发布会在沙箱中物化清洗 SQL 为 parquet,并注册一个新版本。已发布的资产会进入统一长表,
                供当前 project 工作流(S2–S5)直接调用。
              </p>
              {asset.sqlDraft?.status === 'ok' ? (
                <p className="flex items-center gap-1.5 text-[12px] text-emerald-700">
                  <CheckCircle2 className="size-4" />清洗 SQL 预览成功({asset.sqlDraft.rowCount.toLocaleString()} 行),可发布。
                </p>
              ) : (
                <p className="text-[12px] text-muted-foreground">先在“④ 生成 SQL”里运行预览成功后再发布。</p>
              )}
              <Button onClick={() => void publishDataAsset(asset.id)} disabled={busy || asset.sqlDraft?.status !== 'ok'}>
                {busy ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}发布资产
              </Button>
            </Card>

            {asset.versions.length > 0 && (
              <Card className="overflow-hidden p-0">
                <div className="border-b border-border px-4 py-2 text-sm font-semibold">版本历史</div>
                <table className="w-full border-collapse text-[12px]">
                  <thead className="bg-muted/60 text-left text-muted-foreground">
                    <tr>
                      <th className="px-3 py-1.5 font-medium">版本</th>
                      <th className="px-3 py-1.5 text-right font-medium">行数</th>
                      <th className="px-3 py-1.5 text-right font-medium">列数</th>
                      <th className="px-3 py-1.5 font-medium">时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...asset.versions].reverse().map((v) => (
                      <tr key={v.version} className="border-t border-border">
                        <td className="px-3 py-1.5">v{v.version}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{v.rowCount.toLocaleString()}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{v.columns.length}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{v.producedAt.replace('T', ' ').slice(0, 16)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
