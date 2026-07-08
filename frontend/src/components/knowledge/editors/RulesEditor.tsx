import { Plus, Trash2 } from 'lucide-react'
import type { RuleCategory, RuleRow, RuleSeverity } from '../../../lib/types'
import { Button } from '../../ui/button'
import { cn } from '../../../lib/cn'

const CATEGORIES: { value: RuleCategory; label: string }[] = [
  { value: 'quality', label: 'Data quality' },
  { value: 'statistical', label: 'Statistical' },
  { value: 'technical', label: 'Technical' },
  { value: 'business', label: 'Business' },
]

const SEVERITIES: { value: RuleSeverity; label: string; cls: string }[] = [
  { value: 'block', label: 'Block', cls: 'text-destructive' },
  { value: 'warn', label: 'Warn', cls: 'text-amber-600' },
  { value: 'info', label: 'Info', cls: 'text-muted-foreground' },
]

function newId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID ? `rule-${crypto.randomUUID().slice(0, 8)}` : `rule-${Date.now()}`
}

interface Props {
  rules: RuleRow[]
  onChange: (rules: RuleRow[]) => void
}

/** Validation / business-rule editor: category · severity · name · detail. */
export function RulesEditor({ rules, onChange }: Props) {
  const update = (i: number, patch: Partial<RuleRow>) =>
    onChange(rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  const remove = (i: number) => onChange(rules.filter((_, idx) => idx !== i))
  const add = () =>
    onChange([...rules, { id: newId(), category: 'business', name: '', detail: '', severity: 'warn' }])

  return (
    <div className="space-y-2">
      <div className="space-y-2">
        {rules.map((r, i) => (
          <div key={r.id || i} className="rounded-lg border border-border p-2.5">
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={r.category}
                onChange={(e) => update(i, { category: e.target.value as RuleCategory })}
                className="rounded-md border border-border bg-background px-2 py-1 text-[11px] outline-none"
              >
                {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
              <select
                value={r.severity}
                onChange={(e) => update(i, { severity: e.target.value as RuleSeverity })}
                className={cn('rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium outline-none',
                  SEVERITIES.find((s) => s.value === r.severity)?.cls)}
              >
                {SEVERITIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
              <input
                value={r.name}
                onChange={(e) => update(i, { name: e.target.value })}
                placeholder="rule name"
                className="min-w-0 flex-1 rounded-md border border-border px-2 py-1 text-[12px] font-medium outline-none focus:border-primary"
              />
              <button type="button" onClick={() => remove(i)} className="rounded p-1 text-muted-foreground hover:text-destructive">
                <Trash2 className="size-3.5" />
              </button>
            </div>
            <textarea
              value={r.detail}
              onChange={(e) => update(i, { detail: e.target.value })}
              placeholder="Rule detail / threshold"
              rows={2}
              className="mt-2 w-full resize-y rounded-md bg-muted/30 px-2 py-1.5 text-[12px] leading-relaxed outline-none focus:bg-primary/5"
            />
          </div>
        ))}
        {rules.length === 0 && (
          <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            No rules yet — add the first rule.
          </p>
        )}
      </div>
      <Button size="sm" variant="outline" onClick={add}><Plus />Add rule</Button>
    </div>
  )
}
