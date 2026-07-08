import { useRef, useState, type ChangeEvent } from 'react'
import { Copy, Download, Loader2, Save, Trash2, Upload } from 'lucide-react'
import { api } from '../../api/client'
import { exportTable } from '../../lib/export'
import { IMPORT_ACCEPT, parseSectionFile, patchRowCount } from '../../lib/knowledge-import'
import type { KnowledgeTemplate } from '../../lib/types'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { FactorTreeEditor } from './editors/FactorTreeEditor'
import { InterviewEditor } from './editors/InterviewEditor'
import { RulesEditor } from './editors/RulesEditor'
import { KnowledgeNotesEditor } from './editors/KnowledgeNotesEditor'

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Request failed'
}

function exportSection(t: KnowledgeTemplate): void {
  switch (t.kind) {
    case 'factor_tree':
      void exportTable(t.name, ['L1', 'L2', 'L3', 'L4', 'Indicator'],
        t.factorRows.map((r) => [r.l1, r.l2, r.l3, r.l4, r.indicator]))
      break
    case 'interview':
      void exportTable(t.name, ['Category', 'Role', 'Question'],
        t.interviewQuestions.map((q) => [q.category, q.role, q.question]))
      break
    case 'rules':
      void exportTable(t.name, ['Category', 'Severity', 'Name', 'Detail'],
        t.ruleRows.map((r) => [r.category, r.severity, r.name, r.detail]))
      break
    default:
      void exportTable(t.name, ['Title', 'Body', 'Tags'],
        t.knowledgeNotes.map((n) => [n.title, n.body, n.tags.join(' / ')]))
  }
}

interface Props {
  /** The section template to edit. Pass a `key={template.id}` from the parent so
   *  switching sections remounts the editor with a fresh draft. */
  template: KnowledgeTemplate
  /** Reload the templates list after a save / clone / delete. */
  onChanged: (selectId?: string) => void
}

/** Edits one knowledge-pack section: name + kind-appropriate body + actions. */
export function SectionEditorCard({ template, onChanged }: Props) {
  const [draft, setDraft] = useState<KnowledgeTemplate>(() => structuredClone(template))
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function patch(p: Partial<KnowledgeTemplate>) {
    setDraft((d) => ({ ...d, ...p }))
    setDirty(true)
  }

  async function onImportFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // reset so re-selecting the same file re-fires change
    if (!file) return
    setImporting(true)
    setError(null)
    try {
      const parsed = await parseSectionFile(draft.kind, file)
      if (patchRowCount(parsed) === 0) {
        setError('No rows found — check the file columns match the exported format.')
        return
      }
      // Append imported rows to the draft (non-destructive); user reviews then Saves.
      setDraft((d) => ({
        ...d,
        factorRows: parsed.factorRows ? [...d.factorRows, ...parsed.factorRows] : d.factorRows,
        interviewQuestions: parsed.interviewQuestions
          ? [...d.interviewQuestions, ...parsed.interviewQuestions] : d.interviewQuestions,
        ruleRows: parsed.ruleRows ? [...d.ruleRows, ...parsed.ruleRows] : d.ruleRows,
        knowledgeNotes: parsed.knowledgeNotes
          ? [...d.knowledgeNotes, ...parsed.knowledgeNotes] : d.knowledgeNotes,
      }))
      setDirty(true)
    } catch (err) {
      setError(errMsg(err))
    } finally {
      setImporting(false)
    }
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const saved = await api.saveTemplate(draft)
      onChanged(saved.id)
    } catch (e) {
      setError(errMsg(e))
    } finally {
      setSaving(false)
    }
  }

  async function clone() {
    setError(null)
    try {
      const copy = await api.cloneTemplate(draft.id, `${draft.name} (custom)`)
      onChanged(copy.id)
    } catch (e) {
      setError(errMsg(e))
    }
  }

  async function remove() {
    if (draft.builtin) return
    setError(null)
    try {
      await api.deleteTemplate(draft.id)
      onChanged()
    } catch (e) {
      setError(errMsg(e))
    }
  }

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">{error}</p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={draft.name}
          onChange={(e) => patch({ name: e.target.value })}
          disabled={draft.builtin}
          className="min-w-0 flex-1 rounded-md border border-border px-2.5 py-1.5 text-sm font-semibold outline-none focus:border-primary disabled:opacity-70"
        />
        {draft.builtin
          ? <Badge variant="muted">Built-in · clone to edit</Badge>
          : <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">v{draft.version}</span>}
      </div>

      <div className="border-t border-border pt-3">
        {draft.kind === 'factor_tree' && (
          <FactorTreeEditor rows={draft.factorRows} onChange={(factorRows) => patch({ factorRows })} />
        )}
        {draft.kind === 'interview' && (
          <InterviewEditor questions={draft.interviewQuestions} onChange={(interviewQuestions) => patch({ interviewQuestions })} />
        )}
        {draft.kind === 'rules' && (
          <RulesEditor rules={draft.ruleRows} onChange={(ruleRows) => patch({ ruleRows })} />
        )}
        {(draft.kind === 'industry_knowledge' || draft.kind === 'general_knowledge') && (
          <KnowledgeNotesEditor notes={draft.knowledgeNotes} onChange={(knowledgeNotes) => patch({ knowledgeNotes })} />
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
        <Button size="sm" onClick={() => void save()} disabled={!dirty || saving || draft.builtin}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}Save
        </Button>
        <Button size="sm" variant="outline" onClick={() => void clone()}><Copy />Clone</Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={IMPORT_ACCEPT}
          className="hidden"
          onChange={(e) => void onImportFile(e)}
        />
        <Button
          size="sm"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={importing || draft.builtin}
          title="Bulk-add rows from an Excel or CSV file"
        >
          {importing ? <Loader2 className="animate-spin" /> : <Upload />}Import
        </Button>
        <Button size="sm" variant="outline" onClick={() => exportSection(draft)}><Download />Export</Button>
        {!draft.builtin && (
          <Button size="sm" variant="ghost" onClick={() => void remove()} className="text-destructive"><Trash2 />Delete</Button>
        )}
        {draft.builtin && <span className="text-[11px] text-muted-foreground">Built-in templates are read-only — clone to customize.</span>}
      </div>
    </div>
  )
}
