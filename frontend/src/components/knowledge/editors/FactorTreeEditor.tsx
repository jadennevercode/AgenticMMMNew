import { ChevronDown, ChevronUp, Plus, Trash2 } from 'lucide-react'
import type { FactorTreeRow } from '../../../lib/types'
import { Button } from '../../ui/button'

const COLS: { key: keyof FactorTreeRow; label: string }[] = [
  { key: 'l1', label: 'L1' },
  { key: 'l2', label: 'L2' },
  { key: 'l3', label: 'L3' },
  { key: 'l4', label: 'L4' },
  { key: 'indicator', label: 'Indicator' },
]

const EMPTY_ROW: FactorTreeRow = { l1: '', l2: '', l3: '', l4: '', indicator: '' }

interface Props {
  rows: FactorTreeRow[]
  onChange: (rows: FactorTreeRow[]) => void
}

/** Friendly inline table editor: per-cell edit, add / delete / reorder rows. */
export function FactorTreeEditor({ rows, onChange }: Props) {
  const update = (i: number, key: keyof FactorTreeRow, val: string) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)))
  const remove = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const add = () => onChange([...rows, { ...EMPTY_ROW }])
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir
    if (j < 0 || j >= rows.length) return
    const next = [...rows]
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="bg-muted/50 text-left text-muted-foreground">
              <th className="w-8" />
              {COLS.map((c) => (
                <th key={c.key} className="px-2 py-1.5 font-medium">{c.label}</th>
              ))}
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-border group">
                <td className="px-1 text-center align-middle">
                  <span className="font-mono text-[10px] text-muted-foreground/60">{i + 1}</span>
                </td>
                {COLS.map((c) => (
                  <td key={c.key} className="p-0">
                    <input
                      value={r[c.key]}
                      onChange={(e) => update(i, c.key, e.target.value)}
                      className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                    />
                  </td>
                ))}
                <td className="whitespace-nowrap px-1 text-right opacity-40 transition-opacity group-hover:opacity-100">
                  <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="rounded p-0.5 text-muted-foreground hover:text-primary disabled:opacity-30">
                    <ChevronUp className="size-3.5" />
                  </button>
                  <button type="button" onClick={() => move(i, 1)} disabled={i === rows.length - 1} className="rounded p-0.5 text-muted-foreground hover:text-primary disabled:opacity-30">
                    <ChevronDown className="size-3.5" />
                  </button>
                  <button type="button" onClick={() => remove(i)} className="rounded p-0.5 text-muted-foreground hover:text-destructive">
                    <Trash2 className="size-3.5" />
                  </button>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLS.length + 2} className="px-2 py-6 text-center text-muted-foreground">
                  No factors yet — add the first row.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Button size="sm" variant="outline" onClick={add}><Plus />Add factor</Button>
    </div>
  )
}
