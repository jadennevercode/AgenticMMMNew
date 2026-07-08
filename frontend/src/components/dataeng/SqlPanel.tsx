import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, Play, Sparkles } from 'lucide-react'
import type { DataAsset } from '../../lib/types'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { Badge } from '../ui/badge'

interface Props {
  asset: DataAsset
  busy: boolean
  onGenerate: () => void
  onRun: (sql: string) => void
}

/** AI-drafted DuckDB cleaning SQL — editable, runnable in the sandbox, with a preview. */
export function SqlPanel({ asset, busy, onGenerate, onRun }: Props) {
  const draft = asset.sqlDraft ?? null
  const [sql, setSql] = useState(draft?.sql ?? '')

  // Keep the editor in sync when a new draft arrives (generate / run replaces it).
  useEffect(() => {
    setSql(asset.sqlDraft?.sql ?? '')
  }, [asset.sqlDraft?.sql])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">清洗 SQL · DuckDB</h3>
          <p className="text-[11px] text-muted-foreground">
            AI 依据字段画像与清洗要求生成单条 SELECT;可手动编辑后在沙箱中运行预览。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={onGenerate} disabled={busy}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
            AI 生成
          </Button>
          <Button size="sm" onClick={() => onRun(sql)} disabled={busy || !sql.trim()}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
            运行预览
          </Button>
        </div>
      </div>

      <textarea
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        spellCheck={false}
        placeholder="SELECT … FROM raw"
        className="h-56 w-full resize-y rounded-lg border border-border bg-card p-3 font-mono text-[12px] leading-relaxed outline-none focus:border-primary/60"
      />

      {draft && draft.status === 'error' && (
        <Card className="flex items-start gap-2 border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span className="font-mono">{draft.error}</span>
        </Card>
      )}

      {draft && draft.status === 'ok' && (
        <Card className="space-y-2 p-3">
          <div className="flex items-center gap-2 text-[12px]">
            <CheckCircle2 className="size-4 text-emerald-600" />
            <span className="font-medium text-foreground">预览成功</span>
            <Badge>{draft.rowCount.toLocaleString()} 行</Badge>
            <Badge>{draft.previewColumns.length} 列</Badge>
          </div>
          <div className="max-h-[20rem] overflow-auto rounded-md border border-border">
            <table className="w-full border-collapse text-[11px]">
              <thead className="sticky top-0 bg-muted/60">
                <tr className="text-left text-muted-foreground">
                  {draft.previewColumns.map((c) => (
                    <th key={c} className="whitespace-nowrap px-2 py-1.5 font-medium">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {draft.previewRows.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {row.map((cell, j) => (
                      <td key={j} className="whitespace-nowrap px-2 py-1 tabular-nums">{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-muted-foreground">
            预览仅展示前 {draft.previewRows.length} 行;发布时会物化全部 {draft.rowCount.toLocaleString()} 行为数据资产。
          </p>
        </Card>
      )}
    </div>
  )
}
