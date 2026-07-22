import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'

import { api } from '../../../api/client'
import type { ArtifactInstance, FactorMap, FactorMapRow } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { Button } from '../../ui/button'
import { FactorTreeCanvas } from '../factor-tree/FactorTreeCanvas'
import type { FactorCanvasRow, FactorCanvasTone } from '../factor-tree/types'

const TONE: Record<string, FactorCanvasTone> = {
  mapped: 'ok',
  ignored: 'muted',
  pending: 'warn',
}
const STATUS_LABEL: Record<string, string> = {
  mapped: 'Mapped',
  ignored: 'Ignored',
  pending: 'Pending',
}

/**
 * 2.1 Data Processing — the factor tree with its Data-Engine mapping on every row.
 *
 * The same bind / remap / ignore actions the Data Engine's indicator catalogue
 * offers, on the surface where the factor tree is the subject. The factor map is
 * component-local state (as in the Data Engine panel) because it is derived from
 * published indicators, not from a ProjectState slice the poll replaces.
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

  const rows: FactorCanvasRow[] = useMemo(
    () =>
      (map?.rows ?? []).map((r) => ({
        key: r.rowId,
        l1: r.l1, l2: r.l2, l3: r.l3, l4: r.l4,
        indicator: r.indicator,
        tone: TONE[r.status] ?? 'muted',
        statusLabel: STATUS_LABEL[r.status] ?? r.status,
        cells: [r.assetName || (r.status === 'ignored' ? '—' : ''), r.metric || ''],
      })),
    [map],
  )

  const selectedRow: FactorMapRow | undefined = useMemo(
    () => (map?.rows ?? []).find((r) => r.rowId === selected),
    [map, selected],
  )

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

  const header = (
    <header className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 className="text-sm font-medium">{inst.name}</h3>
        <p className="text-[11px] text-muted-foreground">
          {map
            ? `${map.mapped} mapped · ${map.ignored} ignored · ${map.pending} pending of ${map.total}`
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
        columns={['Asset', 'Metric']}
        selectedKey={selected}
        onSelect={setSelected}
        header={header}
        emptyHint="No active factor-tree rows to map. Confirm the factor tree in S1 first."
        actions={(r) => {
          const row = (map?.rows ?? []).find((x) => x.rowId === r.key)
          if (!row) return null
          if (row.status === 'mapped') {
            return (
              <button type="button" disabled={busy} onClick={() => bind(row.rowId, '')}
                className="text-[10.5px] text-muted-foreground hover:text-foreground">
                Release
              </button>
            )
          }
          if (row.status === 'ignored') {
            return (
              <button type="button" disabled={busy} onClick={() => ignore(row.rowId, false)}
                className="text-[10.5px] text-muted-foreground hover:text-foreground">
                Restore
              </button>
            )
          }
          return (
            <div className="flex items-center gap-2">
              {row.suggestions[0] && (
                <button type="button" disabled={busy}
                  onClick={() => bind(row.rowId, row.suggestions[0].indicatorId)}
                  className="text-[10.5px] text-emerald-600 hover:underline">
                  Accept “{row.suggestions[0].metric}”
                </button>
              )}
              <button type="button" disabled={busy} onClick={() => ignore(row.rowId, true)}
                className="text-[10.5px] text-muted-foreground hover:text-foreground">
                Ignore
              </button>
            </div>
          )
        }}
      />
      {selectedRow && selectedRow.suggestions.length > 1 && (
        <aside className="border-t border-border p-3">
          <p className="mb-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            Other candidates for {selectedRow.l4 || selectedRow.l3} · {selectedRow.indicator}
          </p>
          <ul className="space-y-1">
            {selectedRow.suggestions.slice(1, 6).map((s) => (
              <li key={s.indicatorId} className="flex items-center justify-between gap-2 text-[11px]">
                <span>
                  <span className="font-medium">{s.metric}</span>
                  <span className="text-muted-foreground"> · {s.assetName} · {s.unit}</span>
                  <span className="text-muted-foreground/60"> · {s.coverageStart}–{s.coverageEnd}</span>
                </span>
                <button type="button" disabled={busy}
                  onClick={() => bind(selectedRow.rowId, s.indicatorId)}
                  className="text-[10.5px] text-emerald-600 hover:underline">
                  Use this
                </button>
              </li>
            ))}
          </ul>
        </aside>
      )}
    </>
  )
}
