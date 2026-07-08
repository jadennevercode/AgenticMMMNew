import { useEffect, useState } from 'react'
import { Grid3x3, Loader2, Plus, RotateCcw, Rows3, Save, Trash2, X } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import type { ModelScope, ModelScopeDimension, ProjectProfile, TimeGranularity } from '../../lib/types'
import { Card } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'

const TIME_GRANULARITIES: TimeGranularity[] = ['Year', 'Month', 'Week']

interface DimensionCardProps {
  dim: ModelScopeDimension
  canRemove: boolean
  onRename: (name: string) => void
  onSetValues: (values: string[]) => void
  onRemove: () => void
}

/** One scope dimension: editable name + chip-based value list (add/remove individual values). */
function DimensionCard({ dim, canRemove, onRename, onSetValues, onRemove }: DimensionCardProps) {
  const [entry, setEntry] = useState('')

  function commitEntry() {
    const value = entry.trim()
    setEntry('')
    if (!value || dim.values.includes(value)) return
    onSetValues([...dim.values, value])
  }

  return (
    <div className="space-y-1.5 rounded-md border border-border p-2">
      <div className="flex items-center gap-1">
        <input
          value={dim.name}
          onChange={(e) => onRename(e.target.value)}
          className="w-full bg-transparent text-xs font-semibold outline-none focus:bg-primary/5"
        />
        <button
          type="button"
          onClick={onRemove}
          disabled={!canRemove}
          title="Remove dimension"
          className="rounded p-0.5 text-muted-foreground hover:text-destructive disabled:opacity-30 disabled:hover:text-muted-foreground"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
      {dim.values.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {dim.values.map((value, vi) => (
            <span key={vi} className="inline-flex items-center gap-1 rounded bg-muted/60 px-1.5 py-0.5 text-[11px]">
              {value}
              <button
                type="button"
                onClick={() => onSetValues(dim.values.filter((_, i) => i !== vi))}
                className="text-muted-foreground hover:text-destructive"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <input
        value={entry}
        onChange={(e) => setEntry(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commitEntry()
          }
        }}
        onBlur={commitEntry}
        placeholder="add value + Enter"
        className="w-full rounded bg-muted/30 px-1.5 py-1 text-[11px] outline-none focus:bg-primary/5"
      />
    </div>
  )
}

function emptyProfile(): ProjectProfile {
  return {
    projectIntro: '',
    timeGranularity: 'Month',
    modelScope: { dimensions: [{ name: 'Product', values: [] }, { name: 'Channel', values: [] }, { name: 'Platform & Region', values: [] }], rows: [] },
    sourceOrigin: '',
  }
}

/** Cross-product of all dimension value lists → scope rows. */
function crossProduct(scope: ModelScope): string[][] {
  const lists = scope.dimensions.map((d) => (d.values.length ? d.values : ['']))
  return lists.reduce<string[][]>(
    (acc, list) => acc.flatMap((row) => list.map((v) => [...row, v])),
    [[]],
  )
}

export function ProfileEditor() {
  const storeProfile = useSimStore((s) => s.profile)
  const updateProfile = useSimStore((s) => s.updateProfile)
  const [draft, setDraft] = useState<ProjectProfile>(storeProfile ?? emptyProfile())
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  // Re-sync local draft when the store profile changes and there are no pending edits.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (storeProfile && !dirty) setDraft(storeProfile)
  }, [storeProfile, dirty])

  function patch(p: Partial<ProjectProfile>) {
    setDraft((d) => ({ ...d, ...p }))
    setDirty(true)
  }
  function patchScope(p: Partial<ModelScope>) {
    setDraft((d) => ({ ...d, modelScope: { ...d.modelScope, ...p } }))
    setDirty(true)
  }

  async function save() {
    setSaving(true)
    try {
      await updateProfile(draft)
      setDirty(false)
    } finally {
      setSaving(false)
    }
  }

  const scope = draft.modelScope

  function setDimension(di: number, next: Partial<ModelScopeDimension>) {
    patchScope({ dimensions: scope.dimensions.map((d, i) => (i === di ? { ...d, ...next } : d)) })
  }
  function removeDimension(di: number) {
    patchScope({
      dimensions: scope.dimensions.filter((_, i) => i !== di),
      rows: scope.rows.map((r) => r.filter((_, j) => j !== di)),
    })
  }
  function addRow() {
    patchScope({ rows: [...scope.rows, scope.dimensions.map(() => '')] })
  }

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Project Profile</h3>
          <p className="text-[11px] text-muted-foreground">
            Parsed from your materials · {draft.sourceOrigin || 'reference case'} · editable
          </p>
        </div>
        <Button size="sm" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}Save
        </Button>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">Project introduction</label>
        <textarea
          value={draft.projectIntro}
          onChange={(e) => patch({ projectIntro: e.target.value })}
          rows={3}
          className="w-full resize-y rounded-md border border-border bg-background px-2.5 py-1.5 text-[13px] outline-none focus:border-primary"
        />
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-muted-foreground">Time granularity</label>
        <div className="inline-flex rounded-md border border-border p-0.5">
          {TIME_GRANULARITIES.map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => patch({ timeGranularity: g })}
              className={`rounded px-3 py-1 text-xs font-medium ${draft.timeGranularity === g ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* Model-scope matrix builder */}
      <div className="space-y-2 border-t border-border pt-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium text-muted-foreground">Model granularity (scope dimensions)</label>
          <Badge variant="muted">{scope.rows.length} scope rows</Badge>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          {scope.dimensions.map((dim, di) => (
            <DimensionCard
              key={di}
              dim={dim}
              canRemove={scope.dimensions.length > 1}
              onRename={(name) => setDimension(di, { name })}
              onSetValues={(values) => setDimension(di, { values })}
              onRemove={() => removeDimension(di)}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => patchScope({ dimensions: [...scope.dimensions, { name: 'New dimension', values: [] }] })}>
            <Plus />Add dimension
          </Button>
          <Button size="sm" variant="outline" onClick={() => patchScope({ rows: crossProduct(scope) })} disabled={scope.dimensions.length === 0}>
            <Grid3x3 />Generate scope rows
          </Button>
          <Button size="sm" variant="outline" onClick={addRow} disabled={scope.dimensions.length === 0}>
            <Rows3 />Add row
          </Button>
          {scope.rows.length > 0 && (
            <Button size="sm" variant="ghost" onClick={() => patchScope({ rows: [] })}>
              <RotateCcw />Clear rows
            </Button>
          )}
        </div>

        {scope.rows.length > 0 && (
          <div className="max-h-64 overflow-auto rounded-lg border border-border">
            <table className="w-full border-collapse text-[12px]">
              <thead className="sticky top-0 bg-muted/60">
                <tr className="text-left text-muted-foreground">
                  {scope.dimensions.map((d, i) => <th key={i} className="px-2 py-1.5 font-medium">{d.name}</th>)}
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {scope.rows.map((row, ri) => (
                  <tr key={ri} className="border-t border-border">
                    {scope.dimensions.map((_, ci) => (
                      <td key={ci} className="p-0">
                        <input
                          value={row[ci] ?? ''}
                          onChange={(e) => patchScope({ rows: scope.rows.map((r, i) => i === ri ? r.map((c, j) => j === ci ? e.target.value : c) : r) })}
                          className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                        />
                      </td>
                    ))}
                    <td className="text-center">
                      <button type="button" onClick={() => patchScope({ rows: scope.rows.filter((_, i) => i !== ri) })} className="rounded p-1 text-muted-foreground hover:text-destructive">
                        <Trash2 className="size-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  )
}
