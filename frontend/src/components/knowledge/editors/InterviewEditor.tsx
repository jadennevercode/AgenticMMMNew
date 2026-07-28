import { Plus, Trash2 } from 'lucide-react'
import type { InterviewCategory, InterviewQuestion } from '../../../lib/types'
import { Button } from '../../ui/button'

const CATEGORIES: InterviewCategory[] = ['Leadership', 'Management', 'Operation', 'Data']

interface Props {
  questions: InterviewQuestion[]
  onChange: (questions: InterviewQuestion[]) => void
}

/** Interview-outline editor: questions grouped by category, per-role rows. */
export function InterviewEditor({ questions, onChange }: Props) {
  const update = (i: number, patch: Partial<InterviewQuestion>) =>
    onChange(questions.map((q, idx) => (idx === i ? { ...q, ...patch } : q)))
  const remove = (i: number) => onChange(questions.filter((_, idx) => idx !== i))
  const add = (category: InterviewCategory) =>
    onChange([...questions, { category, role: '', question: '' }])

  return (
    <div className="space-y-4">
      {CATEGORIES.map((cat) => {
        const items = questions.map((q, i) => ({ q, i })).filter(({ q }) => q.category === cat)
        return (
          <div key={cat} className="space-y-1.5">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {cat}
                <span className="ml-2 font-mono text-[10px]">{items.length}</span>
              </h4>
              <Button size="sm" variant="ghost" onClick={() => add(cat)}><Plus className="size-3" />Add</Button>
            </div>
            {cat === 'Data' && (
              <p className="text-[11px] text-muted-foreground">
                Data questions are generated from the project's Factor Tree at runtime; template-level items are optional.
              </p>
            )}
            <div className="space-y-1">
              {items.map(({ q, i }) => (
                <div key={i} className="flex items-start gap-2 rounded-md border border-border p-1.5">
                  <input
                    value={q.role}
                    onChange={(e) => update(i, { role: e.target.value })}
                    placeholder="role"
                    className="w-28 shrink-0 rounded bg-muted/40 px-1.5 py-1 text-[11px] outline-none focus:bg-primary/5"
                  />
                  <textarea
                    value={q.question}
                    onChange={(e) => update(i, { question: e.target.value })}
                    placeholder="question"
                    rows={1}
                    className="min-h-[28px] flex-1 resize-y rounded bg-transparent px-1.5 py-1 text-[12px] outline-none focus:bg-primary/5"
                  />
                  <button type="button" onClick={() => remove(i)} className="rounded p-1 text-muted-foreground hover:text-destructive">
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
