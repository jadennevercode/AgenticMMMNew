import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, CircleDashed, Loader2, Upload } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import type { DataRequestSlot, DataSlotStatus } from '../../lib/types'
import { cn } from '../../lib/cn'

const STATUS: Record<DataSlotStatus, { label: string; cls: string }> = {
  pending: { label: '待上传', cls: 'bg-muted text-muted-foreground' },
  uploaded: { label: '待校验', cls: 'bg-sky-500/10 text-sky-700' },
  validated: { label: '已校验', cls: 'bg-emerald-600/10 text-emerald-700' },
  incomplete: { label: '缺指标', cls: 'bg-amber-500/10 text-amber-700' },
  error: { label: '解析失败', cls: 'bg-destructive/10 text-destructive' },
}

function SlotRow({ slot }: { slot: DataRequestSlot }) {
  const uploadToSlot = useSimStore((s) => s.uploadToSlot)
  const inputRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const badge = STATUS[slot.status]

  async function handleFile(file: File | undefined) {
    if (!file) return
    setBusy(true)
    try {
      await uploadToSlot(slot.l3, file)
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const icon =
    slot.status === 'validated' ? <CheckCircle2 className="size-3.5 text-emerald-600" />
    : slot.status === 'incomplete' || slot.status === 'error' ? <AlertTriangle className="size-3.5 text-amber-600" />
    : <CircleDashed className="size-3.5 text-muted-foreground" />

  return (
    <div className="rounded-md border border-border bg-background px-2.5 py-1.5">
      <div className="flex items-center gap-2">
        {icon}
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium" title={slot.l3}>{slot.l3}</p>
          <p className="text-[10px] text-muted-foreground">
            {slot.expectedL4s.length} L4 · {slot.coveredIndicators}/{slot.expectedIndicators} 指标
            {slot.filename ? ` · ${slot.filename}` : ''}
          </p>
        </div>
        <span className={cn('shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium', badge.cls)}>
          {slot.status === 'incomplete'
            ? `缺 ${slot.missingIndicators.length}`
            : badge.label}
        </span>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          title={slot.fileId ? '重新上传' : '上传该 L3 工作簿'}
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
        </button>
      </div>
      {slot.status === 'incomplete' && slot.missingIndicators.length > 0 && (
        <p className="mt-1 truncate text-[10px] text-amber-700" title={slot.missingIndicators.join('， ')}>
          缺：{slot.missingIndicators.slice(0, 4).join('， ')}
          {slot.missingIndicators.length > 4 ? ` …+${slot.missingIndicators.length - 4}` : ''}
        </p>
      )}
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xlsm,.csv"
        className="hidden"
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />
    </div>
  )
}

/** BU-derived data-collection checklist: one L3 workbook slot per Data Request. */
export function DataRequestChecklist() {
  const manifest = useSimStore((s) => s.dataManifest)
  const loadDataManifest = useSimStore((s) => s.loadDataManifest)

  useEffect(() => {
    void loadDataManifest()
  }, [loadDataManifest])

  if (!manifest) {
    return (
      <div className="flex items-center gap-2 py-2 text-[11px] text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" /> 载入数据收集清单…
      </div>
    )
  }
  if (manifest.total === 0) {
    return (
      <p className="py-2 text-[11px] text-muted-foreground">
        尚无 Data Request（先在 Business Understanding 生成因子树与数据需求）。
      </p>
    )
  }

  const pct = Math.round((manifest.validated / manifest.total) * 100)
  return (
    <section className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-semibold">数据收集清单 · 按 Data Request（L3）</h3>
        <span className="font-mono text-[10px] text-muted-foreground">{manifest.validated}/{manifest.total} 已校验</span>
      </div>
      <p className="text-[10px] text-muted-foreground">
        每个 L3 一个工作簿（sheet=L4、列=指标）；上传即对照因子树校验覆盖。粒度 {manifest.timeGranularity} · 维度 {manifest.scopeDims.join(' / ')}
      </p>
      <div className="h-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="space-y-1 pt-0.5">
        {manifest.slots.map((slot) => <SlotRow key={slot.l3} slot={slot} />)}
      </div>
    </section>
  )
}
