import { Plus, Trash2 } from 'lucide-react'
import type { KnowledgeNote } from '../../../lib/types'
import { Button } from '../../ui/button'

function newId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID ? `note-${crypto.randomUUID().slice(0, 8)}` : `note-${Date.now()}`
}

interface Props {
  notes: KnowledgeNote[]
  onChange: (notes: KnowledgeNote[]) => void
}

/** Free-form knowledge-note editor: title · body · comma-separated tags. */
export function KnowledgeNotesEditor({ notes, onChange }: Props) {
  const update = (i: number, patch: Partial<KnowledgeNote>) =>
    onChange(notes.map((n, idx) => (idx === i ? { ...n, ...patch } : n)))
  const remove = (i: number) => onChange(notes.filter((_, idx) => idx !== i))
  const add = () => onChange([...notes, { id: newId(), title: '', body: '', tags: [] }])

  return (
    <div className="space-y-2">
      <div className="grid gap-2.5 sm:grid-cols-2">
        {notes.map((n, i) => (
          <div key={n.id || i} className="flex flex-col rounded-lg border border-border p-3">
            <div className="flex items-start gap-2">
              <input
                value={n.title}
                onChange={(e) => update(i, { title: e.target.value })}
                placeholder="Title"
                className="min-w-0 flex-1 bg-transparent text-sm font-semibold outline-none placeholder:text-muted-foreground/60 focus:bg-primary/5"
              />
              <button type="button" onClick={() => remove(i)} className="rounded p-0.5 text-muted-foreground hover:text-destructive">
                <Trash2 className="size-3.5" />
              </button>
            </div>
            <textarea
              value={n.body}
              onChange={(e) => update(i, { body: e.target.value })}
              placeholder="Body / method / definition"
              rows={3}
              className="mt-1.5 w-full flex-1 resize-y rounded-md bg-muted/30 px-2 py-1.5 text-[12.5px] leading-relaxed outline-none focus:bg-primary/5"
            />
            <input
              value={n.tags.join(', ')}
              onChange={(e) =>
                update(i, { tags: e.target.value.split(',').map((t) => t.trim()).filter(Boolean) })}
              placeholder="Tags (comma-separated)"
              className="mt-1.5 w-full rounded-md bg-transparent px-2 py-1 font-mono text-[11px] text-muted-foreground outline-none focus:bg-primary/5"
            />
          </div>
        ))}
      </div>
      {notes.length === 0 && (
        <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
          No notes yet — add the first note.
        </p>
      )}
      <Button size="sm" variant="outline" onClick={add}><Plus />Add note</Button>
    </div>
  )
}
