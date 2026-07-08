import { useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { api } from '../../api/client'
import { GENERAL_INDUSTRY, type KnowledgeTemplate, type ProjectListItem } from '../../lib/types'
import { buildPacks, packKey, SECTION_META } from '../../lib/knowledge'
import { SectionHeader } from '../ui/primitives'
import { Card } from '../ui/card'
import { Button } from '../ui/button'
import { IndustryNavigator, type Selection } from './IndustryNavigator'
import { PackDetail } from './PackDetail'
import { SectionEditorCard } from './SectionEditorCard'

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Request failed'
}

function emptyGeneral(): KnowledgeTemplate {
  return {
    id: '', kind: 'general_knowledge', name: 'General MMM Knowledge',
    industryL1: GENERAL_INDUSTRY, industryL2: undefined, version: 1, builtin: false,
    factorRows: [], interviewQuestions: [], ruleRows: [], knowledgeNotes: [], updatedAt: '',
  }
}

export default function KnowledgeView() {
  const [templates, setTemplates] = useState<KnowledgeTemplate[]>([])
  const [projects, setProjects] = useState<ProjectListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selection, setSelection] = useState<Selection>({ type: 'general' })
  const [creatingGeneral, setCreatingGeneral] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [tpls, projs] = await Promise.all([api.listTemplates(), api.listProjects()])
      setTemplates(tpls)
      setProjects(projs)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload()
  }, [reload])

  const packs = useMemo(() => buildPacks(templates), [templates])
  const general = useMemo(() => templates.find((t) => t.kind === 'general_knowledge'), [templates])

  // Derive (don't store) a valid selection: a pack that no longer exists (e.g. its
  // last section was deleted) falls back to general knowledge for this render.
  const effectiveSelection: Selection =
    selection.type === 'pack' && !packs.some((p) => p.key === selection.key)
      ? { type: 'general' }
      : selection
  const activePack =
    effectiveSelection.type === 'pack' ? packs.find((p) => p.key === effectiveSelection.key) : undefined

  async function newPack(l1: string, l2: string | undefined) {
    // Creating the first (factor_tree) section materializes the pack.
    try {
      await api.saveTemplate({
        id: '', kind: 'factor_tree', name: SECTION_META.factor_tree.label,
        industryL1: l1, industryL2: l2, version: 1, builtin: false,
        factorRows: [], interviewQuestions: [], ruleRows: [], knowledgeNotes: [], updatedAt: '',
      })
      await reload()
      setSelection({ type: 'pack', key: packKey(l1, l2) })
    } catch (e) {
      setError(errMsg(e))
    }
  }

  async function createGeneral() {
    setCreatingGeneral(true)
    try {
      await api.saveTemplate(emptyGeneral())
      await reload()
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setCreatingGeneral(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-6">
      <SectionHeader kicker="What the team knows" title="Knowledge" />

      {error && (
        <p className="mb-4 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">{error}</p>
      )}

      {loading ? (
        <div className="grid place-items-center py-24 text-muted-foreground">
          <Loader2 className="size-5 animate-spin" />
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
          <IndustryNavigator packs={packs} selection={effectiveSelection} onSelect={setSelection} onNewPack={newPack} />

          <div>
            {effectiveSelection.type === 'general' ? (
              general ? (
                <Card className="space-y-3 p-4">
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Cross-industry</p>
                    <h3 className="text-lg font-semibold">General knowledge</h3>
                    <p className="mt-1 text-[12px] text-muted-foreground">{SECTION_META.general_knowledge.blurb}</p>
                  </div>
                  <div className="border-t border-border pt-3">
                    <SectionEditorCard key={general.id} template={general} onChanged={reload} />
                  </div>
                </Card>
              ) : (
                <Card className="flex flex-col items-center gap-3 p-10 text-center">
                  <p className="text-sm text-muted-foreground">No general-knowledge section yet.</p>
                  <Button size="sm" onClick={() => void createGeneral()} disabled={creatingGeneral}>
                    {creatingGeneral ? <Loader2 className="animate-spin" /> : <Plus />}Create general knowledge
                  </Button>
                </Card>
              )
            ) : activePack ? (
              <PackDetail pack={activePack} projects={projects} onChanged={reload} />
            ) : (
              <Card className="grid place-items-center p-10 text-sm text-muted-foreground">
                Select a pack to edit.
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
