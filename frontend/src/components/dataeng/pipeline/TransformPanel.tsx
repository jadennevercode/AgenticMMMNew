import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, Database, GitBranch, Loader2, PanelRightClose,
  PanelRightOpen, Play, RefreshCw, Save, Sparkles, Table2, XCircle,
} from 'lucide-react'
import type {
  ColumnValuesResult, DataAsset, DbtWorkspaceInfo, EnumSuggestion, FieldMapSuggestion,
  InputColumnsResult, SqlSuggestion, StepKind, TransformPipeline, TransformStep,
} from '../../../lib/types'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'
import { Card } from '../../ui/card'
import { Button } from '../../ui/button'
import { cn } from '../../../lib/cn'
import { DataGrid } from '../grid/DataGrid'
import { PipelineCanvas } from './PipelineCanvas'
import { StepList } from './StepList'
import { KIND_META, StepInspector } from './StepInspector'
import { usePipelinePreview } from './usePipelinePreview'

/**
 * The transform screen: sources and steps on the left, the data in the middle, the
 * selected step's configuration on the right.
 *
 * The data is the centre of the screen because that is the question being asked —
 * "what does this step do to my rows?" — and {@link usePipelinePreview} answers it
 * from the sandbox as you type, without saving or waiting on a dbt build. `dbt
 * build` stays the authoritative run: it is what validates the quality tests and
 * what Publish gates on.
 */

const FAIL = new Set(['error', 'fail', 'runtime error'])

const TEST_LABELS: { prefix: string; label: string }[] = [
  { prefix: 'time_span_min_years', label: 'Time span ≥ 2 years' },
  { prefix: 'time_granularity_allowed', label: 'Granularity: day / week / month' },
  { prefix: 'has_variation', label: 'Has variation' },
  { prefix: 'yoy_comparable', label: 'Year-over-year comparable' },
  { prefix: 'accepted_values', label: 'Values in allowed set' },
  { prefix: 'not_null', label: 'Not null' },
]
const testLabel = (name: string) => TEST_LABELS.find((t) => name.startsWith(t.prefix))?.label ?? name

const EMPTY_PIPE: TransformPipeline = { steps: [], outputStep: '', note: '' }

function newStep(kind: StepKind, n: number): TransformStep {
  return {
    id: `step_${Date.now().toString(36)}_${n}`, kind, name: KIND_META[kind].label.toLowerCase(),
    note: '', inputs: [], fieldMap: [], enumField: '', enumTarget: '', enumMap: [], join: null,
    groupBy: [], aggs: [], filterExpr: '', derive: [], sql: '',
  }
}

export function TransformPanel({ asset }: { asset: DataAsset }) {
  const pid = useSimStore((s) => s.activeProjectId)
  const busy = useSimStore((s) => s.dataAssetBusy) === asset.id
  const { dbtBuild, dbtGenerate, dbtStatus, putPipeline } = useSimStore.getState()

  const [info, setInfo] = useState<DbtWorkspaceInfo | null>(null)
  const [pipe, setPipe] = useState<TransformPipeline>(asset.pipeline ?? EMPTY_PIPE)
  const [dirty, setDirty] = useState(false)
  // Identity of the asset we're currently bound to, and a content-hash of the last
  // server pipeline we reconciled against. Used to avoid clobbering unsaved edits.
  const assetIdRef = useRef(asset.id)
  const syncedRef = useRef(JSON.stringify(asset.pipeline ?? EMPTY_PIPE))
  // Leaving the screen must not throw the work away. The pipeline is configuration —
  // saving it changes nothing downstream on its own (Build and Publish are separate
  // gates) — so an unsaved edit is flushed on the way out rather than lost silently.
  // Keyed on the asset we are *bound to*, not the incoming prop, so the flush on an
  // asset switch writes the outgoing pipeline to the asset it came from.
  const pendingRef = useRef({ assetId: asset.id, pipe: EMPTY_PIPE, dirty: false })
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<'table' | 'graph'>('table')
  // A wide result needs the room more than the form does; the inspector folds away.
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const [instruction, setInstruction] = useState('')
  const [targetCols, setTargetCols] = useState<string[]>([])
  const summary = asset.dbt ?? null

  const refresh = useCallback(async () => setInfo(await dbtStatus(asset.id)), [asset.id, dbtStatus])
  useEffect(() => { void refresh() }, [refresh, asset.updatedAt])
  // Mirrors the editable state for the unmount / asset-switch flush. Declared before
  // the reconcile effect so that on an asset change it still holds the outgoing
  // asset's work when the reconcile effect reads it.
  useEffect(() => {
    pendingRef.current = { assetId: assetIdRef.current, pipe, dirty }
  }, [pipe, dirty])
  useEffect(() => () => {
    const { assetId, pipe: last, dirty: unsaved } = pendingRef.current
    if (unsaved) void putPipeline(assetId, last)
  }, [putPipeline])
  // Reconcile the local (editable) pipeline with the server copy.
  //  - Switching to a different asset always adopts that asset's pipeline.
  //  - For the same asset, adopt a genuinely-changed server pipeline (after a
  //    save / build / publish) only when there are NO unsaved local edits.
  // Without the dirty guard, a background /api/state poll (which replaces the
  // whole dataAssets array every ~2s during a run) would wipe an in-progress
  // step or connection — the reason a freshly-added step "couldn't be wired".
  useEffect(() => {
    const server = asset.pipeline ?? EMPTY_PIPE
    const serverJson = JSON.stringify(server)
    if (assetIdRef.current !== asset.id) {
      // Flush the outgoing asset's unsaved edits before adopting the new one's.
      const prev = pendingRef.current
      if (prev.dirty && prev.assetId === assetIdRef.current) void putPipeline(prev.assetId, prev.pipe)
      assetIdRef.current = asset.id
      syncedRef.current = serverJson
      setPipe(server)
      setDirty(false)
      return
    }
    if (!dirty && serverJson !== syncedRef.current) {
      syncedRef.current = serverJson
      setPipe(server)
    }
  }, [asset.id, asset.pipeline, dirty, putPipeline])
  useEffect(() => {
    if (!pid) return
    void api.getTargetSchema(pid).then((cols) => setTargetCols(cols.map((c) => c.name)))
  }, [pid])

  useEffect(() => {
    const warn = (e: BeforeUnloadEvent) => { if (pendingRef.current.dirty) e.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [])

  const sources = useMemo(() => info?.sources ?? [], [info])
  const sourceTables = useMemo(() => info?.sourceTables ?? [], [info])
  const sourceIssues = useMemo(() => info?.sourceIssues ?? [], [info])
  // Unknown means unavailable: defaulting to true made a failed status call render
  // "engine ready" and offer a build that could not run.
  const available = info?.available ?? false
  const statusByStep = useMemo(() => {
    const byModel = new Map((summary?.nodes ?? []).map((n) => [n.name, n.status]))
    const out: Record<string, string> = {}
    for (const [stepId, model] of Object.entries(summary?.stepModels ?? {})) {
      const st = byModel.get(model)
      if (st) out[stepId] = FAIL.has(st) ? 'error' : 'success'
    }
    return out
  }, [summary])
  const tests = (summary?.nodes ?? []).filter((n) => n.resourceType === 'test')

  const outputId = pipe.outputStep || pipe.steps[pipe.steps.length - 1]?.id || ''
  // Always have something in the grid: fall back to the output step, then the first source.
  const activeId = useMemo(() => {
    const valid = selected
      && (selected.startsWith('source:')
        ? sources.includes(selected.slice(7))
        : pipe.steps.some((s) => s.id === selected))
    if (valid) return selected as string
    if (outputId) return outputId
    return sources.length ? `source:${sources[0]}` : ''
  }, [selected, sources, pipe.steps, outputId])
  const selectedStep = pipe.steps.find((s) => s.id === activeId) ?? null

  const preview = usePipelinePreview(asset.id, pipe, activeId)

  const inputOptions = useMemo(
    () => [...sources.map((s) => `source:${s}`),
           ...pipe.steps.filter((s) => s.id !== activeId).map((s) => s.id)],
    [sources, pipe.steps, activeId])
  const inputLabel = useCallback((input: string) => {
    if (input.startsWith('source:')) return input.slice(7)
    const s = pipe.steps.find((x) => x.id === input)
    return s ? (s.name || KIND_META[s.kind].label) : input
  }, [pipe.steps])
  // Same rule the canvas enforces on a drag, so wiring from the form and wiring on
  // the graph cannot disagree about what is a legal edge.
  const wouldCycle = useCallback((input: string, stepId: string) => {
    if (input.startsWith('source:')) return false
    if (input === stepId) return true
    const byId = new Map(pipe.steps.map((s) => [s.id, s]))
    const reaches = (from: string, target: string, seen = new Set<string>()): boolean => {
      const s = byId.get(from)
      if (!s) return false
      for (const i of s.inputs) {
        if (i === target) return true
        if (!seen.has(i)) { seen.add(i); if (reaches(i, target, seen)) return true }
      }
      return false
    }
    return reaches(input, stepId)
  }, [pipe.steps])

  // Edits compose off the latest pipeline, not the one captured at render: deleting
  // a node fires both a step delete and an edge delete in the same tick, and two
  // object-valued updates would have silently discarded the first.
  const mutate = useCallback((fn: (p: TransformPipeline) => TransformPipeline) => {
    setPipe(fn)
    setDirty(true)
  }, [])
  const patchStep = useCallback((next: TransformStep) =>
    mutate((p) => ({ ...p, steps: p.steps.map((s) => (s.id === next.id ? next : s)) })), [mutate])
  const deleteStep = useCallback((stepId: string) => {
    mutate((p) => ({
      ...p,
      steps: p.steps.filter((s) => s.id !== stepId)
        .map((s) => ({ ...s, inputs: s.inputs.filter((i) => i !== stepId) })),
      outputStep: p.outputStep === stepId ? '' : p.outputStep,
    }))
    setSelected((cur) => (cur === stepId ? null : cur))
  }, [mutate])

  async function save(): Promise<boolean> {
    if (!pid) return false
    const saved = await putPipeline(asset.id, pipe)
    if (!saved) return false
    // Record what we just persisted so the reconcile effect treats the store's
    // echoed-back copy as already-synced instead of reverting our own edits.
    syncedRef.current = JSON.stringify(saved)
    setPipe(saved)
    setDirty(false)
    return true
  }
  async function saveAndBuild() {
    if (await save()) { await dbtBuild(asset.id); await refresh() }
  }
  async function aiDraft() {
    if (dirty) await save()
    await dbtGenerate(asset.id, instruction.trim())
    setInstruction('')
    await refresh()
  }
  // The in-editor pipeline travels with each of these, so an unsaved rewiring is
  // reflected in what the AI sees and in the values the field lookup returns.
  const stepId = selectedStep?.id ?? ''
  const suggestEnum = useCallback(async (field: string, targetColumn: string): Promise<EnumSuggestion | null> => {
    if (!pid || !stepId) return null
    try { return await api.suggestEnumMap(pid, asset.id, pipe, stepId, field, targetColumn) } catch { return null }
  }, [pid, asset.id, pipe, stepId])
  const clusterEnum = useCallback(async (field: string) => {
    if (!pid || !stepId) return null
    try { return await api.clusterEnumValues(pid, asset.id, pipe, stepId, field) } catch { return null }
  }, [pid, asset.id, pipe, stepId])
  const suggestFieldMap = useCallback(async (): Promise<FieldMapSuggestion | null> => {
    if (!pid || !stepId) return null
    try { return await api.suggestFieldMap(pid, asset.id, pipe, stepId) } catch { return null }
  }, [pid, asset.id, pipe, stepId])
  const inputColumns = useCallback(async (): Promise<InputColumnsResult> => {
    if (!pid || !stepId) return { ok: false, error: 'No step selected.', columns: [] }
    try { return await api.inputColumns(pid, asset.id, pipe, stepId) }
    catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : 'Could not read the columns.', columns: [] }
    }
  }, [pid, asset.id, pipe, stepId])
  const suggestSql = useCallback(async (instruction: string): Promise<SqlSuggestion | null> => {
    if (!pid || !stepId) return null
    try { return await api.suggestSql(pid, asset.id, pipe, stepId, instruction) } catch { return null }
  }, [pid, asset.id, pipe, stepId])
  const columnValues = useCallback(async (field: string): Promise<ColumnValuesResult> => {
    if (!pid || !stepId) return { ok: false, error: 'No step selected.', values: [] }
    try { return await api.columnValues(pid, asset.id, pipe, stepId, field) }
    catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : 'Could not read the values.', values: [] }
    }
  }, [pid, asset.id, pipe, stepId])

  function addStep(kind: StepKind) {
    const s = newStep(kind, pipe.steps.length + 1)
    // Wire a new step to whatever is on screen, so it previews immediately instead
    // of landing disconnected and erroring until the user finds the input picker.
    const upstream = activeId && activeId !== s.id ? [activeId] : []
    mutate((p) => ({
      ...p, steps: [...p.steps, { ...s, inputs: upstream }],
      outputStep: p.outputStep || s.id,
    }))
    setSelected(s.id)
    setView('table')
  }

  const gridTitle = activeId.startsWith('source:')
    ? activeId.slice(7)
    : selectedStep ? (selectedStep.name || KIND_META[selectedStep.kind].label) : 'output'

  return (
    <div className="flex min-h-0 w-full flex-col gap-3">
      {/* ── toolbar: AI + save + build ── */}
      <Card className="flex shrink-0 flex-wrap items-center gap-2 p-2.5">
        <div className={cn('flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-medium',
          available ? 'bg-emerald-500/10 text-emerald-700' : 'bg-rose-500/10 text-rose-700')}>
          <Database className="size-3" />{available ? (info?.message ?? 'engine ready') : 'engine unavailable'}
        </div>
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void aiDraft() }}
          placeholder={pipe.steps.length === 0
            ? 'Describe the shape you need, e.g. "standardise channels, join the price list, sum to channel × month"'
            : 'Ask the AI to adjust the pipeline, e.g. "split e-commerce vs modern trade"'}
          className="min-w-48 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-[12px] outline-none transition-colors focus:border-primary/60"
        />
        <Button size="sm" onClick={() => void aiDraft()} disabled={busy || !available}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
          {pipe.steps.length === 0 ? 'AI draft' : 'AI adjust'}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void save()} disabled={!dirty || busy}>
          <Save className="size-3.5" />{dirty ? 'Save' : 'Saved'}
        </Button>
        <Button size="sm" variant="outline" onClick={() => void saveAndBuild()}
          disabled={busy || !available || pipe.steps.length === 0}>
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}Build & test
        </Button>
      </Card>

      {sourceIssues.length > 0 && (
        <Card className="flex shrink-0 items-start gap-2 border-amber-500/30 bg-amber-500/5 p-2.5 text-[11px]">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
          <div className="min-w-0">
            <p className="font-medium text-amber-800">
              {sourceIssues.length} uploaded file{sourceIssues.length > 1 ? 's' : ''} produced no table
            </p>
            <ul className="mt-0.5 space-y-0.5 text-muted-foreground">
              {sourceIssues.map((i) => (
                <li key={i.fileId} className="truncate">
                  <span className="font-mono">{i.filename || i.fileId}</span> — {i.reason}
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {/* ── steps · data · configuration ── */}
      <div className={cn('grid min-h-0 flex-1 gap-3',
        inspectorOpen ? 'xl:grid-cols-[11.5rem_minmax(0,1fr)_21rem]'
          : 'xl:grid-cols-[11.5rem_minmax(0,1fr)_2.25rem]')}>
        <Card className="min-h-0 overflow-hidden p-0 max-xl:max-h-64">
          <StepList
            pipeline={pipe} sources={sources} sourceTables={sourceTables}
            sourceIssueCount={sourceIssues.length} statusByStep={statusByStep}
            selected={activeId} outputId={outputId}
            onSelect={(id) => setSelected(id)} onAdd={addStep}
          />
        </Card>

        <div className="flex min-h-0 min-w-0 flex-col gap-2">
          <div className="flex shrink-0 items-center gap-2">
            <h4 className="min-w-0 truncate text-[12px] font-semibold">
              {view === 'table' ? <>Preview · <span className="font-mono text-primary">{gridTitle}</span></> : 'Pipeline graph'}
            </h4>
            {dirty && (
              <span className="shrink-0 whitespace-nowrap rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                unsaved edits
              </span>
            )}
            <div className="ml-auto flex shrink-0 items-center gap-1">
              {view === 'table' && (
                <Button size="icon" variant="ghost" onClick={preview.refresh} aria-label="Re-run preview">
                  <RefreshCw className={cn('size-3.5', preview.loading && 'animate-spin')} />
                </Button>
              )}
              <div className="flex rounded-md border border-border p-0.5">
                {([['table', Table2, 'Table'], ['graph', GitBranch, 'Graph']] as const).map(([id, Icon, label]) => (
                  <button key={id} type="button" onClick={() => setView(id)}
                    className={cn('flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium transition-colors',
                      view === id ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground')}>
                    <Icon className="size-3" />{label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {view === 'table' ? (
            <DataGrid
              className="min-h-64 flex-1"
              columns={preview.data?.columns ?? []}
              rows={preview.data?.rows ?? []}
              stats={preview.data?.stats ?? []}
              totalRows={preview.data?.rowCount}
              loading={preview.loading}
              error={preview.data && !preview.data.ok ? preview.data.error : ''}
              emptyMessage={sources.length === 0
                ? (sourceIssues.length > 0
                  ? 'None of the uploaded files could be read — see the note above.'
                  : 'Upload raw files in step 1 — the preview reads them directly.')
                : 'Select a source or step to see its data.'}
            />
          ) : (
            <div className="min-h-64 flex-1 overflow-hidden rounded-lg border border-border">
              <PipelineCanvas
                pipeline={pipe} sources={sources} statusByStep={statusByStep}
                selected={activeId} onSelect={(id) => setSelected(id)}
                onConnect={(src, tgt) => mutate((p) => ({
                  ...p,
                  steps: p.steps.map((s) => (s.id === tgt && !s.inputs.includes(src)
                    ? { ...s, inputs: [...s.inputs, src] } : s)),
                }))}
                onDisconnect={(src, tgt) => mutate((p) => ({
                  ...p,
                  steps: p.steps.map((s) => (s.id === tgt
                    ? { ...s, inputs: s.inputs.filter((i) => i !== src) } : s)),
                }))}
                onDeleteStep={deleteStep}
              />
            </div>
          )}

          <BuildStatus summary={summary} tests={tests} />
        </div>

        {!inspectorOpen ? (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card py-2 max-xl:flex-row max-xl:justify-center">
            <Button size="icon" variant="ghost" onClick={() => setInspectorOpen(true)} aria-label="Show step settings">
              <PanelRightOpen className="size-4" />
            </Button>
            <span className="text-[9px] font-medium uppercase tracking-wider text-muted-foreground xl:[writing-mode:vertical-rl]">
              settings
            </span>
          </div>
        ) : (
        <Card className="min-h-0 overflow-hidden p-0 max-xl:min-h-72">
          {selectedStep ? (
            <StepInspector
              // Remount per step: the inspector holds per-step working state (cluster
              // proposals, loaded values) that must not carry over to another step.
              key={selectedStep.id}
              onCollapse={() => setInspectorOpen(false)}
              step={selectedStep} inputOptions={inputOptions}
              inputLabel={inputLabel} wouldCycle={wouldCycle}
              isOutput={selectedStep.id === outputId} targetColumns={targetCols}
              previewColumns={preview.data?.columns ?? []}
              onChange={patchStep}
              onDelete={() => deleteStep(selectedStep.id)}
              onMakeOutput={() => mutate((p) => ({ ...p, outputStep: selectedStep.id }))}
              onSuggestEnum={suggestEnum}
              onClusterEnum={clusterEnum}
              onColumnValues={columnValues}
              onSuggestFieldMap={suggestFieldMap}
              onInputColumns={inputColumns}
              onSuggestSql={suggestSql}
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
              <Table2 className="size-5 text-muted-foreground/40" />
              <p className="text-[11px] text-muted-foreground">
                {activeId.startsWith('source:')
                  ? 'Raw source table — add a step to start shaping it.'
                  : 'Select a step to configure it, or let the AI draft the pipeline.'}
              </p>
              <Button size="sm" variant="ghost" onClick={() => setInspectorOpen(false)}>
                <PanelRightClose className="size-3.5" />Hide
              </Button>
            </div>
          )}
        </Card>
        )}
      </div>

      {!available && (
        <Card className="flex shrink-0 items-start gap-2 border-rose-500/30 bg-rose-500/5 p-3 text-[12px]">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-600" />
          <p className="text-muted-foreground">
            Previews still work — they run in the local sandbox. To build, test and publish, install the
            dbt engine to <code className="rounded bg-muted px-1">~/.local/bin/dbt</code> or set{' '}
            <code className="rounded bg-muted px-1">DBT_BIN</code>.
          </p>
        </Card>
      )}
    </div>
  )
}

/** The last dbt build: its error, or its quality tests, in one strip under the grid. */
function BuildStatus({ summary, tests }: {
  summary: DataAsset['dbt']
  tests: NonNullable<DataAsset['dbt']>['nodes']
}) {
  const [open, setOpen] = useState(false)
  if (!summary) {
    return (
      <p className="shrink-0 px-1 text-[10px] text-muted-foreground">
        Previews run in the sandbox · run <span className="font-medium">Build &amp; test</span> to
        validate quality and enable publishing.
      </p>
    )
  }
  if (!summary.ok && summary.error) {
    return (
      <Card className="shrink-0 border-rose-500/30 bg-rose-500/5 p-2.5">
        <p className="flex items-center gap-1.5 text-[11px] font-medium text-rose-700">
          <XCircle className="size-3.5 shrink-0" />Build / validation failed
        </p>
        <p className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-muted-foreground">
          {summary.error}
        </p>
      </Card>
    )
  }
  const failed = summary.failed ?? 0
  return (
    <Card className="shrink-0 overflow-hidden p-0">
      <button type="button" onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-[11px] transition-colors hover:bg-accent/50">
        {failed > 0 ? <XCircle className="size-3.5 text-rose-500" /> : <CheckCircle2 className="size-3.5 text-emerald-500" />}
        <span className="font-medium">Data-quality checks</span>
        <span className="text-muted-foreground">
          {summary.passed ?? 0} passed
          {failed > 0 && <span className="text-rose-600"> · {failed} failed</span>}
        </span>
        <span className="ml-auto text-[10px] text-muted-foreground">{open ? 'hide' : 'details'}</span>
      </button>
      {open && (
        <ul className="max-h-40 divide-y divide-border overflow-auto border-t border-border">
          {tests.map((t) => {
            const bad = FAIL.has(t.status)
            return (
              <li key={t.uniqueId} className="flex items-center gap-2 px-3 py-1 text-[11px]">
                {bad ? <XCircle className="size-3.5 shrink-0 text-rose-500" /> : <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />}
                <span className="font-medium">{testLabel(t.name)}</span>
                {bad && typeof t.failures === 'number' && t.failures > 0 && (
                  <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-700">{t.failures} bad rows</span>
                )}
                <span className="ml-auto truncate font-mono text-[9px] text-muted-foreground">{t.name}</span>
              </li>
            )
          })}
          {tests.length === 0 && (
            <li className="px-3 py-2 text-[10px] text-muted-foreground">No tests ran in the last build.</li>
          )}
        </ul>
      )}
    </Card>
  )
}
