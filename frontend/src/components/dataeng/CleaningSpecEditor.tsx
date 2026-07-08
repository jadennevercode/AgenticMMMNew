import { useMemo, useState } from 'react'
import { Plus, Trash2, Wand2 } from 'lucide-react'
import type { CleaningSpec, CleaningTransform, DataAsset, FieldRule, NaPolicy } from '../../lib/types'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'

/** The 2.21 unified long-table columns a cleaning rule can target. */
export const TARGET_COLUMNS = [
  'task_name', 'brand', 'province_group', 'channel_type', 'channel', 'year', 'month',
  'source', 'l1', 'l2', 'l3', 'l4', 'l5', 'l6', 'l7', 'l8', 'metric_type', 'metric', 'value',
] as const

const TRANSFORMS: CleaningTransform[] = ['passthrough', 'mapping', 'transform', 'calc', 'hardcode', 'drop']
const NA_POLICIES: NaPolicy[] = ['keep', 'drop', 'zero', 'na']

function rid(): string {
  return `r-${Math.random().toString(36).slice(2, 9)}`
}

interface Props {
  asset: DataAsset
  onChange: (spec: CleaningSpec) => void
}

/** Vertical, field-by-field cleaning-requirements editor: one row per source field,
 *  mapped to a target 2.21 column with a transform + cleaning rule. */
export function CleaningSpecEditor({ asset, onChange }: Props) {
  const spec = asset.cleaningSpec ?? null
  const sourceFields = useMemo(() => {
    const fields = asset.review?.fields ?? []
    return fields.map((f) => f.name)
  }, [asset.review])

  const rows = useMemo(() => spec?.rules ?? [], [spec])
  const [seeded, setSeeded] = useState(false)

  function commit(next: FieldRule[]) {
    onChange({ rules: next, targetSchema: spec?.targetSchema ?? [], note: spec?.note ?? '' })
  }
  function patch(id: string, p: Partial<FieldRule>) {
    commit(rows.map((r) => (r.id === id ? { ...r, ...p } : r)))
  }
  function remove(id: string) {
    commit(rows.filter((r) => r.id !== id))
  }
  function add(sourceField = '') {
    commit([...rows, {
      id: rid(), sourceField, targetColumn: '', transform: 'passthrough',
      rule: '', naPolicy: 'keep', dtype: '', enabled: true,
    }])
  }
  /** Pre-fill one row per profiled source field (a starting point to edit down). */
  function seedFromFields() {
    const next: FieldRule[] = sourceFields.map((name) => ({
      id: rid(), sourceField: name, targetColumn: '', transform: 'passthrough',
      rule: '', naPolicy: 'keep', dtype: '', enabled: true,
    }))
    setSeeded(true)
    commit(next)
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">清洗要求 · 字段映射</h3>
          <p className="text-[11px] text-muted-foreground">
            纵向铺开每个源字段,指定它映射到统一长表的哪一列、如何变换与缺失处理。AI 据此生成 SQL。
          </p>
        </div>
        {rows.length === 0 && sourceFields.length > 0 && (
          <Button size="sm" variant="outline" onClick={seedFromFields} disabled={seeded}>
            <Wand2 className="size-3.5" />从字段画像生成
          </Button>
        )}
      </div>

      <div className="max-h-[26rem] overflow-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead className="sticky top-0 bg-muted/60">
            <tr className="text-left text-muted-foreground">
              <th className="w-40 px-2 py-1.5 font-medium">源字段</th>
              <th className="w-36 px-2 py-1.5 font-medium">目标列</th>
              <th className="w-28 px-2 py-1.5 font-medium">变换</th>
              <th className="px-2 py-1.5 font-medium">清洗规则 / 公式</th>
              <th className="w-20 px-2 py-1.5 font-medium">缺失</th>
              <th className="w-10 px-2 py-1.5 text-center font-medium" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={cn('border-t border-border align-top', !r.enabled && 'opacity-50')}>
                <td className="p-0">
                  <input
                    list={`sf-${asset.id}`}
                    value={r.sourceField}
                    onChange={(e) => patch(r.id, { sourceField: e.target.value })}
                    placeholder="(常量/合成)"
                    className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  />
                </td>
                <td className="p-0">
                  <select
                    value={r.targetColumn}
                    onChange={(e) => patch(r.id, { targetColumn: e.target.value })}
                    className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  >
                    <option value="">—</option>
                    {TARGET_COLUMNS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </td>
                <td className="p-0">
                  <select
                    value={r.transform}
                    onChange={(e) => patch(r.id, { transform: e.target.value as CleaningTransform })}
                    className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  >
                    {TRANSFORMS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td className="p-0">
                  <input
                    value={r.rule}
                    onChange={(e) => patch(r.id, { rule: e.target.value })}
                    placeholder="如 '2023-01' → 202301 / case when …"
                    className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  />
                </td>
                <td className="p-0">
                  <select
                    value={r.naPolicy}
                    onChange={(e) => patch(r.id, { naPolicy: e.target.value as NaPolicy })}
                    className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                  >
                    {NA_POLICIES.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </td>
                <td className="px-2 py-1 text-center">
                  <button type="button" onClick={() => remove(r.id)} className="rounded p-1 text-muted-foreground hover:text-destructive">
                    <Trash2 className="size-3" />
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-[12px] text-muted-foreground">
                还没有清洗规则 — 先运行快速 Review,再从字段画像生成,或手动添加。
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
      <datalist id={`sf-${asset.id}`}>
        {sourceFields.map((f) => <option key={f} value={f} />)}
      </datalist>
      <Button size="sm" variant="outline" onClick={() => add()}><Plus className="size-3.5" />添加字段规则</Button>
    </Card>
  )
}
