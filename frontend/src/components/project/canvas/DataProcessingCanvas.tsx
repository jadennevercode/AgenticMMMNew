import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

import { api } from '../../../api/client'
import type { ArtifactInstance, FactorMap, FactorMapRow, MetricRole } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { Button } from '../../ui/button'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

/**
 * The model role, as the user picks it: the response, a driver, or out.
 * `excluded` is the wire value the backend already stores for "not in model".
 */
const ROLE_OPTIONS: { value: MetricRole; label: string }[] = [
  { value: 'X', label: 'X' },
  { value: 'Y', label: 'Y' },
  { value: 'excluded', label: 'Unused' },
]

/**
 * Two aggregations, because there are only two questions worth asking of an
 * indicator: does it add up across periods and dimensions, or does it average?
 * The backend accepts exactly these and honours the answer everywhere downstream.
 */
const AGG_OPTIONS: { value: string; label: string }[] = [
  { value: 'sum', label: 'SUM' },
  { value: 'average', label: 'AVG' },
]

/**
 * Status is binary here: an indicator either has a published Data-Engine
 * indicator behind it or it does not. `ignored` and `pending` are two ways of
 * not having one — the distinction still exists on the wire (the 2.1 gate and
 * the ledger read it) but it is not what this column is asking.
 */
const STATUS_LABEL: Record<string, string> = {
  mapped: 'Matched',
  ignored: 'Unmatched',
  pending: 'Unmatched',
}
const TONE: Record<string, FactorCanvasTone> = {
  mapped: 'ok',
  ignored: 'muted',
  pending: 'muted',
}

/**
 * 2.1 Data Processing — the factor tree with its Data-Engine mapping on every row.
 *
 * The table answers exactly the questions this step owns:
 * `L1 · L2 · L3 · L4 · Indicator · Role · Aggregation · Status`. Provenance
 * (which asset, which raw metric, what coverage) belongs to the Data Engine and
 * to the row detail below — carrying it in the grid made every row three lines
 * of text wide and buried the two controls that actually decide the model.
 *
 * The factor map is component-local state (as in the Data Engine panel) because
 * it is derived from published indicators, not from a ProjectState slice the
 * poll replaces.
 */
export function DataProcessingCanvas({ inst }: { inst: ArtifactInstance }) {
  const projectId = useSimStore((s) => s.activeProjectId)
  const refresh = useSimStore((s) => s.refresh)
  const reportError = useSimStore((s) => s.reportError)
  const [map, setMap] = useState<FactorMap | null>(null)
  const [selected, setSelected] = useState<string>('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!projectId) return
    api.getFactorMap(projectId).then(setMap).catch((e) => { setMap(null); reportError(e) })
  }, [projectId, reportError])

  useEffect(load, [load])

  async function mutate(fn: () => Promise<FactorMap>) {
    setBusy(true)
    try {
      setMap(await fn())
      await refresh()
    } catch (e) {
      reportError(e)
    } finally {
      setBusy(false)
    }
  }

  function bind(rowId: string, indicatorId: string) {
    if (!projectId) return
    void mutate(() => api.bindFactorMap(projectId, rowId, indicatorId))
  }

  function ignore(rowId: string, ignored: boolean) {
    if (!projectId) return
    void mutate(() => api.setFactorMapIgnore(projectId, rowId, ignored, ''))
  }

  function ignoreAllPending() {
    if (!projectId || !map) return
    const rowIds = map.rows.filter((x) => x.status === 'pending').map((r) => r.rowId)
    if (!rowIds.length) return
    void mutate(() => api.setFactorMapIgnoreBulk(projectId, rowIds, 'No data source'))
  }

  function setRole(row: FactorMapRow, metricType: MetricRole) {
    if (!projectId) return
    void mutate(() => api.setFactorMapMetricType(projectId, row.l4, row.metric || row.indicator, metricType))
  }

  function setAgg(row: FactorMapRow, aggregation: string) {
    if (!projectId) return
    void mutate(() => api.setFactorMapAggregation(projectId, row.l4, row.metric || row.indicator, aggregation))
  }

  /** The indicator currently carrying the response role, if any. */
  const currentY: FactorMapRow | undefined = useMemo(
    () => (map?.rows ?? []).find((r) => r.status === 'mapped' && r.metricType === 'Y'),
    [map],
  )

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      (map?.rows ?? []).map((r) => {
        const matched = r.status === 'mapped'
        return {
          key: r.rowId,
          l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
          indicator: r.indicator,
          tone: TONE[r.status] ?? 'muted',
          statusLabel: STATUS_LABEL[r.status] ?? r.status,
          cells: [
            matched ? (
              <select
                aria-label={`Role for ${r.indicator}`}
                value={r.metricType}
                disabled={busy}
                onChange={(e) => setRole(r, e.target.value as MetricRole)}
                className="rounded border border-border bg-background px-1 py-0.5 text-[11px]
                           transition-colors hover:border-foreground/40
                           focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-foreground/20"
              >
                {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : '—',
            matched ? (
              <select
                aria-label={`Aggregation for ${r.indicator}`}
                value={AGG_OPTIONS.some((a) => a.value === r.aggregation) ? r.aggregation : 'sum'}
                disabled={busy || r.metricType === 'excluded'}
                onChange={(e) => setAgg(r, e.target.value)}
                className="rounded border border-border bg-background px-1 py-0.5 text-[11px]
                           transition-colors hover:border-foreground/40 disabled:opacity-40
                           focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-foreground/20"
              >
                {AGG_OPTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
            ) : '—',
          ],
        }
      }),
    // `busy` is a dependency because it disables every control in the grid.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [map, busy],
  )

  const selectedRow: FactorMapRow | undefined = useMemo(
    () => (map?.rows ?? []).find((r) => r.rowId === selected),
    [map, selected],
  )

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">{inst.name}</h3>
        <p className="text-[11px] text-muted-foreground">
          {map
            ? `${map.mapped} matched · ${map.total - map.mapped} unmatched of ${map.total}` +
              (currentY ? ` · response: ${currentY.indicator}` : ' · no response selected')
            : 'Loading the mapping…'}
        </p>
      </div>
      <div className="flex items-center gap-2">
        {map && map.pending > 0 && (
          <Button size="sm" variant="outline" disabled={busy} onClick={ignoreAllPending}>
            Ignore all pending
          </Button>
        )}
        <Button size="sm" variant="outline" asChild>
          <Link to={`/p/${projectId}/data`}>
            Open Data Engine <ExternalLink className="ml-1 h-3 w-3" />
          </Link>
        </Button>
      </div>
    </header>
  )

  return (
    <>
      <FactorTreeCanvas
        rows={rows}
        columns={['Role', 'Aggregation']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="No active factor-tree rows to map. Confirm the factor tree in S1 first."
      />
      {selectedRow && (
        <RowDetail
          row={selectedRow}
          busy={busy}
          currentY={currentY}
          onBind={bind}
          onIgnore={ignore}
        />
      )}
    </>
  )
}

/**
 * The selected row's provenance and its mapping actions.
 *
 * These moved out of the grid's Action column: binding, releasing and ignoring
 * are per-row decisions a user makes one at a time after reading where the data
 * would come from, and they were competing for width with the two controls used
 * on every row.
 */
function RowDetail({
  row, busy, currentY, onBind, onIgnore,
}: {
  row: FactorMapRow
  busy: boolean
  currentY: FactorMapRow | undefined
  onBind: (rowId: string, indicatorId: string) => void
  onIgnore: (rowId: string, ignored: boolean) => void
}) {
  const isY = row.status === 'mapped' && row.metricType === 'Y'
  const otherY = currentY && currentY.rowId !== row.rowId ? currentY : undefined

  return (
    <aside className="border-t border-border bg-muted/20 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {[row.l4 || row.l3, row.indicator].filter(Boolean).join(' · ')}
        </p>
        <div className="flex items-center gap-3">
          {row.status === 'mapped' && (
            <button type="button" disabled={busy} onClick={() => onBind(row.rowId, '')}
              className="text-[11px] text-muted-foreground transition-colors hover:text-foreground">
              Release
            </button>
          )}
          {row.status === 'ignored' && (
            <button type="button" disabled={busy} onClick={() => onIgnore(row.rowId, false)}
              className="text-[11px] text-muted-foreground transition-colors hover:text-foreground">
              Restore
            </button>
          )}
          {row.status === 'pending' && (
            <button type="button" disabled={busy} onClick={() => onIgnore(row.rowId, true)}
              className="text-[11px] text-muted-foreground transition-colors hover:text-foreground">
              Ignore
            </button>
          )}
        </div>
      </div>

      {row.status === 'mapped' && (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Matched to {row.metric || '—'}
          {row.assetName ? ` in ${row.assetName}` : ''}
        </p>
      )}

      {!isY && otherY && (
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          Setting this indicator to Y replaces the current response ({otherY.indicator}) —
          a model has exactly one.
        </p>
      )}

      {row.suggestions.length > 0 && (
        <>
          <p className="mt-3 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {row.status === 'mapped' ? 'Other candidates' : 'Candidates'}
          </p>
          <ul className="mt-1 space-y-1">
            {row.suggestions.slice(0, 6).map((s) => (
              <li key={s.indicatorId} className="flex items-center justify-between gap-2 text-[11px]">
                <span>
                  {s.metric}
                  <span className="text-muted-foreground"> · {s.assetName} · {s.unit}</span>
                  <span className="text-muted-foreground/60"> · {s.coverageStart}–{s.coverageEnd}</span>
                </span>
                <button type="button" disabled={busy}
                  onClick={() => onBind(row.rowId, s.indicatorId)}
                  className="shrink-0 text-[11px] text-emerald-600 transition-colors hover:underline">
                  Use this
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </aside>
  )
}
