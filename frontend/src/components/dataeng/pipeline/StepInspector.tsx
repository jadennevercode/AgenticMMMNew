import { useEffect, useState } from 'react'
import { Check, Layers, Loader2, PanelRightClose, Plus, Sparkles, Trash2, X } from 'lucide-react'
import type {
  AggSpec, ClusterResult, ColumnValuesResult, EnumMapEntry, EnumSuggestion, FieldMapEntry,
  FieldMapSuggestion, InputColumnsResult, SqlSuggestion, StepKind, TransformStep, ValueCluster,
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
  /** Human label for an input token — step names beat generated step ids. */
  inputLabel: (input: string) => string
  /** Would wiring this input into this step close a loop? */
  wouldCycle: (input: string, stepId: string) => boolean
  isOutput: boolean
  targetColumns: string[]             // for enum target select
  previewColumns: string[]            // columns of the previewed output, for pickers
  onChange: (next: TransformStep) => void
  onDelete: () => void
  onMakeOutput: () => void
  onSuggestEnum: (field: string, targetColumn: string) => Promise<EnumSuggestion | null>
  /** AI-match this step's input columns onto the target schema. */
  onSuggestFieldMap: () => Promise<FieldMapSuggestion | null>
  /** Columns available at this step's input. */
  onInputColumns: () => Promise<InputColumnsResult>
  /** Draft this custom_sql step's body from plain English. */
  onSuggestSql: (instruction: string) => Promise<SqlSuggestion | null>
  onClusterEnum: (field: string) => Promise<ClusterResult | null>
  /** Distinct values of a column as they reach this step, most frequent first. */
  onColumnValues: (field: string) => Promise<ColumnValuesResult>
  onCollapse: () => void
}

const inputCls = 'w-full rounded-md border border-border bg-background px-2 py-1 text-[11px] outline-none focus:border-primary/60'
const cellCls = 'rounded border border-transparent bg-transparent px-1.5 py-0.5 text-[11px] outline-none hover:border-border focus:border-primary/60'

export function StepInspector(props: InspectorProps) {
  const { step, onChange } = props
  const meta = KIND_META[step.kind]
  const set = (patch: Partial<TransformStep>) => onChange({ ...step, ...patch })
  const [confirmDelete, setConfirmDelete] = useState(false)

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
          {/* Deleting rewires every downstream step, so it asks first. */}
          {confirmDelete ? (
            <>
              <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
              <Button size="sm" onClick={props.onDelete}>Delete step</Button>
            </>
          ) : (
            <Button size="icon" variant="ghost" onClick={() => setConfirmDelete(true)} aria-label="Delete step">
              <Trash2 className="size-3.5" />
            </Button>
          )}
          <Button size="icon" variant="ghost" onClick={props.onCollapse} aria-label="Hide step settings">
            <PanelRightClose className="size-3.5" />
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

        <InputPicker step={step} options={props.inputOptions} labelOf={props.inputLabel}
          wouldCycle={props.wouldCycle} set={set} />

        {step.kind === 'field_map' && (
          <FieldMapGrid step={step} set={set} targetColumns={props.targetColumns}
            onSuggest={props.onSuggestFieldMap} onInputColumns={props.onInputColumns} />
        )}
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
          <CustomSqlForm step={step} set={set} onSuggestSql={props.onSuggestSql} />
        )}
        <datalist id="target-columns">
          {props.targetColumns.map((c) => <option key={c} value={c} />)}
        </datalist>

        <p className="border-t border-border pt-2 text-[10px] leading-relaxed text-muted-foreground">
          Every edit re-runs the preview on the left against the real rows — no save or build needed.
        </p>
      </div>
    </div>
  )
}

/**
 * Which upstream feeds this step.
 *
 * Sources and steps are separated because they are different things to reason
 * about, steps show their name rather than their generated id, and a choice that
 * would close a loop is refused here exactly as the graph refuses the equivalent
 * drag — the two ways of wiring the same edge should not disagree.
 */
function InputPicker({ step, options, labelOf, wouldCycle, set }: {
  step: TransformStep
  options: string[]
  labelOf: (input: string) => string
  wouldCycle: (input: string, stepId: string) => boolean
  set: (p: Partial<TransformStep>) => void
}) {
  const sources = options.filter((o) => o.startsWith('source:'))
  const steps = options.filter((o) => !o.startsWith('source:'))
  const ordered = step.kind === 'join'
    ? step.inputs.map((i, n) => `${n === 0 ? 'left' : 'right'}: ${labelOf(i)}`)
    : []

  const chip = (opt: string) => {
    const on = step.inputs.includes(opt)
    const blocked = !on && wouldCycle(opt, step.id)
    return (
      <button key={opt} type="button" disabled={blocked}
        title={blocked ? 'That would make the pipeline feed itself' : labelOf(opt)}
        onClick={() => set({ inputs: on ? step.inputs.filter((i) => i !== opt) : [...step.inputs, opt] })}
        className={cn('max-w-full truncate rounded-full border px-2 py-0.5 text-[10px] transition-colors',
          on ? 'border-primary/50 bg-primary/10 text-primary'
            : blocked ? 'cursor-not-allowed border-dashed border-border text-muted-foreground/40'
              : 'border-border text-muted-foreground hover:bg-accent')}>
        {opt.startsWith('source:') ? `⬡ ${opt.slice(7)}` : labelOf(opt)}
      </button>
    )
  }

  return (
    <div className="space-y-1">
      <span className="text-[10px] font-medium text-muted-foreground">INPUTS</span>
      {step.inputs.length === 0 && step.kind !== 'custom_sql' && (
        <p className="rounded bg-amber-500/10 px-2 py-1 text-[10px] text-amber-700">
          Not connected — pick what feeds this step.
        </p>
      )}
      {sources.length > 0 && <div className="flex flex-wrap gap-1">{sources.map(chip)}</div>}
      {steps.length > 0 && <div className="flex flex-wrap gap-1">{steps.map(chip)}</div>}
      {step.kind === 'join' && step.inputs.length === 2 && (
        <p className="flex items-center gap-1 text-[10px] text-muted-foreground">
          {ordered.join(' · ')}
          <button type="button" onClick={() => set({ inputs: [...step.inputs].reverse() })}
            className="text-primary hover:underline">swap</button>
        </p>
      )}
    </div>
  )
}

// ── field map ────────────────────────────────────────────
const NEW_FIELD_ROW: FieldMapEntry = { source: '', target: '', cast: '', expr: '', by: 'human' }

/**
 * Rename and cast the input's columns onto the target schema.
 *
 * The input's real columns are listed up front: mapping them is the work, and it
 * cannot be done from memory of a spreadsheet. Unmapped ones are one click away
 * from becoming a row. AI matches apply directly rather than waiting behind a
 * confirmation gate — unlike an enum mapping, a wrong field map is loud, the
 * preview grid shows the wrong column at once — so they are simply marked.
 */
function FieldMapGrid({ step, set, onSuggest, onInputColumns }: {
  step: TransformStep
  set: (p: Partial<TransformStep>) => void
  onSuggest: () => Promise<FieldMapSuggestion | null>
  onInputColumns: () => Promise<InputColumnsResult>
  targetColumns: string[]
}) {
  const rows = step.fieldMap
  const [available, setAvailable] = useState<InputColumnsResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const patch = (i: number, p: Partial<FieldMapEntry>) =>
    set({ fieldMap: rows.map((r, idx) => (idx === i ? { ...r, ...p, by: 'human' as const } : r)) })

  const upstream = step.inputs[0] ?? ''
  useEffect(() => {
    if (!upstream) { setAvailable(null); return }
    let cancelled = false
    void onInputColumns().then((r) => { if (!cancelled) setAvailable(r) })
    return () => { cancelled = true }
  }, [upstream, onInputColumns])

  const mapped = new Set(rows.map((r) => r.source).filter(Boolean))
  const columns = available?.ok ? available.columns : []
  const unmapped = columns.filter((c) => !mapped.has(c))
  const aiRows = rows.filter((r) => r.by === 'ai').length

  async function suggest() {
    setBusy(true)
    setMessage('')
    try {
      const got = await onSuggest()
      if (!got) setMessage('AI suggestion failed — the backend did not respond.')
      else if (!got.ok) setMessage(got.error)
      else set({ fieldMap: got.entries })
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-medium text-muted-foreground">COLUMN MAPPINGS</span>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => void suggest()}
          disabled={busy || !upstream}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          AI suggest
        </Button>
      </div>

      {!upstream && (
        <p className="rounded bg-amber-500/10 px-2 py-1 text-[10px] text-amber-700">
          Connect an input to this step to see its columns.
        </p>
      )}
      {available && !available.ok && (
        <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700">{available.error}</p>
      )}
      {available?.ok && (
        <div className="space-y-1 rounded border border-border p-1.5">
          <p className="text-[10px] text-muted-foreground">
            <span className="font-medium text-foreground">{columns.length}</span> column(s) in the input ·{' '}
            {mapped.size} mapped
            {unmapped.length > 0 && <span className="text-amber-700"> · {unmapped.length} not mapped</span>}
          </p>
          <div className="flex flex-wrap gap-1">
            {columns.map((c) => {
              const on = mapped.has(c)
              return (
                <button key={c} type="button" disabled={on}
                  title={on ? 'Already mapped' : 'Add a mapping for this column'}
                  onClick={() => set({ fieldMap: [...rows, { ...NEW_FIELD_ROW, source: c, target: c }] })}
                  className={cn('rounded-full border px-1.5 py-0.5 font-mono text-[10px] transition-colors',
                    on ? 'border-transparent bg-secondary text-muted-foreground/60'
                      : 'border-dashed border-primary/40 text-primary/80 hover:bg-primary/10')}>
                  {on ? c : <>+ {c}</>}
                </button>
              )
            })}
          </div>
        </div>
      )}
      {message && <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700">{message}</p>}
      {aiRows > 0 && (
        <p className="text-[10px] text-muted-foreground">
          {aiRows} row(s) matched by AI — check them against the preview; editing one marks it yours.
        </p>
      )}

      <table className="w-full border-collapse text-[11px]">
        <thead className="text-left text-[10px] text-muted-foreground">
          <tr><th className="py-0.5 pr-1 font-medium">Source column</th><th className="px-1 font-medium">→ Target</th><th className="px-1 font-medium">Cast</th><th className="px-1 font-medium">Expr (optional)</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={cn(r.by === 'ai' && 'bg-primary/5')}>
              <td className="pr-1">
                <input className={cn(cellCls, 'w-full font-mono')} list="input-columns" value={r.source}
                  onChange={(e) => patch(i, { source: e.target.value })} />
              </td>
              <td className="px-1">
                <input className={cn(cellCls, 'w-full font-mono')} list="target-columns" value={r.target}
                  onChange={(e) => patch(i, { target: e.target.value })} />
              </td>
              <td className="px-1">
                <select className={cellCls} value={r.cast} onChange={(e) => patch(i, { cast: e.target.value })}>
                  {['', 'integer', 'double', 'date', 'text'].map((c) => <option key={c} value={c}>{c || 'keep'}</option>)}
                </select>
              </td>
              <td className="px-1"><input className={cn(cellCls, 'w-full font-mono')} value={r.expr} onChange={(e) => patch(i, { expr: e.target.value })} placeholder="'constant'" /></td>
              <td><button type="button" onClick={() => set({ fieldMap: rows.filter((_, idx) => idx !== i) })} className="text-muted-foreground hover:text-rose-600" aria-label={`Remove ${r.source || 'row'}`}><X className="size-3" /></button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <datalist id="input-columns">{columns.map((c) => <option key={c} value={c} />)}</datalist>
      <Button size="sm" variant="ghost" onClick={() => set({ fieldMap: [...rows, { ...NEW_FIELD_ROW }] })}>
        <Plus className="size-3" />Add mapping
      </Button>
    </div>
  )
}

// ── enum map ─────────────────────────────────────────────
/**
 * Standardise one column's values.
 *
 * The editor opens with **what is actually in the data**: picking a field loads
 * every distinct value reaching this step, with its row count, so the work is
 * visible before anything is mapped rather than starting from an empty table the
 * user has to populate from memory. The AI then fills what it is sure of and
 * leaves the rest as proposals — a proposal is pre-filled but does not compile,
 * so an uncertain guess can never silently rewrite the data.
 */
function EnumMapGrid(props: InspectorProps & { set: (p: Partial<TransformStep>) => void }) {
  const { step, set } = props
  const target = step.enumTarget || props.targetColumns[0] || ''
  const [busy, setBusy] = useState<'suggest' | 'cluster' | null>(null)
  const [clusters, setClusters] = useState<ClusterResult | null>(null)
  const [values, setValues] = useState<ColumnValuesResult | null>(null)
  const [message, setMessage] = useState('')
  const rows = step.enumMap
  const patch = (raw: string, p: Partial<EnumMapEntry>) =>
    set({
      enumMap: rows.map((r) => (r.raw === raw
        ? { ...r, ...p, by: 'human' as const, confidence: 1, status: 'accepted' as const } : r)),
    })
  const proposed = rows.filter((r) => r.status === 'proposed').length
  const accepted = rows.filter((r) => r.status === 'accepted' && r.canonical.trim()).length

  // Load the field's real values whenever the field (or what feeds it) changes.
  const field = step.enumField.trim()
  const upstream = step.inputs[0] ?? ''
  const { onColumnValues } = props
  useEffect(() => {
    if (!field || !upstream) { setValues(null); return }
    let cancelled = false
    void onColumnValues(field).then((r) => { if (!cancelled) setValues(r) })
    return () => { cancelled = true }
  }, [field, upstream, onColumnValues])

  const countByRaw = new Map(values?.values ?? [])
  // Every value in the data gets a row, mapped or not — an unmapped value is the
  // work still to do, not something to discover later from a failing build.
  const seen = new Set(rows.map((r) => r.raw))
  const missing = (values?.values ?? [])
    .filter(([v]) => !seen.has(v))
    .map(([v]): EnumMapEntry => ({ raw: v, canonical: '', confidence: 0, by: 'ai', status: 'proposed' }))
  const allRows = [...rows, ...missing]

  async function suggest() {
    if (!field) return
    setBusy('suggest')
    setMessage('')
    try {
      const got = await props.onSuggestEnum(field, target)
      if (!got) setMessage('AI suggestion failed — the backend did not respond.')
      else if (!got.ok) setMessage(got.error)
      else set({ enumMap: got.entries })
    } finally { setBusy(null) }
  }

  async function findClusters() {
    if (!field) return
    setBusy('cluster')
    setMessage('')
    try {
      const got = await props.onClusterEnum(field)
      if (!got) setMessage('Clustering failed — the backend did not respond.')
      else setClusters(got)
    } finally { setBusy(null) }
  }

  /** Accept one cluster: every spelling in it maps to the canonical value. */
  function applyCluster(group: ValueCluster, canonical: string) {
    const decided = new Map(allRows.map((r) => [r.raw, r]))
    for (const [raw] of group.values) {
      decided.set(raw, { raw, canonical, confidence: 1, by: 'human', status: 'accepted' })
    }
    set({ enumMap: [...decided.values()] })
    setClusters((c) => c && { ...c, clusters: c.clusters.filter((g) => g.key !== group.key) })
  }

  function acceptAllProposals() {
    set({
      enumMap: allRows.map((r) => (r.status === 'proposed' && r.canonical.trim()
        ? { ...r, status: 'accepted' as const } : r)),
    })
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
          FIELD TO STANDARDISE
          <input className={inputCls} list="preview-columns" value={step.enumField}
            onChange={(e) => { set({ enumField: e.target.value }); setClusters(null); setMessage('') }}
            placeholder="raw_channel" />
          <datalist id="preview-columns">
            {props.previewColumns.map((c) => <option key={c} value={c} />)}
          </datalist>
        </label>
        <label className="space-y-1 text-[10px] font-medium text-muted-foreground">
          STANDARD VALUES OF
          <select className={inputCls} value={target} onChange={(e) => set({ enumTarget: e.target.value })}>
            {props.targetColumns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>

      {field && !upstream && (
        <p className="rounded bg-amber-500/10 px-2 py-1 text-[10px] text-amber-700">
          Connect an input to this step to see the values in {field}.
        </p>
      )}
      {values && !values.ok && (
        <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700">{values.error}</p>
      )}
      {values?.ok && (
        <p className="text-[10px] text-muted-foreground">
          <span className="font-medium text-foreground">{values.values.length.toLocaleString()}</span> distinct
          value(s) in <span className="font-mono">{field}</span> · {accepted} mapped
          {proposed > 0 && <span className="text-amber-700"> · {proposed} awaiting confirmation</span>}
        </p>
      )}

      <div className="flex gap-2">
        <Button size="sm" variant="outline" className="flex-1" onClick={() => void suggest()}
          disabled={!!busy || !field || !upstream}>
          {busy === 'suggest' ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          AI suggest
        </Button>
        <Button size="sm" variant="outline" className="flex-1" onClick={() => void findClusters()}
          disabled={!!busy || !field || !upstream}>
          {busy === 'cluster' ? <Loader2 className="size-3.5 animate-spin" /> : <Layers className="size-3.5" />}
          Cluster similar
        </Button>
      </div>
      {message && <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700">{message}</p>}

      {clusters && <ClusterReview result={clusters} onApply={applyCluster}
        onDismiss={(g) => setClusters({ ...clusters, clusters: clusters.clusters.filter((x) => x.key !== g.key) })} />}

      {proposed > 0 && (
        <div className="flex items-center gap-2 rounded bg-amber-500/10 px-2 py-1">
          <p className="flex-1 text-[10px] font-medium text-amber-700">
            {proposed} proposal(s) need confirming — they do not reach the data until accepted.
          </p>
          <Button size="sm" variant="ghost" onClick={acceptAllProposals}>
            <Check className="size-3" />Accept all
          </Button>
        </div>
      )}

      <table className="w-full border-collapse text-[11px]">
        <thead className="text-left text-[10px] text-muted-foreground">
          <tr>
            <th className="py-0.5 pr-1 font-medium">Raw value</th>
            <th className="px-1 font-medium">→ Canonical</th>
            <th className="px-1 font-medium">Source</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {allRows.map((r) => {
            const n = countByRaw.get(r.raw)
            const pending = r.status === 'proposed'
            return (
              <tr key={r.raw} className={cn(pending && 'bg-amber-500/5', !r.canonical && 'text-muted-foreground')}>
                <td className="pr-1">
                  <input className={cn(cellCls, 'w-full font-mono')} value={r.raw}
                    onChange={(e) => patch(r.raw, { raw: e.target.value })} />
                  {n !== undefined && (
                    <span className="ml-1 tabular-nums text-[9px] text-muted-foreground">{n.toLocaleString()}</span>
                  )}
                </td>
                <td className="px-1">
                  <input className={cn(cellCls, 'w-full font-mono')} value={r.canonical}
                    placeholder="unmapped — passes through"
                    onChange={(e) => patch(r.raw, { canonical: e.target.value })} />
                </td>
                <td className="px-1 text-[10px] text-muted-foreground">
                  {r.by === 'ai' ? `AI ${(r.confidence * 100).toFixed(0)}%` : 'human'}
                </td>
                <td className="whitespace-nowrap">
                  {pending && r.canonical.trim() && (
                    <button type="button" onClick={() => patch(r.raw, {})}
                      className="text-emerald-600 hover:text-emerald-700" aria-label={`Confirm ${r.raw}`}>
                      <Check className="size-3" />
                    </button>
                  )}
                  <button type="button" onClick={() => set({ enumMap: rows.filter((x) => x.raw !== r.raw) })}
                    className="text-muted-foreground hover:text-rose-600" aria-label={`Remove ${r.raw}`}>
                    <X className="size-3" />
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <Button size="sm" variant="ghost"
        onClick={() => set({ enumMap: [...rows, { raw: '', canonical: '', confidence: 1, by: 'human', status: 'accepted' }] })}>
        <Plus className="size-3" />Add mapping
      </Button>
    </div>
  )
}

/**
 * Near-duplicate spellings, grouped into one decision each.
 *
 * The grouping is deterministic (key-collision fingerprints, computed over the rows
 * that actually reach this step) so the proposal is reproducible — but it is still a
 * proposal: nothing enters the mapping table until a group is accepted here.
 */
function ClusterReview({ result, onApply, onDismiss }: {
  result: ClusterResult
  onApply: (group: ValueCluster, canonical: string) => void
  onDismiss: (group: ValueCluster) => void
}) {
  const [edited, setEdited] = useState<Record<string, string>>({})
  if (!result.ok) {
    return (
      <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700">{result.error}</p>
    )
  }
  if (result.clusters.length === 0) {
    return (
      <p className="rounded bg-muted px-2 py-1 text-[10px] text-muted-foreground">
        No near-duplicate spellings among the {result.values.toLocaleString()} distinct values.
      </p>
    )
  }
  return (
    <div className="space-y-1.5 rounded-md border border-primary/30 bg-primary/5 p-2">
      <p className="text-[10px] font-medium text-primary">
        {result.clusters.length} group(s) of spellings look like the same value
      </p>
      {result.clusters.map((g) => {
        const canonical = edited[g.key] ?? g.suggestion
        return (
          <div key={g.key} className="rounded border border-border bg-background p-1.5">
            <div className="flex flex-wrap items-center gap-1">
              {g.values.map(([value, n]) => (
                <span key={value} className="rounded-full bg-secondary px-1.5 py-0.5 font-mono text-[9px]">
                  {value}<span className="ml-1 tabular-nums text-muted-foreground">{n.toLocaleString()}</span>
                </span>
              ))}
            </div>
            <div className="mt-1.5 flex items-center gap-1">
              <span className="text-[10px] text-muted-foreground">→</span>
              <input
                className={cn(cellCls, 'min-w-0 flex-1 border-border font-mono')}
                value={canonical}
                onChange={(e) => setEdited((m) => ({ ...m, [g.key]: e.target.value }))}
              />
              <Button size="sm" variant="ghost" onClick={() => onApply(g, canonical)} disabled={!canonical.trim()}>
                <Check className="size-3" />Accept
              </Button>
              <button type="button" onClick={() => onDismiss(g)}
                className="text-muted-foreground hover:text-rose-600" aria-label="Dismiss group">
                <X className="size-3" />
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── custom SQL ───────────────────────────────────────────
/**
 * The escape hatch, with a way in.
 *
 * Custom SQL exists for the shapes the typed steps cannot express, which is exactly
 * where a person is least likely to know the dialect. Describing the intent in
 * plain English is a way to start; the backend only returns SQL that actually ran
 * in the sandbox, and the previous version stays one click away.
 */
function CustomSqlForm({ step, set, onSuggestSql }: {
  step: TransformStep
  set: (p: Partial<TransformStep>) => void
  onSuggestSql: (instruction: string) => Promise<SqlSuggestion | null>
}) {
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [previous, setPrevious] = useState<string | null>(null)

  async function generate() {
    if (!instruction.trim() || busy) return
    setBusy(true)
    setMessage('')
    try {
      const got = await onSuggestSql(instruction.trim())
      if (!got) setMessage('Generation failed — the backend did not respond.')
      else if (!got.ok) setMessage(got.error)
      else {
        setPrevious(step.sql)
        set({ sql: got.sql, note: step.note || instruction.trim() })
        setMessage('')
      }
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-1.5">
      <span className="text-[10px] font-medium text-muted-foreground">
        DESCRIBE WHAT THIS STEP SHOULD DO
      </span>
      <div className="flex gap-1">
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void generate() }}
          placeholder="e.g. unpivot the month columns into month / value rows"
          className={cn(inputCls, 'flex-1')}
        />
        <Button size="sm" variant="outline" onClick={() => void generate()}
          disabled={busy || !instruction.trim()}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          Generate
        </Button>
      </div>
      {message && <p className="rounded bg-rose-500/10 px-2 py-1 text-[10px] text-rose-700">{message}</p>}
      {previous !== null && (
        <div className="flex items-center gap-2 rounded bg-primary/5 px-2 py-1">
          <p className="flex-1 text-[10px] text-primary">Generated — the preview on the left is already running it.</p>
          <Button size="sm" variant="ghost"
            onClick={() => { set({ sql: previous }); setPrevious(null) }}>
            Undo
          </Button>
        </div>
      )}
      <label className="block space-y-1 text-[10px] font-medium text-muted-foreground">
        SQL (inputs available as input_1, input_2, …)
        <textarea spellCheck={false} className={cn(inputCls, 'h-28 resize-y font-mono')}
          value={step.sql} onChange={(e) => { set({ sql: e.target.value }); setPrevious(null) }} />
      </label>
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
