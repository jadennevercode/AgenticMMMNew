import { useEffect, useMemo, useState } from 'react'
import { Loader2, Save, TriangleAlert } from 'lucide-react'
import { useSimStore } from '../../../store/useSimStore'
import { cn } from '../../../lib/cn'
import { Button } from '../../ui/button'
import type {
  OlsConfig,
  OlsParams,
  OlsSeasonality,
  OlsTrend,
  OlsXCandidate,
  TaskPanelKind,
} from '../../../lib/types'

/**
 * The 2.5 OLS setup panels — rendered inline inside their Process step
 * (ArtifactDetail → BuildStep). AI proposes, the human confirms:
 *   ols-y      → the response per model object
 *   ols-x      → the model variables, with their 2.4 statistics
 *   ols-params → transforms + trend/seasonality controls
 *
 * All three edit one backing model (`olsConfig`). Saving PUTs it, which re-fits
 * the regression server-side and re-renders the a-ols-test canvas. A draft +
 * dirty guard is required: the state poll replaces the whole slice every tick
 * and would otherwise clobber in-flight edits.
 */

/* ── shared shell ──────────────────────────────────────── */
function PanelShell({
  title, hint, dirty, saving, onSave, children,
}: {
  title: string
  hint?: string
  dirty: boolean
  saving: boolean
  onSave: () => void
  children: React.ReactNode
}) {
  return (
    <section className="mt-3 rounded-lg border border-border bg-card p-3">
      <header className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="text-[12.5px] font-semibold">{title}</h4>
          {hint && <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{hint}</p>}
        </div>
        <Button size="sm" onClick={onSave} disabled={!dirty || saving} className="shrink-0">
          {saving ? <Loader2 className="animate-spin" /> : <Save />}
          {saving ? 'Fitting…' : 'Save & refit'}
        </Button>
      </header>
      {children}
    </section>
  )
}

function SourceBanner({ dataSource }: { dataSource: string }) {
  if (dataSource !== 'reference') return null
  return (
    <p className="mb-2 flex items-start gap-1.5 rounded-md bg-amber-500/10 px-2 py-1.5 text-[11px] leading-snug text-amber-600">
      <TriangleAlert className="mt-px size-3 shrink-0" />
      No published project data — this setup is configured against the reference dataset.
      Publish the project&apos;s own assets in the Data Engine for a real fit.
    </p>
  )
}

/** Local draft over the store's olsConfig, guarded against poll churn. */
function useOlsDraft() {
  const stored = useSimStore((s) => s.olsConfig)
  const updateOlsConfig = useSimStore((s) => s.updateOlsConfig)
  const [draft, setDraft] = useState<OlsConfig | null>(stored)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // Re-sync from the store only while there are no pending local edits.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (stored && !dirty) setDraft(stored)
  }, [stored, dirty])

  function patch(p: Partial<OlsConfig>) {
    setDraft((d) => (d ? { ...d, ...p } : d))
    setDirty(true)
  }
  async function save() {
    if (!draft) return
    setSaving(true)
    try {
      await updateOlsConfig(draft)
      setDirty(false)
    } finally {
      setSaving(false)
    }
  }
  return { draft, dirty, saving, patch, save }
}

/* ── ols-y: the response variable ──────────────────────── */
function YPanel() {
  const { draft, dirty, saving, patch, save } = useOlsDraft()
  if (!draft) return null
  const objects = [...new Set(draft.yCandidates.map((c) => c.object))]

  const choose = (object: string, metric: string) => {
    const c = draft.yCandidates.find((x) => x.object === object && x.metric === metric)
    if (!c) return
    patch({
      y: [
        ...draft.y.filter((x) => x.object !== object),
        { object, metric: c.metric, metricType: c.metricType, isMoney: c.isMoney },
      ],
    })
  }

  return (
    <PanelShell
      title="Response variable (Y)"
      hint="What each model object is fitted against. A money response makes ROI a true incremental-revenue / spend ratio; a volume response keeps coefficients in sales units."
      dirty={dirty} saving={saving} onSave={() => void save()}
    >
      <SourceBanner dataSource={draft.dataSource} />
      <div className="space-y-2.5">
        {objects.map((obj) => {
          const picked = draft.y.find((y) => y.object === obj)?.metric
          return (
            <div key={obj}>
              <p className="mb-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">{obj}</p>
              <div className="space-y-1">
                {draft.yCandidates.filter((c) => c.object === obj).map((c) => (
                  <label
                    key={c.metric}
                    className={cn(
                      'flex cursor-pointer items-start gap-2 rounded-md border px-2 py-1.5 transition-colors',
                      picked === c.metric ? 'border-primary/50 bg-accent' : 'border-border hover:bg-accent/50',
                    )}
                  >
                    <input
                      type="radio" name={`y-${obj}`} checked={picked === c.metric}
                      onChange={() => choose(obj, c.metric)} className="mt-1 shrink-0"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[12px] font-medium">{c.metric}</span>
                        <span className={cn(
                          'rounded px-1 text-[9px] font-medium uppercase',
                          c.isMoney ? 'bg-emerald-500/15 text-emerald-600' : 'bg-muted text-muted-foreground',
                        )}>
                          {c.isMoney ? 'money' : 'volume'}
                        </span>
                        <span className="text-[10px] text-muted-foreground">{c.metricType} · {c.months} months</span>
                        {c.recommended && (
                          <span className="rounded bg-primary/10 px-1 text-[9px] font-medium text-primary">recommended</span>
                        )}
                      </span>
                      <span className="mt-0.5 block text-[10.5px] leading-snug text-muted-foreground">{c.rationale}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </PanelShell>
  )
}

/* ── ols-x: the model variables ────────────────────────── */
function statTone(v: number, warn: number, bad: number): string {
  const a = Math.abs(v)
  if (a >= bad) return 'text-rose-600'
  if (a >= warn) return 'text-amber-600'
  return 'text-muted-foreground'
}

/** Which S2 layer rejected a locked candidate, in the human's language. */
const LOCKED_LABEL: Record<string, string> = {
  mapping: 'Ignored at 2.1',
  quality: 'Dropped at 2.2',
  signoff: 'Not signed off at 2.3',
  statistical: 'Dropped at 2.4',
}

function XRow({ c, onToggle }: { c: OlsXCandidate; onToggle: () => void }) {
  return (
    <label
      className={cn(
        'flex items-start gap-2 rounded-md border px-2 py-1.5 transition-colors',
        c.locked
          ? 'cursor-not-allowed border-dashed border-border/70 bg-muted/30 opacity-70'
          : c.selected
            ? 'cursor-pointer border-primary/50 bg-accent'
            : 'cursor-pointer border-border hover:bg-accent/50',
      )}
      title={c.locked ? c.rationale : undefined}
    >
      <input
        type="checkbox" checked={c.selected} onChange={onToggle} disabled={c.locked}
        className="mt-1 shrink-0"
      />
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-1.5">
          <span className={cn('text-[12px] font-medium', c.locked && 'line-through decoration-1')}>
            {c.indicator}
          </span>
          {c.l4 && <span className="text-[10px] text-muted-foreground">{c.l4}</span>}
          {c.isSpend && <span className="rounded bg-muted px-1 text-[9px] text-muted-foreground">spend</span>}
          {c.locked && (
            <span className="rounded bg-destructive/10 px-1 text-[9px] font-medium text-destructive">
              {LOCKED_LABEL[c.lockedBy] ?? 'rejected upstream'}
            </span>
          )}
          {c.recommended && !c.locked && (
            <span className="rounded bg-primary/10 px-1 text-[9px] font-medium text-primary">recommended</span>
          )}
        </span>
        <span className="mt-0.5 flex flex-wrap gap-2 font-mono text-[10px]">
          <span className={statTone(c.pearson, 0, 0)}>r={c.pearson >= 0 ? '+' : ''}{c.pearson.toFixed(2)}</span>
          <span className={statTone(c.vif, 5, 10)}>VIF={c.vif.toFixed(1)}</span>
          <span className="text-muted-foreground">CV={c.cv.toFixed(3)}</span>
          {c.statVerdict && <span className="text-muted-foreground">2.4: {c.statVerdict}</span>}
        </span>
        <span className="mt-0.5 block text-[10.5px] leading-snug text-muted-foreground">{c.rationale}</span>
      </span>
    </label>
  )
}

function XPanel() {
  const { draft, dirty, saving, patch, save } = useOlsDraft()
  const [showAll, setShowAll] = useState(false)
  if (!draft) return null

  // A locked candidate was rejected by an earlier layer; the tick is inert, and
  // the server would strip it from the selection anyway.
  const toggle = (key: string) =>
    patch({
      xCandidates: draft.xCandidates.map((c) =>
        c.key === key && !c.locked ? { ...c, selected: !c.selected } : c),
    })

  const selected = draft.xCandidates.filter((c) => c.selected)
  const locked = draft.xCandidates.filter((c) => c.locked)
  const shown = showAll
    ? draft.xCandidates
    : draft.xCandidates.filter((c) => c.selected || (c.recommended && !c.locked))
  // Cheapest honest df estimate: the shortest object drives the constraint. The
  // authoritative number comes back from the fit (objects[].dfRemaining).
  const controls = (draft.params.trend === 'linear' ? 1 : 0)
    + (draft.params.seasonality === 'fourier' ? 2 * draft.params.fourierK
      : draft.params.seasonality === 'dummies' ? 11 : 0)
  const used = 1 + selected.length + controls
  const tight = used > 20

  return (
    <PanelShell
      title="Model variables (X)"
      hint="Tick the variables that enter the regression. This is where you drive the screening — each carries its correlation with the KPI, its collinearity (VIF) and its 2.4 verdict."
      dirty={dirty} saving={saving} onSave={() => void save()}
    >
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span className="rounded bg-muted px-1.5 py-0.5 font-medium">
          {selected.length} of {draft.xCandidates.length} selected
        </span>
        <span className={cn('rounded px-1.5 py-0.5', tight ? 'bg-amber-500/15 text-amber-600' : 'bg-muted text-muted-foreground')}>
          ~{used} parameters ({selected.length} variables + {controls} controls + intercept)
        </span>
        {locked.length > 0 && (
          <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-destructive">
            {locked.length} rejected upstream
          </span>
        )}
        {tight && <span className="text-amber-600">Fewer variables fit more reliably on a short series.</span>}
      </div>
      <div className="space-y-1">
        {shown.map((c) => <XRow key={c.key} c={c} onToggle={() => toggle(c.key)} />)}
      </div>
      {draft.xCandidates.length > shown.length && !showAll && (
        <button type="button" onClick={() => setShowAll(true)} className="mt-2 text-[11px] text-primary hover:underline">
          Show all {draft.xCandidates.length} candidates
        </button>
      )}
    </PanelShell>
  )
}

/* ── ols-params: transforms + controls ─────────────────── */
const SEASONALITY: { id: OlsSeasonality; label: string; hint: string }[] = [
  { id: 'fourier', label: 'Fourier terms', hint: 'Smooth yearly shape, cheap in degrees of freedom' },
  { id: 'dummies', label: 'Monthly dummies', hint: 'Fully flexible, but costs 11 parameters' },
  { id: 'none', label: 'None', hint: 'Seasonal swing leaks into the paid variables' },
]
const TREND: { id: OlsTrend; label: string; hint: string }[] = [
  { id: 'linear', label: 'Linear trend', hint: 'Absorbs long-run drift' },
  { id: 'none', label: 'None', hint: 'Trend leaks into the paid variables' },
]

function Choice<T extends string>({
  label, hint, value, options, onChange,
}: {
  label: string
  hint?: string
  value: T
  options: { id: T; label: string; hint: string }[]
  onChange: (v: T) => void
}) {
  return (
    <div>
      <p className="text-[11px] font-medium">{label}</p>
      {hint && <p className="mb-1 text-[10.5px] leading-snug text-muted-foreground">{hint}</p>}
      <div className="mt-1 flex flex-wrap gap-1">
        {options.map((o) => (
          <button
            key={o.id} type="button" onClick={() => onChange(o.id)} title={o.hint}
            className={cn(
              'rounded-md border px-2 py-1 text-[11px] transition-colors',
              value === o.id ? 'border-primary/50 bg-accent font-medium' : 'border-border text-muted-foreground hover:bg-accent/50',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function ParamsPanel() {
  const { draft, dirty, saving, patch, save } = useOlsDraft()
  if (!draft) return null
  const p = draft.params
  const setP = (next: Partial<OlsParams>) => patch({ params: { ...p, ...next } })
  const anyVolume = draft.y.some((y) => !y.isMoney)

  return (
    <PanelShell
      title="Model settings"
      hint="Transforms shape how spend turns into sales; the controls absorb trend and seasonality so the paid variables do not — that is what keeps the baseline positive and the coefficients correctly signed."
      dirty={dirty} saving={saving} onSave={() => void save()}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-[11px] font-medium">Adstock carryover</p>
          <p className="mb-1 text-[10.5px] leading-snug text-muted-foreground">
            How much of a month&apos;s effect carries into the next.
          </p>
          <div className="flex items-center gap-2">
            <input
              type="range" min={0} max={0.9} step={0.1} value={p.adstock}
              onChange={(e) => setP({ adstock: Number(e.target.value) })}
              className="min-w-0 flex-1"
            />
            <span className="w-8 shrink-0 text-right font-mono text-[11px]">{p.adstock.toFixed(1)}</span>
          </div>
        </div>
        <Choice
          label="Saturation" hint="Diminishing returns on spend."
          value={p.saturation} onChange={(v) => setP({ saturation: v })}
          options={[
            { id: 'hill', label: 'Hill curve', hint: 'Diminishing returns at the mean' },
            { id: 'none', label: 'Linear', hint: 'No diminishing returns' },
          ]}
        />
        <Choice label="Trend control" value={p.trend} options={TREND} onChange={(v) => setP({ trend: v })} />
        <Choice
          label="Seasonality control" value={p.seasonality} options={SEASONALITY}
          onChange={(v) => setP({ seasonality: v })}
        />
        {p.seasonality === 'fourier' && (
          <div>
            <p className="text-[11px] font-medium">Fourier harmonics (K)</p>
            <p className="mb-1 text-[10.5px] leading-snug text-muted-foreground">Each K costs 2 parameters.</p>
            <div className="flex items-center gap-2">
              <input
                type="range" min={1} max={4} step={1} value={p.fourierK}
                onChange={(e) => setP({ fourierK: Number(e.target.value) })}
                className="min-w-0 flex-1"
              />
              <span className="w-8 shrink-0 text-right font-mono text-[11px]">{p.fourierK}</span>
            </div>
          </div>
        )}
        {anyVolume && (
          <div>
            <p className="text-[11px] font-medium">Unit price (optional)</p>
            <p className="mb-1 text-[10.5px] leading-snug text-muted-foreground">
              Converts incremental volume into revenue, so ROI becomes a real revenue / spend ratio
              comparable to the industry bands. Leave empty to keep ROI in volume per spend.
            </p>
            <input
              type="number" min={0} step="any" placeholder="e.g. 50"
              value={p.pricePerUnit ?? ''}
              onChange={(e) => setP({ pricePerUnit: e.target.value === '' ? null : Number(e.target.value) })}
              className="w-32 rounded-md border border-border bg-transparent px-2 py-1 text-[12px] outline-none focus:border-primary/50"
            />
          </div>
        )}
      </div>
    </PanelShell>
  )
}

/* ── dispatch ──────────────────────────────────────────── */
export function OlsStepPanel({ kind }: { kind: TaskPanelKind }) {
  const cfg = useSimStore((s) => s.olsConfig)
  const panel = useMemo(() => {
    switch (kind) {
      case 'ols-y': return <YPanel />
      case 'ols-x': return <XPanel />
      case 'ols-params': return <ParamsPanel />
      default: return null
    }
  }, [kind])

  if (!cfg) {
    return (
      <p className="mt-3 rounded-lg border border-dashed border-border px-3 py-2 text-[11.5px] text-muted-foreground">
        The setup has not been proposed yet — run the previous step first.
      </p>
    )
  }
  return panel
}
