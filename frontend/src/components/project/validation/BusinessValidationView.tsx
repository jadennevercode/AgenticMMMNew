import { useState } from 'react'
import type { ArtifactInstance } from '../../../lib/types'
import { useSimStore } from '../../../store/useSimStore'
import { asValidation } from '../../../lib/artifact-format'
import { cn } from '../../../lib/cn'
import { ChartsTab } from './ChartsTab'
import { ExploreTab } from './ExploreTab'
import { SignoffTab } from './SignoffTab'

type Tab = 'charts' | 'explore' | 'signoff'
const TAB_LABEL: Record<Tab, string> = {
  charts: 'Charts',
  explore: 'Free explore',
  signoff: 'Sign-off',
}

export function BusinessValidationView({ inst }: { inst: ArtifactInstance }) {
  const projectId = useSimStore((s) => s.activeProjectId)
  const signoffs = useSimStore((s) => s.signoffs)
  const [tab, setTab] = useState<Tab>('charts')
  const data = asValidation(inst.body)

  if (!data || !data.groups.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        Business Validation is not ready yet — run task 2.3 to chart each factor against sell-out.
      </div>
    )
  }

  // Denials are the consequential verdict — an explicit 'no' excludes an
  // indicator (or, via l3, every indicator under a factor) from the model.
  const denied = Object.values(signoffs).filter((v) => v === 'no').length

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex items-center justify-between gap-3 border-b border-border px-5 py-2.5">
        <div className="flex items-center gap-1">
          {(['charts', 'explore', 'signoff'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                'rounded-md px-3 py-1 text-xs font-medium transition-colors',
                tab === t ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted',
              )}
            >
              {TAB_LABEL[t]}
            </button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground">
          Response Y: <span className="font-medium text-foreground">{data.kpiMetric || '—'}</span> · {denied} denied
        </span>
      </header>
      {tab === 'charts'
        ? projectId && <ChartsTab projectId={projectId} data={data} />
        : tab === 'explore'
        ? projectId && <ExploreTab projectId={projectId} specs={data.specs ?? []} />
        : <SignoffTab groups={data.groups} />}
    </div>
  )
}
