import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, Database, GitBranch, Loader2, PanelRightClose,
  PanelRightOpen, Play, RefreshCw, Save, Sparkles, Table2, XCircle,
} from 'lucide-react'
import type {
  DataAsset, DbtWorkspaceInfo, EnumMapEntry, StepKind, TransformPipeline, TransformStep,
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
    note: '', inputs: [], fieldMap: [], enumField: '', enumMap: [], join: null,
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
  const [selected, setSelected] = useState<string | null>(null)
  const [view, setView] = useState<'table' | 'graph'>('table')
  // A wide result needs the room more than the form does; the inspector folds away.
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const [instruction, setInstruction] = useState('')
  const [targetCols, setTargetCols] = useState<string[]>([])
  const summary = asset.dbt ?? null

  const refresh = useCallback(async () => setInfo(await dbtStatus(asset.id)), [asset.id, dbtStatus])
  useEffect(() => { void refresh() }, [refresh, asset.updatedAt])
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
  }, [asset.id, asset.pipeline, dirty])
  useEffect(() => {
    if (!pid) return
    void api.getTargetSchema(pid).then((cols) => setTargetCols(cols.map((c) => c.name)))
  }, [pid])

  const sources = useMemo(() => info?.sources ?? [], [info])
  const available = info?.available ?? true
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

  const mutate = (next: TransformPipeline) => { setPipe(next); setDirty(true) }
  const patchStep = (next: TransformStep) =>
    mutate({ ...pipe, steps: pipe.steps.map((s) => (s.id === next.id ? next : s)) })

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
  const suggestEnum = useCallback(async (field: string, targetColumn: string): Promise<EnumMapEntry[] | null> => {
    if (!pid) return null
    try { return await api.suggestEnumMap(pid, asset.id, field, targetColumn) } catch { return null }
  }, [pid, asset.id])
  const clusterEnum = useCallback(async (field: string) => {
    if (!pid || !selectedStep) return null
    try { return await api.clusterEnumValues(pid, asset.id, pipe, selectedStep.id, field) } catch { return null }
  }, [pid, asset.id, pipe, selectedStep])

  function addStep(kind: StepKind) {
    const s = newStep(kind, pipe.steps.length + 1)
    mutate({ ...pipe, steps: [...pipe.steps, s], outputStep: pipe.outputStep || s.id })
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

      {/* ── steps · data · configuration ── */}
      <div className={cn('grid min-h-0 flex-1 gap-3',
        inspectorOpen ? 'xl:grid-cols-[11.5rem_minmax(0,1fr)_21rem]'
          : 'xl:grid-cols-[11.5rem_minmax(0,1fr)_2.25rem]')}>
        <Card className="min-h-0 overflow-hidden p-0 max-xl:max-h-64">
          <StepList
            pipeline={pipe} sources={sources} statusByStep={statusByStep}
            selected={activeId} outputId={outputId}
            onSelect={(id) => setSelected(id)} onAdd={addStep}
          />
        </Card>

        <div className="flex min-h-0 min-w-0 flex-col gap-2">
          <div className="flex shrink-0 items-center gap-2">
            <h4 className="min-w-0 truncate text-[12px] font-semibold">
              {view === 'table' ? <>Preview · <span className="font-mono text-primary">{gridTitle}</span></> : 'Pipeline graph'}
            </h4>
            {view === 'table' && dirty && (
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
                ? 'Upload raw files in step 1 — the preview reads them directly.'
                : 'Select a source or step to see its data.'}
            />
          ) : (
            <div className="min-h-64 flex-1 overflow-hidden rounded-lg border border-border">
              <PipelineCanvas
                pipeline={pipe} sources={sources} statusByStep={statusByStep}
                selected={activeId} onSelect={(id) => setSelected(id)}
                onConnect={(src, tgt) => {
                  const step = pipe.steps.find((s) => s.id === tgt)
                  if (step && !step.inputs.includes(src)) patchStep({ ...step, inputs: [...step.inputs, src] })
                }}
                onDisconnect={(src, tgt) => {
                  const step = pipe.steps.find((s) => s.id === tgt)
                  if (step) patchStep({ ...step, inputs: step.inputs.filter((i) => i !== src) })
                }}
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
              onCollapse={() => setInspectorOpen(false)}
              step={selectedStep} inputOptions={inputOptions}
              isOutput={selectedStep.id === outputId} targetColumns={targetCols}
              previewColumns={preview.data?.columns ?? []}
              onChange={patchStep}
              onDelete={() => {
                mutate({
                  ...pipe,
                  steps: pipe.steps.filter((s) => s.id !== selectedStep.id)
                    .map((s) => ({ ...s, inputs: s.inputs.filter((i) => i !== selectedStep.id) })),
                  outputStep: pipe.outputStep === selectedStep.id ? '' : pipe.outputStep,
                })
                setSelected(null)
              }}
              onMakeOutput={() => mutate({ ...pipe, outputStep: selectedStep.id })}
              onSuggestEnum={suggestEnum}
              onClusterEnum={clusterEnum}
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
