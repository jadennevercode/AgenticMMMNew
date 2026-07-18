import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useSimStore } from '../../../store/useSimStore'
import { asDoc, asMasterData, asOlsTree, asReview, asSheet, asSlides } from '../../../lib/artifact-format'
import { BusinessValidationView } from '../validation/BusinessValidationView'
import { MasterDataView } from './MasterDataView'
import { OlsTreeView } from './OlsTreeView'
import { MiniMarkdown } from '../../ui/primitives'
import { cn } from '../../../lib/cn'
import type { ArtifactInstance, DocData, SheetData, SlidesData } from '../../../lib/types'
import { ReviewChartView } from '../charts/ReviewCharts'

/* ── Excel: sheet tabs + editable grid ─────────────────── */
function SheetView({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const editArtifact = useSimStore((s) => s.editArtifact)
  const data = asSheet(inst.body)
  const [active, setActive] = useState(0)
  if (!data?.sheets.length) return null
  const si = Math.min(active, data.sheets.length - 1)
  const sheet = data.sheets[si]

  const commit = (next: SheetData) => editArtifact(inst.id, { body: next })
  const setCell = (ri: number, ci: number, val: string) =>
    commit({
      sheets: data.sheets.map((s, i) =>
        i !== si ? s : { ...s, rows: s.rows.map((r, j) => (j !== ri ? r : r.map((c, k) => (k !== ci ? c : val)))) },
      ),
    })
  const addRow = () =>
    commit({ sheets: data.sheets.map((s, i) => (i !== si ? s : { ...s, rows: [...s.rows, s.columns.map(() => '')] })) })
  const addCol = () =>
    commit({
      sheets: data.sheets.map((s, i) =>
        i !== si ? s : { ...s, columns: [...s.columns, `列${s.columns.length + 1}`], rows: s.rows.map((r) => [...r, '']) },
      ),
    })

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1 border-b border-border px-3 py-1.5">
        {data.sheets.map((s, i) => (
          <button
            key={s.name + i}
            type="button"
            onClick={() => setActive(i)}
            className={cn(
              'rounded-md px-2.5 py-1 text-[12px] transition-colors',
              i === si ? 'bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/60',
            )}
          >
            {s.name}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {(sheet.preRows ?? []).map((r, i) => {
          const text = r.join(' ').trim()
          if (!text) return null
          return (
            <p key={i} className={cn('px-1 leading-snug', i === 0 ? 'text-[13px] font-semibold' : 'text-[11px] text-muted-foreground')}>
              {text}
            </p>
          )
        })}
        <table className="mt-1.5 w-full border-collapse text-[12.5px]">
          <thead>
            <tr>
              <th className="w-8 border border-border bg-muted/60" />
              {sheet.columns.map((c, ci) => (
                <th key={ci} className="border border-border bg-muted/60 px-2 py-1 text-left font-semibold">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sheet.rows.map((r, ri) => (
              <tr key={ri}>
                <td className="border border-border bg-muted/40 px-1 text-center font-mono text-[10px] text-muted-foreground">{ri + 1}</td>
                {sheet.columns.map((_, ci) => (
                  <td key={ci} className="border border-border p-0 align-top">
                    {editing ? (
                      <input
                        value={r[ci] ?? ''}
                        onChange={(e) => setCell(ri, ci, e.target.value)}
                        className="w-full bg-transparent px-2 py-1 outline-none focus:bg-primary/5"
                      />
                    ) : (
                      <span className="block px-2 py-1 leading-snug">{r[ci] ?? ''}</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {editing && (
          <div className="mt-2 flex gap-2">
            <button type="button" onClick={addRow} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] hover:bg-accent">
              <Plus className="size-3" /> Row
            </button>
            <button type="button" onClick={addCol} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] hover:bg-accent">
              <Plus className="size-3" /> Column
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── PPT: slide rail + slide editor ────────────────────── */
function SlidesView({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const editArtifact = useSimStore((s) => s.editArtifact)
  const data = asSlides(inst.body)
  const [active, setActive] = useState(0)
  if (!data?.slides.length) return null
  const si = Math.min(active, data.slides.length - 1)
  const slide = data.slides[si]

  const commit = (next: SlidesData) => editArtifact(inst.id, { body: next })
  const setTitle = (val: string) => commit({ slides: data.slides.map((s, i) => (i !== si ? s : { ...s, title: val })) })
  const setBullet = (bi: number, val: string) =>
    commit({ slides: data.slides.map((s, i) => (i !== si ? s : { ...s, bullets: s.bullets.map((b, j) => (j !== bi ? b : val)) })) })
  const addBullet = () => commit({ slides: data.slides.map((s, i) => (i !== si ? s : { ...s, bullets: [...s.bullets, ''] })) })
  const addSlide = () => {
    commit({ slides: [...data.slides, { title: '新页', bullets: [''] }] })
    setActive(data.slides.length)
  }

  return (
    <div className="flex h-full">
      <div className="w-40 shrink-0 space-y-1.5 overflow-y-auto border-r border-border p-2">
        {data.slides.map((s, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setActive(i)}
            className={cn('block w-full rounded-md border p-2 text-left', i === si ? 'border-primary/50 bg-accent' : 'border-border hover:bg-accent/60')}
          >
            <span className="font-mono text-[9px] text-muted-foreground">{i + 1}</span>
            <span className="mt-0.5 line-clamp-2 text-[11px] font-medium leading-tight">{s.title || '—'}</span>
          </button>
        ))}
        {editing && (
          <button type="button" onClick={addSlide} className="inline-flex w-full items-center justify-center gap-1 rounded-md border border-dashed border-border py-1.5 text-[11px] text-muted-foreground hover:bg-accent">
            <Plus className="size-3" /> Slide
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-5">
        <div className="mx-auto aspect-[16/9] w-full max-w-2xl rounded-lg border border-border bg-card p-6 shadow-sm">
          {editing ? (
            <input value={slide.title} onChange={(e) => setTitle(e.target.value)} className="w-full border-b border-border bg-transparent pb-1.5 text-lg font-semibold outline-none focus:border-primary/50" />
          ) : (
            <h3 className="border-b border-border pb-1.5 text-lg font-semibold">{slide.title}</h3>
          )}
          <ul className="mt-3 space-y-1.5">
            {slide.bullets.map((b, bi) => (
              <li key={bi} className="flex gap-2 text-[13px] leading-relaxed">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
                {editing ? (
                  <input value={b} onChange={(e) => setBullet(bi, e.target.value)} className="min-w-0 flex-1 bg-transparent outline-none focus:bg-primary/5" />
                ) : (
                  <span>{b}</span>
                )}
              </li>
            ))}
          </ul>
          {editing && (
            <button type="button" onClick={addBullet} className="mt-3 inline-flex items-center gap-1 text-[11px] text-primary hover:underline">
              <Plus className="size-3" /> bullet
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Word: editable block document ─────────────────────── */
function DocView({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const editArtifact = useSimStore((s) => s.editArtifact)
  const data = asDoc(inst.body)
  if (!data?.blocks.length) return null
  const commit = (next: DocData) => editArtifact(inst.id, { body: next })
  const setText = (i: number, val: string) => commit({ blocks: data.blocks.map((b, j) => (j !== i ? b : { ...b, text: val })) })
  const addBlock = () => commit({ blocks: [...data.blocks, { type: 'p', text: '' }] })

  const cls: Record<DocData['blocks'][number]['type'], string> = {
    h1: 'text-xl font-semibold',
    h2: 'text-sm font-semibold uppercase tracking-wider text-foreground pt-2',
    p: 'text-[13px] leading-relaxed text-muted-foreground',
    li: 'text-[13px] leading-relaxed text-muted-foreground',
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      <div className="mx-auto max-w-2xl space-y-2 rounded-lg border border-border bg-card px-8 py-6 shadow-sm">
        {data.blocks.map((b, i) => (
          <div key={i} className={b.type === 'li' ? 'flex gap-2' : ''}>
            {b.type === 'li' && <span className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground/50" />}
            {editing ? (
              <input value={b.text} onChange={(e) => setText(i, e.target.value)} className={cn('w-full bg-transparent outline-none focus:bg-primary/5', cls[b.type])} />
            ) : (
              <p className={cls[b.type]}>{b.text}</p>
            )}
          </div>
        ))}
        {editing && (
          <button type="button" onClick={addBlock} className="mt-2 inline-flex items-center gap-1 text-[11px] text-primary hover:underline">
            <Plus className="size-3" /> paragraph
          </button>
        )}
      </div>
    </div>
  )
}

/* ── Markdown ──────────────────────────────────────────── */
function MarkdownView({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const editArtifact = useSimStore((s) => s.editArtifact)
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
      {editing ? (
        <textarea
          value={inst.content}
          onChange={(e) => editArtifact(inst.id, { content: e.target.value })}
          spellCheck={false}
          className="h-full min-h-[320px] w-full resize-none rounded-lg border border-border bg-card px-4 py-3 font-mono text-[12.5px] leading-relaxed outline-none focus:border-primary/50"
        />
      ) : (
        <div className="rounded-lg border border-border bg-card px-4 py-3">
          <MiniMarkdown text={inst.content} />
        </div>
      )}
    </div>
  )
}

/* ── Review: visualized six-step business validation (computed charts) ── */
function ReviewView({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  const editArtifact = useSimStore((s) => s.editArtifact)
  const data = asReview(inst.body)
  if (!data?.steps.length) {
    return (
      <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
        业务检验图表尚未生成 —— 运行 2.32（数据展示）后在此查看分步可视化校验。
      </div>
    )
  }

  const setSignoff = (stepIdx: number, chartIdx: number, value: string) =>
    editArtifact(inst.id, {
      body: {
        steps: data.steps.map((s, i) =>
          i !== stepIdx
            ? s
            : { ...s, charts: s.charts.map((c, j) => (j !== chartIdx ? c : { ...c, signoff: c.signoff === value ? '' : value })) },
        ),
      },
    })

  return (
    <div className="min-h-0 flex-1 space-y-8 overflow-y-auto px-5 py-5">
      {data.steps.map((step, si) => (
        <section key={step.id} aria-labelledby={`${step.id}-h`}>
          <div className="mb-3 border-l-2 border-primary pl-3">
            <h3 id={`${step.id}-h`} className="text-sm font-semibold tracking-tight">{step.title}</h3>
            {step.intro && <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{step.intro}</p>}
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {step.charts.map((chart, ci) => (
              <figure key={chart.id} className="rounded-xl border border-border bg-card p-3.5 shadow-sm">
                <figcaption className="mb-1 flex items-start justify-between gap-2">
                  <span className="text-[13px] font-medium leading-snug">{chart.title}</span>
                  {chart.unit && <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{chart.unit}</span>}
                </figcaption>
                <ReviewChartView chart={chart} />
                {chart.interpretation && <p className="mt-2 text-xs leading-relaxed">{chart.interpretation}</p>}
                {chart.conclusion && (
                  <p className="mt-1 text-[11px] italic leading-relaxed text-muted-foreground">{chart.conclusion}</p>
                )}
                <div className="mt-2.5 flex items-center justify-between gap-2 border-t border-border/60 pt-2">
                  <div className="flex flex-wrap gap-1">
                    {(chart.factors ?? []).map((f) => (
                      <span key={f} className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{f}</span>
                    ))}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <span className="text-[10px] text-muted-foreground">Sign-off</span>
                    {(['yes', 'no'] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        disabled={!editing}
                        onClick={() => setSignoff(si, ci, v)}
                        className={cn(
                          'rounded px-2 py-0.5 text-[11px] font-medium transition-colors',
                          chart.signoff === v
                            ? v === 'yes'
                              ? 'bg-emerald-500/15 text-emerald-600'
                              : 'bg-rose-500/15 text-rose-600'
                            : 'border border-border text-muted-foreground hover:bg-muted',
                          !editing && 'cursor-not-allowed opacity-60',
                        )}
                      >
                        {v === 'yes' ? 'Y' : 'N'}
                      </button>
                    ))}
                  </div>
                </div>
              </figure>
            ))}
          </div>
          {(step.tables ?? []).map((tbl) => (
            <div key={tbl.title} className="mt-4 overflow-hidden rounded-xl border border-border bg-card">
              <div className="border-b border-border bg-muted/40 px-3.5 py-2 text-[13px] font-medium">{tbl.title}</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-left text-muted-foreground">
                      {tbl.columns.map((c) => (
                        <th key={c} className="px-3 py-1.5 font-medium whitespace-nowrap">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tbl.rows.map((r, ri) => (
                      <tr key={ri} className="border-b border-border/50 last:border-0">
                        {tbl.columns.map((_, ci) => (
                          <td key={ci} className="px-3 py-1.5 align-top leading-relaxed">{r[ci] ?? ''}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {tbl.note && <p className="px-3.5 py-2 text-[11px] text-muted-foreground">{tbl.note}</p>}
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}

/** Dispatch to the renderer for the artifact's format */
export function ArtifactCanvas({ inst, editing }: { inst: ArtifactInstance; editing: boolean }) {
  switch (inst.format) {
    case 'sheet':
      return <SheetView inst={inst} editing={editing} />
    case 'slides':
      return <SlidesView inst={inst} editing={editing} />
    case 'doc':
      return <DocView inst={inst} editing={editing} />
    case 'review':
      return <ReviewView inst={inst} editing={editing} />
    case 'validation':
      return <BusinessValidationView inst={inst} editing={editing} />
    case 'olsTree':
      // Legacy projects saved a sheet body before the olsTree upgrade — fall back
      // to the sheet grid until they re-run 2.5.
      return asOlsTree(inst.body) ? <OlsTreeView inst={inst} /> : <SheetView inst={inst} editing={editing} />
    case 'masterData':
      // Same story: projects assembled before the funnel view still hold a sheet body.
      return asMasterData(inst.body) ? <MasterDataView inst={inst} /> : <SheetView inst={inst} editing={editing} />
    default:
      return <MarkdownView inst={inst} editing={editing} />
  }
}
