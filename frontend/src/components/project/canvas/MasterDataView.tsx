import { useEffect, useState } from 'react'
import { ChevronRight, Loader2, TriangleAlert } from 'lucide-react'
import { api } from '../../../api/client'
import { asMasterData } from '../../../lib/artifact-format'
import { cn } from '../../../lib/cn'
import { useSimStore } from '../../../store/useSimStore'
import type {
  ArtifactInstance,
  FunnelLayer,
  MasterDataObject,
  MasterDataRejected,
  MasterTable,
} from '../../../lib/types'

/**
 * Master Data (2.6) — the modeling feature table, and the audit trail behind it.
 *
 * Two things the old sheet view could not answer, and this one must:
 *   1. "Show me the wide table for THIS product × channel × region" — the slice
 *      is fetched live rather than baked into the artifact.
 *   2. "Where did my indicator go?" — the funnel names the layer that rejected
 *      each one, and every rejected row opens to its full chain of verdicts.
 */

/* ── the slicing bar ───────────────────────────────────── */
function DimSelect({
  label, options, value, onChange,
}: {
  label: string
  options: string[]
  value: string
  onChange: (v: string) => void
}) {
  if (options.length === 0) return null
  return (
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-[7rem] rounded-md border border-border bg-transparent px-2 py-1 text-[12px] outline-none focus:border-primary/50"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>{o}</option>
        ))}
      </select>
    </label>
  )
}

/* ── the filter funnel ─────────────────────────────────── */
function FunnelBar({ layers, onPick, picked }: {
  layers: FunnelLayer[]
  picked: string
  onPick: (layer: string) => void
}) {
  const start = layers[0]?.intake ?? 0
  return (
    <div className="flex flex-wrap items-stretch gap-1.5">
      {layers.map((l) => {
        const killed = l.rejected > 0
        const width = start > 0 ? Math.max(8, (l.survivors / start) * 100) : 0
        const isPicked = picked === l.layer
        return (
          <button
            key={l.layer}
            type="button"
            onClick={() => onPick(isPicked ? '' : l.layer)}
            disabled={!killed}
            className={cn(
              'group min-w-[8.5rem] flex-1 rounded-lg border px-2.5 py-2 text-left transition-colors',
              isPicked ? 'border-primary/60 bg-accent' : 'border-border bg-card',
              killed ? 'cursor-pointer hover:border-primary/40' : 'cursor-default opacity-70',
            )}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[11px] font-medium">{l.label}</span>
              <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{l.task}</span>
            </div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="font-mono text-[15px] font-semibold tabular-nums">{l.survivors}</span>
              {killed && (
                <span className="font-mono text-[11px] font-medium text-destructive">−{l.rejected}</span>
              )}
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted">
              <div
                className={cn('h-full rounded-full', killed ? 'bg-destructive/60' : 'bg-emerald-500/60')}
                style={{ width: `${width}%` }}
              />
            </div>
          </button>
        )
      })}
    </div>
  )
}

/* ── a rejected indicator, with its full verdict chain ─── */
function RejectedRow({ r }: { r: MasterDataRejected }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="border-b border-border/60 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-2 py-1.5 text-left hover:bg-accent/50"
      >
        <ChevronRight className={cn('mt-0.5 size-3 shrink-0 transition-transform', open && 'rotate-90')} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-1.5">
            <span className="text-[12px] font-medium">{r.indicator}</span>
            {r.l4 && <span className="text-[10px] text-muted-foreground">{r.l4}</span>}
          </span>
          <span className="mt-0.5 block text-[10.5px] leading-snug text-muted-foreground">{r.reason}</span>
        </span>
      </button>
      {open && (
        <ol className="mb-2 ml-7 space-y-1 border-l border-border pl-3">
          {r.verdicts.map((v) => (
            <li key={v.layer} className="flex items-baseline gap-2 text-[10.5px]">
              <span
                className={cn(
                  'w-[4.5rem] shrink-0 rounded px-1 text-center text-[9px] font-medium uppercase',
                  v.status === 'rejected' ? 'bg-destructive/15 text-destructive'
                    : v.status === 'inherited' ? 'bg-muted text-muted-foreground'
                      : v.status === 'flagged' ? 'bg-amber-500/15 text-amber-600'
                        : v.status === 'pending' ? 'bg-slate-400/15 text-slate-500'
                          : 'bg-emerald-500/15 text-emerald-600',
                )}
              >
                {v.status}
              </span>
              <span className="min-w-0">
                <span className="font-medium">{v.label}</span>
                <span className="ml-1 font-mono text-[9px] text-muted-foreground">{v.task}</span>
                <span className="block text-muted-foreground">{v.note}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </li>
  )
}

function ObjectCard({ o }: { o: MasterDataObject }) {
  if (o.error) {
    return (
      <div className="min-w-[190px] shrink-0 rounded-xl border border-rose-500/30 bg-rose-500/5 p-3">
        <div className="text-[13px] font-semibold text-rose-600">{o.object}</div>
        <p className="mt-1 text-[11px] leading-snug text-rose-500/80">{o.error}</p>
      </div>
    )
  }
  return (
    <div className="min-w-[190px] shrink-0 rounded-xl border border-border bg-card p-3 shadow-sm">
      <div className="text-[13px] font-semibold">{o.object}</div>
      <dl className="mt-2 space-y-1 text-[11px]">
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Periods</dt>
          <dd className="font-mono">{o.months}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Features</dt>
          <dd className="font-mono font-medium">{o.features}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="shrink-0 text-muted-foreground">Y</dt>
          <dd className="truncate font-mono" title={o.y}>{o.y || '—'}</dd>
        </div>
      </dl>
    </div>
  )
}

/* ── the live wide table ───────────────────────────────── */
function WideTable({ table, loading }: { table: MasterTable | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="grid h-40 place-items-center text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
      </div>
    )
  }
  if (!table || table.rows.length === 0) {
    return (
      <p className="px-3 py-8 text-center text-[12px] text-muted-foreground">
        {table?.note || 'No rows for this slice.'}
      </p>
    )
  }
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead className="sticky top-0 bg-muted/80 backdrop-blur">
          <tr>
            {table.columns.map((c, i) => (
              <th
                key={c}
                className={cn(
                  'whitespace-nowrap border-b border-border px-2 py-1.5 text-left font-medium',
                  i === 0 && 'sticky left-0 bg-muted/80',
                  i === 1 && 'text-primary',
                )}
                title={c}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, ri) => (
            <tr key={ri} className="hover:bg-accent/40">
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className={cn(
                    'whitespace-nowrap border-b border-border/40 px-2 py-1 font-mono tabular-nums',
                    ci === 0 && 'sticky left-0 bg-background font-medium',
                    ci === 1 && 'text-primary',
                    cell === null && 'text-muted-foreground/50',
                  )}
                >
                  {cell === null ? '—' : typeof cell === 'number' ? cell.toLocaleString() : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ── the view ──────────────────────────────────────────── */
export function MasterDataView({ inst }: { inst: ArtifactInstance }) {
  const data = asMasterData(inst.body)
  const projectId = useSimStore((s) => s.activeProjectId)

  const [brand, setBrand] = useState('')
  const [provinceGroup, setProvinceGroup] = useState('')
  const [channelType, setChannelType] = useState('')
  const [channel, setChannel] = useState('')
  const [grainPick, setGrainPick] = useState('')
  const [table, setTable] = useState<MasterTable | null>(null)
  const [loading, setLoading] = useState(false)
  const [pickedLayer, setPickedLayer] = useState('')

  const dims = data?.dimensions
  const grains = dims?.grains ?? ['month']
  // Derived rather than stored: the available grains come from the artifact, so
  // storing a pick that may not be offered would need an effect to repair it.
  const grain = grainPick && grains.includes(grainPick)
    ? grainPick
    : grains[grains.length - 1] ?? 'month'

  useEffect(() => {
    if (!projectId || !data) return
    let cancelled = false
    // Fetching the slice IS the external-system sync this effect exists for, and
    // the loading flag is part of that handshake rather than derived state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    api
      .masterTable(projectId, {
        brand: brand ? [brand] : [],
        provinceGroup: provinceGroup ? [provinceGroup] : [],
        channelType: channelType ? [channelType] : [],
        channel: channel ? [channel] : [],
        grain,
      })
      .then((t) => { if (!cancelled) setTable(t) })
      .finally(() => { if (!cancelled) setLoading(false) })
    // A slice change makes the shown table wrong, so the in-flight one is dropped.
    return () => { cancelled = true }
  }, [projectId, data, brand, provinceGroup, channelType, channel, grain])

  if (!data) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        Master Data is not assembled yet — run task 2.6.
      </div>
    )
  }

  const rejected = pickedLayer
    ? data.rejected.filter((r) => r.rejectedAt === pickedLayer)
    : data.rejected
  const pickedLabel = data.funnel.find((f) => f.layer === pickedLayer)?.label

  return (
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
      <header className="rounded-xl border border-border bg-muted/30 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold tracking-tight">
            Master Data · {data.adopted.length} adopted indicator{data.adopted.length === 1 ? '' : 's'}
          </h2>
          <span className="text-xs text-muted-foreground">
            {data.rejected.length} rejected across {data.funnel.length} filter layers
          </span>
        </div>
        {data.note && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{data.note}</p>}
      </header>

      {data.objects.length > 0 && (
        <div className="flex gap-2.5 overflow-x-auto pb-1">
          {data.objects.map((o) => <ObjectCard key={o.object} o={o} />)}
        </div>
      )}

      <section className="space-y-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Filter funnel
        </h3>
        <FunnelBar layers={data.funnel} picked={pickedLayer} onPick={setPickedLayer} />
      </section>

      {data.rejected.length > 0 && (
        <section className="rounded-xl border border-border bg-card">
          <header className="flex items-baseline justify-between gap-2 border-b border-border px-3 py-2">
            <h3 className="text-[12px] font-semibold">
              Rejected indicators{pickedLabel ? ` · ${pickedLabel}` : ''}
            </h3>
            <span className="text-[10.5px] text-muted-foreground">
              {rejected.length} shown — click one for its full verdict chain
            </span>
          </header>
          <ul className="max-h-64 overflow-y-auto">
            {rejected.map((r) => <RejectedRow key={`${r.l4}|${r.indicator}`} r={r} />)}
          </ul>
        </section>
      )}

      <section className="rounded-xl border border-border bg-card">
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-3 py-2.5">
          <div className="flex flex-wrap items-end gap-2.5">
            <DimSelect label="Product" options={dims?.brand ?? []} value={brand} onChange={setBrand} />
            <DimSelect label="Channel type" options={dims?.channelType ?? []} value={channelType} onChange={setChannelType} />
            <DimSelect label="Channel" options={dims?.channel ?? []} value={channel} onChange={setChannel} />
            <DimSelect label="Region" options={dims?.provinceGroup ?? []} value={provinceGroup} onChange={setProvinceGroup} />
            <DimSelect label="Grain" options={grains} value={grain} onChange={setGrainPick} />
          </div>
          {table && table.rows.length > 0 && (
            <span className="pb-1 text-[10.5px] text-muted-foreground">
              {table.rowCount} periods × {table.colCount} indicators
            </span>
          )}
        </header>
        {table?.truncated && (
          <p className="flex items-start gap-1.5 border-b border-border bg-amber-500/10 px-3 py-1.5 text-[10.5px] text-amber-600">
            <TriangleAlert className="mt-px size-3 shrink-0" />
            {table.note}
          </p>
        )}
        <div className="max-h-[26rem]">
          <WideTable table={table} loading={loading} />
        </div>
      </section>
    </div>
  )
}
