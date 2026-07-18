import { useState } from 'react'
import { Loader2, Plus, Sparkles, Table2, Trash2, X } from 'lucide-react'
import type {
  AggSpec, DbtPreview, EnumMapEntry, FieldMapEntry, StepKind, TransformStep,
} from '../../../lib/types'
import { Button } from '../../ui/button'
import { cn } from '../../../lib/cn'

export const KIND_META: Record<StepKind, { label: string; hint: string }> = {
  field_map: { label: 'Field map', hint: 'Rename / cast source columns onto output columns' },
  enum_map: { label: 'Enum map', hint: 'Standardise raw values to canonical values' },
  join: { label: 'Join', hint: 'Attach lookup columns by key' },
  union: { label: 'Union', hint: 'Stack inputs with identical columns' },
  aggregate: { label: 'Aggregate', hint: 'Group and summarise' },
  filter: { label: 'Filter', hint: 'Keep rows matching a condition' },
  derive: { label: 'Derive', hint: 'Add computed columns' },
  custom_sql: { label: 'Custom SQL', hint: 'Escape hatch — full SELECT over inputs' },
}

export interface InspectorProps {
  step: TransformStep
  inputOptions: string[]              // all valid inputs: 'source:<t>' + other step ids
  isOutput: boolean
  targetColumns: string[]             // for enum target select
  onChange: (next: TransformStep) => void
  onDelete: () => void
  onMakeOutput: () => void
  onPreview: () => void
  preview: DbtPreview | null
  previewBusy: boolean
  onSuggestEnum: (field: string, targetColumn: string) => Promise<EnumMapEntry[] | null>
}

const inputCls = 'w-full rounded-md border border-border bg-background px-2 py-1 text-[11px] outline-none focus:border-primary/60'
const cellCls = 'rounded border border-transparent bg-transparent px-1.5 py-0.5 text-[11px] outline-none hover:border-border focus:border-primary/60'

export function StepInspector(props: InspectorProps) {
  const { step, onChange } = props
  const meta = KIND_META[step.kind]
  const set = (patch: Partial<TransformStep>) => onChange({ ...step, ...patch })

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide">{meta.label}</span>
            {props.isOutput && <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">output</span>}
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">{meta.hint}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          {!props.isOutput && (
            <Button size="sm" variant="ghost" onClick={props.onMakeOutput}>Set as output</Button>
          )}
          <Button size="icon" variant="ghost" onClick={props.onDelete} aria-label="Delete step">
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-auto p-3">
        {/* common fields */}
        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
            NAME
            <input className={inputCls} value={step.name} onChange={(e) => set({ name: e.target.value })} />
          </label>
          <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
            DESCRIPTION
            <input className={inputCls} value={step.note} onChange={(e) => set({ note: e.target.value })} placeholder="What this step does, in plain English" />
          </label>
        </div>

        <div className="space-y-1">
          <span className="text-[10px] font-medium text-muted-foreground">INPUTS</span>
          <div className="flex flex-wrap gap-1">
            {props.inputOptions.map((opt) => {
              const on = step.inputs.includes(opt)
              return (
                <button key={opt} type="button"
                  onClick={() => set({ inputs: on ? step.inputs.filter((i) => i !== opt) : [...step.inputs, opt] })}
                  className={cn('rounded-full border px-2 py-0.5 font-mono text-[10px] transition-colors',
                    on ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:bg-accent')}>
                  {opt.replace('source:', '⬡ ')}
                </button>
              )
            })}
          </div>
        </div>

        {step.kind === 'field_map' && <FieldMapGrid step={step} set={set} />}
        {step.kind === 'enum_map' && <EnumMapGrid {...props} set={set} />}
        {step.kind === 'join' && <JoinForm step={step} set={set} />}
        {step.kind === 'aggregate' && <AggregateForm step={step} set={set} />}
        {step.kind === 'filter' && (
          <label className="block space-y-1 text-[10px] font-medium text-muted-foreground">
            CONDITION (SQL boolean)
            <input className={inputCls} value={step.filterExpr} onChange={(e) => set({ filterExpr: e.target.value })} placeholder={'"value" > 0'} />
          </label>
        )}
        {step.kind === 'derive' && <DeriveForm step={step} set={set} />}
        {step.kind === 'custom_sql' && (
          <label className="block space-y-1 text-[10px] font-medium text-muted-foreground">
            SQL (inputs available as input_1, input_2, …)
            <textarea spellCheck={false} className={cn(inputCls, 'h-28 resize-y font-mono')} value={step.sql} onChange={(e) => set({ sql: e.target.value })} />
          </label>
        )}

        {/* preview */}
        <div>
          <Button size="sm" variant="outline" onClick={props.onPreview} disabled={props.previewBusy}>
            {props.previewBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Table2 className="size-3.5" />}
            Preview output
          </Button>
          {props.preview && (
            <div className="mt-2 overflow-hidden rounded-md border border-border">
              <div className="border-b border-border bg-muted/50 px-2 py-1 text-[10px] text-muted-foreground">
                {props.preview.rowCount.toLocaleString()} rows
              </div>
              <div className="max-h-44 overflow-auto">
                <table className="w-full border-collapse text-[10px]">
                  <thead className="sticky top-0 bg-muted/80 text-left text-muted-foreground backdrop-blur">
                    <tr>{props.preview.columns.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1 font-medium">{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {props.preview.rows.map((row, ri) => (
                      <tr key={ri} className="border-t border-border">
                        {row.map((cell, ci) => <td key={ci} className="whitespace-nowrap px-2 py-0.5 tabular-nums">{cell}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── field map ────────────────────────────────────────────
function FieldMapGrid({ step, set }: { step: TransformStep; set: (p: Partial<TransformStep>) => void }) {
  const rows = step.fieldMap
  const patch = (i: number, p: Partial<FieldMapEntry>) =>
    set({ fieldMap: rows.map((r, idx) => (idx === i ? { ...r, ...p } : r)) })
  return (
    <div className="space-y-1">
      <span className="text-[10px] font-medium text-muted-foreground">COLUMN MAPPINGS</span>
      <table className="w-full border-collapse text-[11px]">
        <thead className="text-left text-[10px] text-muted-foreground">
          <tr><th className="py-0.5 pr-1 font-medium">Source column</th><th className="px-1 font-medium">→ Target</th><th className="px-1 font-medium">Cast</th><th className="px-1 font-medium">Expr (optional)</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="pr-1"><input className={cn(cellCls, 'w-full font-mono')} value={r.source} onChange={(e) => patch(i, { source: e.target.value })} /></td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={r.target} onChange={(e) => patch(i, { target: e.target.value })} /></td>
              <td className="px-1">
                <select className={cellCls} value={r.cast} onChange={(e) => patch(i, { cast: e.target.value })}>
                  {['', 'integer', 'double', 'date', 'text'].map((c) => <option key={c} value={c}>{c || 'keep'}</option>)}
                </select>
              </td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={r.expr} onChange={(e) => patch(i, { expr: e.target.value })} placeholder="'constant'" /></td>
              <td><button type="button" onClick={() => set({ fieldMap: rows.filter((_, idx) => idx !== i) })} className="text-muted-foreground hover:text-rose-600"><X className="size-3" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" variant="ghost" onClick={() => set({ fieldMap: [...rows, { source: '', target: '', cast: '', expr: '' }] })}>
        <Plus className="size-3" />Add mapping
      </Button>
    </div>
  )
}

// ── enum map ─────────────────────────────────────────────
function EnumMapGrid(props: InspectorProps & { set: (p: Partial<TransformStep>) => void }) {
  const { step, set } = props
  const [target, setTarget] = useState(props.targetColumns[0] ?? '')
  const [busy, setBusy] = useState(false)
  const rows = step.enumMap
  const patch = (i: number, p: Partial<EnumMapEntry>) =>
    set({ enumMap: rows.map((r, idx) => (idx === i ? { ...r, ...p, by: 'human' as const } : r)) })
  const unmapped = rows.filter((r) => !r.canonical).length

  async function suggest() {
    if (!step.enumField) return
    setBusy(true)
    try {
      const got = await props.onSuggestEnum(step.enumField, target)
      if (got) set({ enumMap: got })
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-end gap-2">
        <label className="flex-1 space-y-1 text-[10px] font-medium text-muted-foreground">
          FIELD TO STANDARDISE
          <input className={inputCls} value={step.enumField} onChange={(e) => set({ enumField: e.target.value })} placeholder="raw_channel" />
        </label>
        <label className="flex-1 space-y-1 text-[10px] font-medium text-muted-foreground">
          STANDARD VALUES OF
          <select className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
            {props.targetColumns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <Button size="sm" variant="outline" onClick={() => void suggest()} disabled={busy || !step.enumField}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}Suggest
        </Button>
      </div>
      {unmapped > 0 && (
        <p className="rounded bg-amber-500/10 px-2 py-1 text-[10px] font-medium text-amber-700">
          {unmapped} value(s) unmapped — fill the canonical value or they pass through unchanged.
        </p>
      )}
      <table className="w-full border-collapse text-[11px]">
        <thead className="text-left text-[10px] text-muted-foreground">
          <tr><th className="py-0.5 pr-1 font-medium">Raw value</th><th className="px-1 font-medium">→ Canonical</th><th className="px-1 font-medium">Source</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={cn(!r.canonical && 'bg-amber-500/5')}>
              <td className="pr-1"><input className={cn(cellCls, 'w-full font-mono')} value={r.raw} onChange={(e) => patch(i, { raw: e.target.value })} /></td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={r.canonical} onChange={(e) => patch(i, { canonical: e.target.value })} /></td>
              <td className="px-1 text-[10px] text-muted-foreground">
                {r.by === 'ai' ? `AI ${(r.confidence * 100).toFixed(0)}%` : 'human'}
              </td>
              <td><button type="button" onClick={() => set({ enumMap: rows.filter((_, idx) => idx !== i) })} className="text-muted-foreground hover:text-rose-600"><X className="size-3" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" variant="ghost" onClick={() => set({ enumMap: [...rows, { raw: '', canonical: '', confidence: 1, by: 'human' }] })}>
        <Plus className="size-3" />Add mapping
      </Button>
    </div>
  )
}

// ── join ─────────────────────────────────────────────────
function JoinForm({ step, set }: { step: TransformStep; set: (p: Partial<TransformStep>) => void }) {
  const j = step.join ?? { how: 'left' as const, leftOn: [], rightOn: [], rightColumns: [] }
  const setJ = (p: Partial<typeof j>) => set({ join: { ...j, ...p } })
  const csv = (v: string[]) => v.join(', ')
  const parse = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)
  return (
    <div className="grid grid-cols-2 gap-2">
      <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
        JOIN TYPE
        <select className={inputCls} value={j.how} onChange={(e) => setJ({ how: e.target.value as 'left' | 'inner' })}>
          <option value="left">left</option><option value="inner">inner</option>
        </select>
      </label>
      <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
        RIGHT COLUMNS TO KEEP (comma-separated)
        <input className={inputCls} value={csv(j.rightColumns)} onChange={(e) => setJ({ rightColumns: parse(e.target.value) })} placeholder="price" />
      </label>
      <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
        LEFT KEYS
        <input className={inputCls} value={csv(j.leftOn)} onChange={(e) => setJ({ leftOn: parse(e.target.value) })} placeholder="channel" />
      </label>
      <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
        RIGHT KEYS
        <input className={inputCls} value={csv(j.rightOn)} onChange={(e) => setJ({ rightOn: parse(e.target.value) })} placeholder="channel" />
      </label>
      <p className="col-span-2 text-[10px] text-muted-foreground">First input = left side; second input = right side. All left columns pass through.</p>
    </div>
  )
}

// ── aggregate ────────────────────────────────────────────
function AggregateForm({ step, set }: { step: TransformStep; set: (p: Partial<TransformStep>) => void }) {
  const patch = (i: number, p: Partial<AggSpec>) =>
    set({ aggs: step.aggs.map((r, idx) => (idx === i ? { ...r, ...p } : r)) })
  return (
    <div className="space-y-2">
      <label className="block space-y-1 text-[10px] font-medium text-muted-foreground">
        GROUP BY (comma-separated)
        <input className={inputCls} value={step.groupBy.join(', ')}
          onChange={(e) => set({ groupBy: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} />
      </label>
      <span className="text-[10px] font-medium text-muted-foreground">AGGREGATIONS</span>
      <table className="w-full border-collapse text-[11px]">
        <tbody>
          {step.aggs.map((a, i) => (
            <tr key={i}>
              <td className="pr-1">
                <select className={cellCls} value={a.func} onChange={(e) => patch(i, { func: e.target.value as AggSpec['func'] })}>
                  {['sum', 'avg', 'min', 'max', 'count'].map((f) => <option key={f}>{f}</option>)}
                </select>
              </td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={a.column} onChange={(e) => patch(i, { column: e.target.value })} placeholder="column" /></td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={a.alias} onChange={(e) => patch(i, { alias: e.target.value })} placeholder="alias (optional)" /></td>
              <td><button type="button" onClick={() => set({ aggs: step.aggs.filter((_, idx) => idx !== i) })} className="text-muted-foreground hover:text-rose-600"><X className="size-3" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" variant="ghost" onClick={() => set({ aggs: [...step.aggs, { column: '', func: 'sum', alias: '' }] })}>
        <Plus className="size-3" />Add aggregation
      </Button>
    </div>
  )
}

// ── derive ───────────────────────────────────────────────
function DeriveForm({ step, set }: { step: TransformStep; set: (p: Partial<TransformStep>) => void }) {
  const patch = (i: number, p: Partial<{ name: string; expr: string }>) =>
    set({ derive: step.derive.map((r, idx) => (idx === i ? { ...r, ...p } : r)) })
  return (
    <div className="space-y-1">
      <span className="text-[10px] font-medium text-muted-foreground">COMPUTED COLUMNS</span>
      <table className="w-full border-collapse text-[11px]">
        <tbody>
          {step.derive.map((d, i) => (
            <tr key={i}>
              <td className="pr-1"><input className={cn(cellCls, 'w-32 font-mono')} value={d.name} onChange={(e) => patch(i, { name: e.target.value })} placeholder="name" /></td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={d.expr} onChange={(e) => patch(i, { expr: e.target.value })} placeholder="units * price" /></td>
              <td><button type="button" onClick={() => set({ derive: step.derive.filter((_, idx) => idx !== i) })} className="text-muted-foreground hover:text-rose-600"><X className="size-3" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <Button size="sm" variant="ghost" onClick={() => set({ derive: [...step.derive, { name: '', expr: '' }] })}>
        <Plus className="size-3" />Add column
      </Button>
    </div>
  )
}
