import { lazy, Suspense, useEffect, useRef, useState } from 'react'
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
  const [error, setError] = useState('')
  const [saveError, setSaveError] = useState(false)
  // Frozen once per project: GW's `chart` prop is live-reactive (it re-imports and
  // resets the active tab on every reference change), and the parent's `specs`
  // array gets a new reference on every ~1.5s /state poll — so we seed this ONCE
  // per project load and never let it be re-derived from a churning prop.
  const [initialCharts, setInitialCharts] = useState<unknown[] | null>(null)

  // GW exposes chart edits only through its store ref (no onChange callback in 0.4.x).
  const storeRef = useRef<VizSpecStore | null>(null)
  // The last spec JSON we persisted, so the poll only saves real changes.
  // When there are no saved specs yet, this starts as '' so the very first poll
  // persists the seeded default charts (intended — it saves the default tabs),
  // not a user edit.
  const lastPersisted = useRef('')
  const versionRef = useRef(0)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    // Reset (not synchronize): clears the previous project's frozen charts so GW
    // never renders one project's saved layout under another project's data while
    // the new project's charts load.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- prop-driven reset keyed on projectId, not an external-system sync
    setInitialCharts(null)
    Promise.all([api.getValidationDataset(projectId), api.getValidationSpecs(projectId)])
      .then(([ds, sp]) => {
        if (cancelled) return
        setError('')
        setDataset(ds)
        const store =
          'specs' in sp && Array.isArray((sp as ValidationSpecStore).specs)
            ? (sp as ValidationSpecStore)
            : null
        // Reset per-project tracking unconditionally so a project switch cannot
        // leak the previous project's version / last-saved snapshot (Fix 3).
        versionRef.current = store ? store.version : 0
        lastPersisted.current = store ? JSON.stringify(store.specs) : ''
        // Seed the explorer's charts ONCE per project and freeze the reference:
        // GW re-imports (and resets the active tab) on every `chart` prop change,
        // and the parent's `specs` array churns on each /state poll — so we must
        // NOT feed `specs` into GW reactively. Saved specs win; else translate presets.
        let charts: unknown[]
        try {
          charts = store?.specs?.length
            ? store.specs
            : specs.map((s) => specToChart(s, ds.columns))
        } catch {
          charts = []
        }
        setInitialCharts(charts)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- specs seeds charts once per project; later churn must not re-import into GW
  }, [projectId])

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
      const prev = lastPersisted.current
      lastPersisted.current = json
      void api
        .putValidationSpecs(projectId, { specs: code, version: versionRef.current + 1 })
        .then((res) => {
          versionRef.current = res.version
          setSaveError(false)
        })
        .catch(() => {
          lastPersisted.current = prev // roll back so the next tick retries this edit
          setSaveError(true)
        })
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
      {saveError && (
        <div className="border-b border-rose-500/30 bg-rose-500/10 px-4 py-1.5 text-[11px] text-rose-700">
          Couldn’t save your latest changes — retrying…
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
            chart={initialCharts && initialCharts.length ? initialCharts : undefined}
          />
        </Suspense>
      </div>
    </div>
  )
}
