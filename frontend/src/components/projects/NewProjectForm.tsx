import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Sparkles, X } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import {
  isValidIndustry,
  l1Options,
  l2Options,
  l3Options,
  type IndustryRef,
} from '../../lib/industries'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'

interface NewProjectFormProps {
  onClose: () => void
}

const labelCls = 'text-xs font-medium text-foreground'
const fieldCls =
  'h-9 w-full rounded-md border border-border bg-card px-3 text-sm outline-none transition-colors focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-50'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className={labelCls}>
        {label}
        {hint && <span className="ml-1.5 font-normal text-muted-foreground">{hint}</span>}
      </span>
      {children}
    </label>
  )
}

export default function NewProjectForm({ onClose }: NewProjectFormProps) {
  const navigate = useNavigate()
  const createProject = useSimStore((s) => s.createProject)

  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [l1, setL1] = useState('')
  const [l2, setL2] = useState('')
  const [l3, setL3] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [touched, setTouched] = useState(false)

  const l2List = useMemo(() => (l1 ? l2Options(l1) : []), [l1])
  const l3List = useMemo(() => (l1 && l2 ? l3Options(l1, l2) : []), [l1, l2])

  const industry: Partial<IndustryRef> = { l1, l2, l3 }
  const industryOk = isValidIndustry(industry)
  const nameOk = name.trim().length > 0
  const brandOk = brand.trim().length > 0
  const valid = nameOk && brandOk && industryOk

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!valid || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const id = await createProject({ name: name.trim(), brand: brand.trim(), industry: industry as IndustryRef })
      navigate(`/p/${id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="new-project-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border bg-card px-6 py-5">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-primary/10 text-primary">
              <Sparkles className="size-[18px]" />
            </span>
            <div>
              <h2 id="new-project-title" className="text-base font-semibold tracking-tight">
                新建项目
              </h2>
              <p className="text-xs text-muted-foreground">填写基础信息，进入工作台</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-6 py-5">
          <Field label="项目名称">
            <input
              className={cn(fieldCls, touched && !nameOk && 'border-destructive')}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：脉动 MMM POC 2026"
              autoFocus
            />
          </Field>

          <Field label="品牌名称">
            <input
              className={cn(fieldCls, touched && !brandOk && 'border-destructive')}
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="如：脉动 Mizone"
            />
          </Field>

          <Field label="行业" hint="L1 → L2 → L3">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <select
                className={cn(fieldCls, touched && !l1 && 'border-destructive')}
                value={l1}
                onChange={(e) => {
                  setL1(e.target.value)
                  setL2('')
                  setL3('')
                }}
              >
                <option value="">大行业</option>
                {l1Options().map((n) => (
                  <option key={n.code} value={n.code}>
                    {n.label}
                  </option>
                ))}
              </select>

              <select
                className={cn(fieldCls, touched && l1 && !l2 && 'border-destructive')}
                value={l2}
                disabled={!l1}
                onChange={(e) => {
                  setL2(e.target.value)
                  setL3('')
                }}
              >
                <option value="">品类</option>
                {l2List.map((n) => (
                  <option key={n.code} value={n.code}>
                    {n.label}
                  </option>
                ))}
              </select>

              <select
                className={cn(fieldCls, touched && l2 && !l3 && 'border-destructive')}
                value={l3}
                disabled={!l2}
                onChange={(e) => setL3(e.target.value)}
              >
                <option value="">子类</option>
                {l3List.map((n) => (
                  <option key={n.code} value={n.code}>
                    {n.label}
                  </option>
                ))}
              </select>
            </div>
          </Field>

          {error && (
            <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>
              取消
            </Button>
            <Button type="submit" disabled={!valid || submitting}>
              {submitting && <Loader2 className="animate-spin" />}
              {submitting ? '创建中…' : '创建项目'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
