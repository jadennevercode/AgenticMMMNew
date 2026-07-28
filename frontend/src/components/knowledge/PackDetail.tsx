import { useMemo, useState } from 'react'
import { Check, Loader2, Plus, Rocket } from 'lucide-react'
import { api } from '../../api/client'
import { PACK_SECTION_KINDS, SECTION_META, type Pack } from '../../lib/knowledge'
import type { KnowledgeTemplate, ProjectListItem, TemplateKind } from '../../lib/types'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'
import { SectionEditorCard } from './SectionEditorCard'

function emptyTemplate(kind: TemplateKind, l1: string, l2?: string): KnowledgeTemplate {
  return {
    id: '', kind, name: SECTION_META[kind].label, industryL1: l1, industryL2: l2,
    version: 1, builtin: false,
    factorRows: [], interviewQuestions: [], ruleRows: [], knowledgeNotes: [], updatedAt: '',
  }
}

function sectionItemCount(t: KnowledgeTemplate): number {
  return t.factorRows.length + t.interviewQuestions.length + t.ruleRows.length + t.knowledgeNotes.length
}

interface Props {
  pack: Pack
  projects: ProjectListItem[]
  onChanged: (selectId?: string) => void
}

export function PackDetail({ pack, projects, onChanged }: Props) {
  const firstPresent = PACK_SECTION_KINDS.find((k) => pack.sections[k]) ?? 'factor_tree'
  const [activeKind, setActiveKind] = useState<TemplateKind>(firstPresent)
  const [creating, setCreating] = useState(false)

  const active = pack.sections[activeKind]

  async function createSection() {
    setCreating(true)
    try {
      const saved = await api.saveTemplate(emptyTemplate(activeKind, pack.l1, pack.l2))
      onChanged(saved.id)
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="space-y-4">
      <PackHeader pack={pack} projects={projects} />

      {/* section tabs */}
      <div className="flex flex-wrap gap-1.5">
        {PACK_SECTION_KINDS.map((kind) => {
          const tpl = pack.sections[kind]
          const isActive = activeKind === kind
          return (
            <button
              key={kind}
              type="button"
              onClick={() => setActiveKind(kind)}
              className={cn('inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors',
                isActive ? 'border-primary bg-primary/5 text-foreground' : 'border-border text-muted-foreground hover:border-primary/40')}
            >
              {SECTION_META[kind].label}
              {tpl
                ? <span className="font-mono text-[10px] text-muted-foreground">{sectionItemCount(tpl)}</span>
                : <span className="text-[10px] text-muted-foreground/50">—</span>}
            </button>
          )
        })}
      </div>

      <p className="text-[12px] text-muted-foreground">{SECTION_META[activeKind].blurb}</p>

      {active ? (
        <Card className="p-4">
          <SectionEditorCard key={active.id} template={active} onChanged={onChanged} />
        </Card>
      ) : (
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <p className="text-sm text-muted-foreground">
            This pack has no <span className="font-medium text-foreground">{SECTION_META[activeKind].label}</span> section yet.
          </p>
          <Button size="sm" onClick={() => void createSection()} disabled={creating}>
            {creating ? <Loader2 className="animate-spin" /> : <Plus />}Create {SECTION_META[activeKind].label}
          </Button>
        </Card>
      )}
    </div>
  )
}

/* ── Pack header: breadcrumb + apply-to-project ─────────── */
function PackHeader({ pack, projects }: { pack: Pack; projects: ProjectListItem[] }) {
  const matching = useMemo(
    () => projects.filter((p) => p.industry.l1 === pack.l1 && (!pack.l2 || p.industry.l2 === pack.l2)),
    [projects, pack],
  )
  const [target, setTarget] = useState('')
  const [applying, setApplying] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Default the target to the first industry-matching project.
  const effectiveTarget = target || matching[0]?.id || ''

  async function apply() {
    if (!effectiveTarget) return
    setApplying(true)
    setError(null)
    setDone(false)
    try {
      await api.applyPack(effectiveTarget, { industryL1: pack.l1, industryL2: pack.l2 })
      setDone(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Apply failed')
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Industry pack</p>
          <h3 className="text-lg font-semibold">{pack.label}</h3>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={effectiveTarget}
            onChange={(e) => { setTarget(e.target.value); setDone(false) }}
            disabled={matching.length === 0}
            className="rounded-md border border-border bg-background px-2 py-1.5 text-xs outline-none disabled:opacity-50"
          >
            {matching.length === 0 && <option value="">No matching project</option>}
            {matching.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Button size="sm" variant="outline" onClick={() => void apply()} disabled={!effectiveTarget || applying}>
            {applying ? <Loader2 className="animate-spin" /> : done ? <Check className="text-success" /> : <Rocket />}
            {done ? 'Applied' : 'Apply to project'}
          </Button>
        </div>
      </div>
      <p className="text-[12px] text-muted-foreground">
        Editing here updates the reusable pack. <span className="font-medium">Apply to project</span> refreshes that
        project's factor tree from this pack — your accepted / rejected factors are preserved.
      </p>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
