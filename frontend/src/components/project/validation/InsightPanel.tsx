// frontend/src/components/project/validation/InsightPanel.tsx
import { useState } from 'react'
import { api } from '../../../api/client'

interface InsightPanelProps {
  projectId: string
  /** Read live at click-time — GW tab switches don't re-render the parent,
   * so a static prop would go stale as soon as the user changes charts. */
  getSpec: () => unknown
  getRows: () => unknown[]
  preset?: string
}

export function InsightPanel({ projectId, getSpec, getRows, preset }: InsightPanelProps) {
  const [text, setText] = useState(preset ?? '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const spec = getSpec()
      const rows = getRows()
      const { insight } = await api.generateValidationInsight(projectId, spec, rows)
      setText(insight || 'No insight returned — try adjusting the chart.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <aside className="w-72 shrink-0 border-l border-border bg-muted/20 p-4">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">AI Insight</h4>
        <button type="button" onClick={() => void generate()} disabled={loading}
          className="rounded-md bg-primary px-2.5 py-1 text-[11px] font-medium text-primary-foreground disabled:opacity-60">
          {loading ? 'Reading…' : 'Generate'}
        </button>
      </div>
      {error && <p className="text-[11px] text-rose-600">{error}</p>}
      <p className="text-xs leading-relaxed text-foreground">
        {text || <span className="text-muted-foreground">Generate an insight for the current chart.</span>}
      </p>
    </aside>
  )
}
