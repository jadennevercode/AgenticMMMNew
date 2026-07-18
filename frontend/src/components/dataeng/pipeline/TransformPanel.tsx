import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, Database, Loader2, Play, Plus, Save, Sparkles, XCircle,
} from 'lucide-react'
import type {
  DataAsset, DbtPreview, DbtWorkspaceInfo, EnumMapEntry, StepKind,
  TransformPipeline, TransformStep,
} from '../../../lib/types'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'
import { Card } from '../../ui/card'
import { Button } from '../../ui/button'
import { cn } from '../../../lib/cn'
import { PipelineCanvas } from './PipelineCanvas'
import { KIND_META, StepInspector } from './StepInspector'

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
  const { dbtBuild, dbtGenerate, dbtStatus, dbtPreview, putPipeline } = useSimStore.getState()

  const [info, setInfo] = useState<DbtWorkspaceInfo | null>(null)
  const [pipe, setPipe] = useState<TransformPipeline>(asset.pipeline ?? EMPTY_PIPE)
  const [dirty, setDirty] = useState(false)
  // Identity of the asset we're currently bound to, and a content-hash of the last
  // server pipeline we reconciled against. Used to avoid clobbering unsaved edits.
  const assetIdRef = useRef(asset.id)
  const syncedRef = useRef(JSON.stringify(asset.pipeline ?? EMPTY_PIPE))
  const [selected, setSelected] = useState<string | null>(null)
  const [instruction, setInstruction] = useState('')
  const [preview, setPreview] = useState<DbtPreview | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
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

  const sources = info?.sources ?? []
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
  const selectedStep = pipe.steps.find((s) => s.id === selected) ?? null
  const inputOptions = useMemo(
    () => [...sources.map((s) => `source:${s}`),
           ...pipe.steps.filter((s) => s.id !== selected).map((s) => s.id)],
    [sources, pipe.steps, selected])

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
  async function previewSelected() {
    if (!selected) return
    setPreviewBusy(true)
    try {
      if (selected.startsWith('source:') && pid) {
        setPreview(await api.rawPreview(pid, asset.id, selected.slice(7)))
      } else {
        const model = summary?.stepModels?.[selected]
        setPreview(model ? await dbtPreview(asset.id, model) : null)
      }
    } finally { setPreviewBusy(false) }
  }
  const suggestEnum = useCallback(async (field: string, targetColumn: string): Promise<EnumMapEntry[] | null> => {
    if (!pid) return null
    try { return await api.suggestEnumMap(pid, asset.id, field, targetColumn) } catch { return null }
  }, [pid, asset.id])

  function addStep(kind: StepKind) {
    const s = newStep(kind, pipe.steps.length + 1)
    mutate({ ...pipe, steps: [...pipe.steps, s], outputStep: pipe.outputStep || s.id })
    setSelected(s.id)
  }

  return (
    <div className="space-y-3">
      {/* ── toolbar: AI + build ── */}
      <Card className="space-y-2 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className={cn('flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-medium',
            available ? 'bg-emerald-500/10 text-emerald-700' : 'bg-rose-500/10 text-rose-700')}>
            <Database className="size-3" />{available ? (info?.message ?? 'engine ready') : 'engine unavailable'}
          </div>
          <span className="text-[11px] text-muted-foreground">
            AI drafts the step pipeline; every mapping, join and aggregation stays visible and editable below.
          </span>
        </div>
        <div className="flex gap-2">
          <input
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void aiDraft() }}
            placeholder={pipe.steps.length === 0
              ? 'Describe the shape you need, e.g. "standardise channels, join the price list, sum to channel × month"'
              : 'Ask the AI to adjust the pipeline, e.g. "split e-commerce vs modern trade"'}
            className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-primary/60"
          />
          <Button size="sm" onClick={() => void aiDraft()} disabled={busy || !available}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
            {pipe.steps.length === 0 ? 'AI draft' : 'AI adjust'}
          </Button>
          <Button size="sm" variant="outline" onClick={() => void save()} disabled={!dirty || busy}>
            <Save className="size-3.5" />Save
          </Button>
          <Button size="sm" variant="outline" onClick={() => void saveAndBuild()} disabled={busy || !available || pipe.steps.length === 0}>
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}Build
          </Button>
        </div>
      </Card>

      {/* ── canvas + inspector ── */}
      <div className="grid gap-3 lg:grid-cols-[1fr_380px]">
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Add step:</span>
            {(Object.keys(KIND_META) as StepKind[]).map((k) => (
              <button key={k} type="button" onClick={() => addStep(k)}
                className="flex items-center gap-0.5 rounded-full border border-border px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary">
                <Plus className="size-2.5" />{KIND_META[k].label}
              </button>
            ))}
          </div>
          <PipelineCanvas
            pipeline={pipe} sources={sources} statusByStep={statusByStep}
            selected={selected} onSelect={(id) => { setSelected(id); setPreview(null) }}
            onConnect={(src, tgt) => {
              const step = pipe.steps.find((s) => s.id === tgt)
              if (step && !step.inputs.includes(src)) patchStep({ ...step, inputs: [...step.inputs, src] })
            }}
            onDisconnect={(src, tgt) => {
              const step = pipe.steps.find((s) => s.id === tgt)
              if (step) patchStep({ ...step, inputs: step.inputs.filter((i) => i !== src) })
            }}
          />
          <p className="text-[10px] text-muted-foreground">
            Connect: drag from a node's right handle onto another step's left handle — or click a step and toggle its <span className="font-medium">Inputs</span> in the panel · {dirty ? 'unsaved changes' : 'saved'}
          </p>
        </div>

        <Card className="min-h-72 overflow-hidden p-0">
          {selectedStep ? (
            <StepInspector
              step={selectedStep} inputOptions={inputOptions}
              isOutput={selectedStep.id === outputId} targetColumns={targetCols}
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
              onPreview={() => void previewSelected()}
              preview={preview} previewBusy={previewBusy}
              onSuggestEnum={suggestEnum}
            />
          ) : selected?.startsWith('source:') ? (
            <div className="space-y-2 p-3">
              <p className="font-mono text-[12px] font-semibold">{selected.slice(7)}</p>
              <p className="text-[11px] text-muted-foreground">Raw source table.</p>
              <Button size="sm" variant="outline" onClick={() => void previewSelected()} disabled={previewBusy}>
                {previewBusy ? <Loader2 className="size-3.5 animate-spin" /> : null}Preview rows
              </Button>
              {preview && (
                <div className="max-h-64 overflow-auto rounded-md border border-border">
                  <table className="w-full border-collapse text-[10px]">
                    <thead className="sticky top-0 bg-muted/80 text-left text-muted-foreground">
                      <tr>{preview.columns.map((c) => <th key={c} className="whitespace-nowrap px-2 py-1 font-medium">{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, ri) => (
                        <tr key={ri} className="border-t border-border">
                          {row.map((cell, ci) => <td key={ci} className="whitespace-nowrap px-2 py-0.5">{cell}</td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center p-6 text-center text-[11px] text-muted-foreground">
              Select a node to configure it — or let the AI draft the pipeline and review each step here.
            </div>
          )}
        </Card>
      </div>

      {/* ── build error ── */}
      {summary && !summary.ok && summary.error && (
        <Card className="flex items-start gap-2 border-rose-500/30 bg-rose-500/5 p-3 text-[12px]">
          <XCircle className="mt-0.5 size-4 shrink-0 text-rose-600" />
          <div>
            <p className="font-medium text-rose-700">Build / validation failed</p>
            <p className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-muted-foreground">{summary.error}</p>
          </div>
        </Card>
      )}

      {/* ── data-quality checks ── */}
      {tests.length > 0 && (
        <Card className="p-0">
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <h4 className="text-[13px] font-semibold">Data-quality checks</h4>
            <span className="text-[11px] text-muted-foreground">
              {summary?.passed ?? 0} passed · <span className={cn((summary?.failed ?? 0) > 0 && 'text-rose-600')}>{summary?.failed ?? 0} failed</span>
            </span>
          </div>
          <ul className="divide-y divide-border">
            {tests.map((t) => {
              const failed = FAIL.has(t.status)
              return (
                <li key={t.uniqueId} className="flex items-center gap-2.5 px-4 py-1.5 text-[12px]">
                  {failed ? <XCircle className="size-4 shrink-0 text-rose-500" /> : <CheckCircle2 className="size-4 shrink-0 text-emerald-500" />}
                  <span className="font-medium">{testLabel(t.name)}</span>
                  {failed && typeof t.failures === 'number' && t.failures > 0 && (
                    <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-700">{t.failures} bad rows</span>
                  )}
                  <span className="ml-auto truncate font-mono text-[10px] text-muted-foreground">{t.name}</span>
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      {!available && (
        <Card className="flex items-start gap-2 border-rose-500/30 bg-rose-500/5 p-3 text-[12px]">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-600" />
          <p className="text-muted-foreground">
            Install the dbt engine to <code className="rounded bg-muted px-1">~/.local/bin/dbt</code> or set <code className="rounded bg-muted px-1">DBT_BIN</code>, then retry.
          </p>
        </Card>
      )}
    </div>
  )
}
