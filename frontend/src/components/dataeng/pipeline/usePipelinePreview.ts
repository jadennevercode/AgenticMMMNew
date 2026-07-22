import { useCallback, useEffect, useRef, useState } from 'react'
import type { StepPreview, TransformPipeline } from '../../../lib/types'
import { api } from '../../../api/client'
import { useSimStore } from '../../../store/useSimStore'

/**
 * Live preview of the step being edited.
 *
 * Editing a transform used to mean save → dbt build → open the inspector's little
 * table; three deliberate actions before you could see whether the change did what
 * you meant. This hook closes that loop: it re-runs the sandbox preview whenever
 * the pipeline or the selected step changes, sending the *in-editor* pipeline so
 * unsaved edits render immediately.
 *
 * Edits arrive a keystroke at a time, so requests are debounced and only the
 * newest response is applied — a slow earlier query can never overwrite a newer
 * result. The previous rows stay on screen while the next run is in flight, which
 * keeps the grid from flashing empty between keystrokes.
 */

const DEBOUNCE_MS = 450

export interface PreviewState {
  data: StepPreview | null
  loading: boolean
  refresh: () => void
}

export function usePipelinePreview(
  assetId: string,
  pipeline: TransformPipeline,
  stepId: string,
  { enabled = true, limit = 200 }: { enabled?: boolean; limit?: number } = {},
): PreviewState {
  const pid = useSimStore((s) => s.activeProjectId)
  const [data, setData] = useState<StepPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [nonce, setNonce] = useState(0)
  const latest = useRef(0)

  // The pipeline object is rebuilt on every edit; key the effect on its content so
  // selecting a step or re-rendering does not re-fire an identical query.
  const pipelineKey = JSON.stringify(pipeline)
  const active = enabled && !!pid && !!stepId
    && (stepId.startsWith('source:') || pipeline.steps.length > 0)

  useEffect(() => {
    const seq = ++latest.current
    const timer = setTimeout(() => {
      if (!active || !pid) {
        setData(null)
        setLoading(false)
        return
      }
      setLoading(true)
      void api.previewPipeline(pid, assetId, JSON.parse(pipelineKey) as TransformPipeline, stepId, limit)
        .then((res) => { if (seq === latest.current) setData(res) })
        .catch((err: unknown) => {
          if (seq !== latest.current) return
          setData({
            ok: false, columns: [], rows: [], rowCount: 0, stats: [],
            error: err instanceof Error ? err.message : 'Preview failed.',
          })
        })
        .finally(() => { if (seq === latest.current) setLoading(false) })
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [active, pid, assetId, pipelineKey, stepId, limit, nonce])

  const refresh = useCallback(() => setNonce((n) => n + 1), [])
  return { data, loading, refresh }
}
