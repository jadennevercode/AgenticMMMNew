import { AlertTriangle, Clock } from 'lucide-react'
import type { DataAsset, FieldProfile } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { ReviewChartView } from '../project/charts/ReviewCharts'
import { cn } from '../../lib/cn'

function dtypeColor(dtype: string): string {
  if (dtype === 'datetime' || dtype === 'date') return 'text-primary'
  if (dtype === 'number' || dtype === 'integer') return 'text-emerald-600'
  if (dtype === 'empty') return 'text-muted-foreground'
  return 'text-foreground'
}

function FieldRow({ f }: { f: FieldProfile }) {
  return (
    <tr className="border-t border-border align-top">
      <td className="px-2 py-1.5 font-medium">{f.name}</td>
      <td className={cn('px-2 py-1.5 font-mono text-[11px] uppercase', dtypeColor(f.dtype))}>{f.dtype}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{(100 - f.nullRatio * 100).toFixed(0)}%</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{f.distinct}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{f.cv != null ? f.cv.toFixed(2) : '—'}</td>
      <td className="px-2 py-1.5 text-muted-foreground">
        {f.isTimeAxis && <Clock className="mr-1 inline size-3 text-primary" />}
        {f.note || (f.sampleValues.length ? f.sampleValues.slice(0, 3).join(' · ') : '')}
      </td>
    </tr>
  )
}

export function ReviewPanel({ asset }: { asset: DataAsset }) {
  const review = asset.review
  if (!review) {
    return (
      <Card className="p-6 text-center text-sm text-muted-foreground">
        还没有 Review。点击“运行快速 Review”对原始数据做体检(时间颗粒度 / 连续性 / 波动性 + 画图)。
      </Card>
    )
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
        <Badge>{review.rowCount.toLocaleString()} 行</Badge>
        <Badge>{review.columnCount} 字段</Badge>
        {review.timeField && <Badge>时间轴: {review.timeField} · {review.timeGranularity}</Badge>}
      </div>

      {review.warnings.length > 0 && (
        <Card className="space-y-1 border-warning/40 bg-warning/5 p-3">
          {review.warnings.map((w, i) => (
            <p key={i} className="flex items-start gap-1.5 text-[12px] text-foreground">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />{w}
            </p>
          ))}
        </Card>
      )}

      {review.charts.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {review.charts.map((chart) => (
            <Card key={chart.id} className="space-y-2 p-4">
              <h4 className="text-sm font-semibold">{chart.title}</h4>
              <ReviewChartView chart={chart} />
              {chart.interpretation && (
                <p className="text-[11px] text-muted-foreground">{chart.interpretation}</p>
              )}
            </Card>
          ))}
        </div>
      )}

      <Card className="overflow-hidden p-0">
        <div className="max-h-[24rem] overflow-auto">
          <table className="w-full border-collapse text-[12px]">
            <thead className="sticky top-0 bg-muted/60">
              <tr className="text-left text-muted-foreground">
                <th className="px-2 py-1.5 font-medium">字段</th>
                <th className="px-2 py-1.5 font-medium">类型</th>
                <th className="px-2 py-1.5 text-right font-medium">完整度</th>
                <th className="px-2 py-1.5 text-right font-medium">去重</th>
                <th className="px-2 py-1.5 text-right font-medium">CV</th>
                <th className="px-2 py-1.5 font-medium">备注 / 样本</th>
              </tr>
            </thead>
            <tbody>
              {review.fields.map((f) => <FieldRow key={`${f.table}.${f.name}`} f={f} />)}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
