import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentType, RefObject } from 'react'
import type { VizSpecStore } from '@kanaries/graphic-walker'
import '@kanaries/graphic-walker/dist/style.css'
import { api } from '../../../api/client'
import type { ValidationDataset, ValidationSpec, ValidationSpecStore } from '../../../lib/types'
import { specToChart } from './specToChart'

/**
 * The subset of Graphic Walker's (0.4.84) local-computation props we drive.
 * GW's exported component is an overload pair (local | remote); typing the lazy
 * component to just the local shape avoids TS resolving to the remote overload
 * (which wants `computation` instead of `data`). `data`/`fields`/`chart` are GW's
 * version-loose runtime shapes — kept as `unknown[]` at this one boundary.
 */
interface GraphicWalkerProps {
  storeRef: RefObject<VizSpecStore | null>
  data: unknown[]
  fields: unknown[]
  chart?: unknown[]
}

// Dynamic import keeps Graphic Walker (large) out of the initial bundle.
const GraphicWalker = lazy(() =>
  import('@kanaries/graphic-walker').then((m) => ({
    default: m.GraphicWalker as unknown as ComponentType<GraphicWalkerProps>,
  })),
)

/** How often we snapshot GW's internal store and persist edits (ms). */
const PERSIST_INTERVAL_MS = 2000

interface ExploreTabProps {
  projectId: string
  specs: ValidationSpec[]
}

export function ExploreTab({ projectId, specs }: ExploreTabProps) {
  const [dataset, setDataset] = useState<ValidationDataset | null>(null)
  const [saved, setSaved] = useState<ValidationSpecStore | null>(null)
  const [error, setError] = useState('')

  // GW exposes chart edits only through its store ref (no onChange callback in 0.4.x).
  const storeRef = useRef<VizSpecStore | null>(null)
  // The last spec JSON we persisted, so the poll only saves real changes.
  const lastPersisted = useRef('')
  const versionRef = useRef(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    Promise.all([api.getValidationDataset(projectId), api.getValidationSpecs(projectId)])
      .then(([ds, sp]) => {
        if (cancelled) return
        setError('')
        setDataset(ds)
        const store =
          'specs' in sp && Array.isArray((sp as ValidationSpecStore).specs)
            ? (sp as ValidationSpecStore)
            : null
        setSaved(store)
        if (store) {
          versionRef.current = store.version
          lastPersisted.current = JSON.stringify(store.specs)
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  // Preset charts: user-saved specs win; else translate the default presets.
  // Wrapped so a malformed preset can never block the explorer (it just starts blank).
  const initialCharts = useMemo<unknown[]>(() => {
    try {
      if (saved?.specs?.length) return saved.specs
      if (!dataset) return []
      return specs.map((s) => specToChart(s, dataset.columns))
    } catch {
      return []
    }
  }, [saved, dataset, specs])

  // Persist edits: poll the GW store, diff, and save when the charts actually change.
  useEffect(() => {
    if (!projectId || !dataset) return
    const timer = setInterval(() => {
      const store = storeRef.current
      if (!store) return
      let code: unknown[]
      try {
        code = store.exportCode()
      } catch {
        return
      }
      const json = JSON.stringify(code)
      if (json === lastPersisted.current) return
      lastPersisted.current = json
      void api
        .putValidationSpecs(projectId, { specs: code, version: versionRef.current + 1 })
        .then((res) => {
          versionRef.current = res.version
        })
        .catch(() => undefined)
    }, PERSIST_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [projectId, dataset])

  if (error) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-xs text-rose-600">
        {error}
      </div>
    )
  }
  if (!dataset) {
    return (
      <div className="grid h-full place-items-center text-xs text-muted-foreground">
        Loading data…
      </div>
    )
  }
  if (!dataset.rows.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        No published data yet — run task 2.3 after publishing indicators.
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {dataset.capped && (
        <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-[11px] text-amber-700">
          {dataset.note}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-auto">
        <Suspense
          fallback={
            <div className="grid h-full place-items-center text-xs text-muted-foreground">
              Loading explorer…
            </div>
          }
        >
          <GraphicWalker
            storeRef={storeRef}
            data={dataset.rows}
            fields={dataset.columns}
            chart={initialCharts.length ? initialCharts : undefined}
          />
        </Suspense>
      </div>
    </div>
  )
}
