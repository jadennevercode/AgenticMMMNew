import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle, ArrowLeft, BrainCircuit, CheckCircle2, Eye, EyeOff, Loader2, Mic, Save,
} from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import {
  emptyModelConfig, isLlmConfigured, MODEL_PLACEHOLDERS,
  type GlobalModelConfig, type ServiceCreds,
} from '../../lib/types'
import { Card } from '../ui/card'
import { Button } from '../ui/button'

const inputCls =
  'w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-[13px] outline-none focus:border-primary'

interface FieldProps { label: string; children: React.ReactNode; hint?: string }
function Field({ label, children, hint }: FieldProps) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

interface CredFieldsProps {
  values: ServiceCreds
  placeholders: { baseUrl: string; model: string }
  onPatch: (p: Partial<ServiceCreds>) => void
}

/** Three free-text credential fields (API key / base URL / model), shared by LLM + ASR. */
function CredFields({ values, placeholders, onPatch }: CredFieldsProps) {
  const [showKey, setShowKey] = useState(false)
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="API Key" hint="The real key — stored on the server, shared by all projects.">
        <div className="relative">
          <input
            className={`${inputCls} pr-9`}
            type={showKey ? 'text' : 'password'}
            value={values.apiKey}
            placeholder="sk-…"
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => onPatch({ apiKey: e.target.value })}
          />
          <button
            type="button"
            aria-label={showKey ? 'Hide key' : 'Show key'}
            className="absolute inset-y-0 right-2 flex items-center text-muted-foreground hover:text-foreground"
            onClick={() => setShowKey((v) => !v)}
          >
            {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
          </button>
        </div>
      </Field>
      <Field label="Model name">
        <input
          className={inputCls}
          value={values.model}
          placeholder={placeholders.model}
          spellCheck={false}
          onChange={(e) => onPatch({ model: e.target.value })}
        />
      </Field>
      <Field label="Base URL" hint="OpenAI-compatible endpoint (no /chat/completions suffix).">
        <input
          className={inputCls}
          value={values.baseUrl}
          placeholder={placeholders.baseUrl}
          spellCheck={false}
          onChange={(e) => onPatch({ baseUrl: e.target.value })}
        />
      </Field>
    </div>
  )
}

export function ModelConfigEditor() {
  const modelConfig = useSimStore((s) => s.modelConfig)
  const loadModelConfig = useSimStore((s) => s.loadModelConfig)

  // Load the global config once. Remount the form (via key) once it arrives so the
  // draft seeds from the real values without a setState-in-effect.
  useEffect(() => { void loadModelConfig() }, [loadModelConfig])
  return (
    <ConfigForm key={modelConfig ? 'loaded' : 'empty'} initial={modelConfig ?? emptyModelConfig()} />
  )
}

function ConfigForm({ initial }: { initial: GlobalModelConfig }) {
  const updateModelConfig = useSimStore((s) => s.updateModelConfig)

  const [draft, setDraft] = useState<GlobalModelConfig>(initial)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  function patchLlm(p: Partial<ServiceCreds>) {
    setDraft((d) => ({ ...d, llm: { ...d.llm, ...p } }))
    setDirty(true)
  }
  function patchAsr(p: Partial<ServiceCreds>) {
    setDraft((d) => ({ ...d, asr: { ...d.asr, ...p } }))
    setDirty(true)
  }

  async function save() {
    setSaving(true)
    try {
      await updateModelConfig(draft)
      setDirty(false)
    } finally {
      setSaving(false)
    }
  }

  const llmReady = isLlmConfigured(draft)

  return (
    <Card className="space-y-5 p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold">Model Service</h3>
          <p className="text-[11px] text-muted-foreground">
            Enter your LLM &amp; ASR credentials once — they apply to <strong>all</strong> projects.
          </p>
        </div>
        <Button size="sm" onClick={() => void save()} disabled={!dirty || saving}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}Save
        </Button>
      </div>

      {/* LLM — required */}
      <section className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BrainCircuit className="size-4 text-primary" />
            <h4 className="text-[13px] font-semibold">LLM (reasoning &amp; narrative)</h4>
            <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">Required</span>
          </div>
          {llmReady
            ? <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600"><CheckCircle2 className="size-3" /> Configured</span>
            : <span className="inline-flex items-center gap-1 text-[11px] text-amber-600"><AlertTriangle className="size-3" /> Fill key, base URL &amp; model</span>}
        </div>
        <CredFields values={draft.llm} placeholders={MODEL_PLACEHOLDERS.llm} onPatch={patchLlm} />
      </section>

      {/* ASR — optional */}
      <section className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex items-center gap-2">
          <Mic className="size-4 text-primary" />
          <h4 className="text-[13px] font-semibold">ASR (interview audio transcription)</h4>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">Optional</span>
        </div>
        <CredFields values={draft.asr} placeholders={MODEL_PLACEHOLDERS.asr} onPatch={patchAsr} />
        <p className="text-[11px] text-muted-foreground">
          Audio uploaded to Interview Recordings is transcribed by this model (task 1.4b · ≤25 MB per file)
          before the AI digests it. Leave the key blank to disable ASR; text minutes still work.
        </p>
      </section>
    </Card>
  )
}

/** In-project Settings tab (rendered inside the app shell). Edits the same global
 * config, with a note that it applies to every project. */
export function ProjectSettingsInShell() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div>
        <h2 className="text-lg font-semibold">Settings</h2>
        <p className="text-sm text-muted-foreground">
          Model-service credentials are global — these settings apply to all projects.
        </p>
      </div>
      <ModelConfigEditor />
    </div>
  )
}

/** Standalone global Settings screen (top-level /settings route). */
export default function GlobalSettingsView() {
  const navigate = useNavigate()
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <button
        type="button"
        onClick={() => navigate('/')}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" /> Projects
      </button>
      <div>
        <h2 className="text-lg font-semibold">Settings</h2>
        <p className="text-sm text-muted-foreground">Global model-service configuration, shared by every project.</p>
      </div>
      <ModelConfigEditor />
    </div>
  )
}
