import type {
  ArtifactBody,
  ArtifactFormat,
  DocData,
  MasterData,
  OlsTreeData,
  ReviewData,
  SheetData,
  SlidesData,
  ValidationReviewData,
} from './types'

/**
 * Format helpers — project a structured artifact body to a markdown preview
 * (so the Assets library / evidence previews keep working), export to a
 * faithful text equivalent, and apply chat-driven edits per format.
 */

export const FORMAT_LABEL: Record<ArtifactFormat, string> = {
  sheet: 'Excel',
  slides: 'PPT',
  doc: 'Word',
  markdown: 'Markdown',
  review: 'Review',
  validation: 'Validation',
  olsTree: 'OLS',
  masterData: 'Master Data',
}

export function asSheet(body?: ArtifactBody): SheetData | null {
  return body && 'sheets' in body ? body : null
}
export function asSlides(body?: ArtifactBody): SlidesData | null {
  return body && 'slides' in body ? body : null
}
export function asDoc(body?: ArtifactBody): DocData | null {
  return body && 'blocks' in body ? body : null
}
export function asReview(body?: ArtifactBody): ReviewData | null {
  return body && 'steps' in body ? body : null
}
export function asValidation(body?: ArtifactBody): ValidationReviewData | null {
  return body && 'groups' in body && 'kpiMetric' in body ? body : null
}
export function asOlsTree(body?: ArtifactBody): OlsTreeData | null {
  return body && 'tree' in body && 'objects' in body ? body : null
}
export function asMasterData(body?: ArtifactBody): MasterData | null {
  return body && 'funnel' in body && 'adopted' in body ? body : null
}

function fmtNum(v: number | null, digits = 2): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits)
}

/** Render a body to markdown for previews / fallback display */
export function bodyToMarkdown(format: ArtifactFormat, body: ArtifactBody | undefined, content: string): string {
  if (format === 'markdown' || !body) return content
  const sheet = asSheet(body)
  if (sheet) {
    return sheet.sheets
      .map((s) => {
        const banner = (s.preRows ?? []).map((r) => r.join(' ').trim()).filter(Boolean)
        const head = `| ${s.columns.join(' | ')} |`
        const sep = `| ${s.columns.map(() => '---').join(' | ')} |`
        const rows = s.rows.map((r) => `| ${s.columns.map((_, i) => r[i] ?? '').join(' | ')} |`)
        return `## ${s.name}\n${[...banner, head, sep, ...rows].join('\n')}`
      })
      .join('\n\n')
  }
  const slides = asSlides(body)
  if (slides) {
    return slides.slides
      .map((sl, i) => `## ${i + 1}. ${sl.title}\n${sl.bullets.map((b) => `- ${b}`).join('\n')}`)
      .join('\n\n')
  }
  const doc = asDoc(body)
  if (doc) {
    return doc.blocks
      .map((b) => (b.type === 'h1' ? `# ${b.text}` : b.type === 'h2' ? `## ${b.text}` : b.type === 'li' ? `- ${b.text}` : b.text))
      .join('\n')
  }
  const review = asReview(body)
  if (review) {
    return review.steps
      .map((st) => {
        const charts = st.charts
          .map((c) => {
            const series = c.series.map((s) => `${s.name}: ${s.data.join(', ')}`).join('\n')
            const lines = [`### ${c.title}`, c.interpretation ?? '', c.conclusion ? `> ${c.conclusion}` : '', series]
            return lines.filter(Boolean).join('\n')
          })
          .join('\n\n')
        return `## ${st.title}\n${st.intro ?? ''}\n\n${charts}`
      })
      .join('\n\n')
  }
  const validation = asValidation(body)
  if (validation) {
    const header = `# Business Validation\nKPI: ${validation.kpiMetric || '—'}`
    const groups = validation.groups
      .map((g) => {
        const sign = g.signoff === 'yes' ? '✓ signed off' : g.signoff === 'no' ? '✗ rejected' : 'pending'
        return `## ${[g.l1, g.l2, g.l3].filter(Boolean).join(' › ')}\n${g.interpretation}\n> Indicators: ${g.defaultIndicators.join(', ') || '—'} · Sign-off: ${sign}`
      })
      .join('\n\n')
    return `${header}\n\n${groups}`
  }
  const ols = asOlsTree(body)
  if (ols) {
    const objs = ols.objects
      .map((o) =>
        o.error
          ? `- **${o.object}**: ${o.error}`
          : `- **${o.object}** — R² ${fmtNum(o.r2)}, MAPE ${fmtNum(o.mape, 1)}%, DW ${fmtNum(o.durbinWatson)}, baseline ${fmtNum(o.baselinePct, 1)}%${o.redFlags.length ? ` · ${o.redFlags.length} red flag(s)` : ''}`,
      )
      .join('\n')
    const cols = ['Path', 'Indicator', 'Coef', 't', 'ROI', 'ROI band', 'Contribution', 'Contribution band', 'Status']
    const head = `| ${cols.join(' | ')} |`
    const sep = `| ${cols.map(() => '---').join(' | ')} |`
    const rows = ols.tree.map((r) => {
      const path = [r.l1, r.l2, r.l3, r.l4].filter(Boolean).join(' › ')
      const cells = [
        path, r.indicator, fmtNum(r.coef), fmtNum(r.tValue),
        fmtNum(r.roi), r.roiRange || '—',
        r.contribution === null ? '—' : `${fmtNum(r.contribution)}%`, r.contributionRange || '—',
        r.status + (r.flagReason ? ` (${r.flagReason})` : ''),
      ]
      return `| ${cells.join(' | ')} |`
    })
    const summary = `In model ${ols.summary.inModel} · In range ${ols.summary.inRange} · Flagged ${ols.summary.flagged} · No benchmark ${ols.summary.noBenchmark} · Not in model ${ols.summary.notInModel} · Dropped ${ols.summary.dropped}`
    return `# OLS Regression Test\n\n## Model objects\n${objs}\n\n## Factor tree results\n${summary}\n\n${[head, sep, ...rows].join('\n')}`
  }
  const master = asMasterData(body)
  if (master) {
    // The wide table itself is a live per-slice query, so the projection carries
    // what is durable: what got in, what did not, and which layer decided.
    const objs = master.objects
      .map((o) => (o.error
        ? `- **${o.object}**: ${o.error}`
        : `- **${o.object}** — ${o.features} features over ${o.months} periods · Y: ${o.y}`))
      .join('\n')
    const funnel = [
      '| Layer | Task | Intake | Rejected | Survivors |',
      '| --- | --- | --- | --- | --- |',
      ...master.funnel.map((f) => `| ${f.label} | ${f.task} | ${f.intake} | ${f.rejected} | ${f.survivors} |`),
    ].join('\n')
    const adopted = master.adopted
      .map((a) => `- ${[a.l1, a.l2, a.l3, a.l4].filter(Boolean).join(' › ')} — ${a.indicator}`)
      .join('\n') || '- (none)'
    const rejected = master.rejected
      .map((r) => `- ${[r.l4, r.indicator].filter(Boolean).join(' · ')} — rejected at ${r.rejectedAt}: ${r.reason}`)
      .join('\n') || '- (none)'
    return [
      '# Master Data',
      `\n## Model objects\n${objs}`,
      `\n## Filter funnel\n${funnel}`,
      `\n## Adopted indicators (${master.adopted.length})\n${adopted}`,
      `\n## Rejected indicators (${master.rejected.length})\n${rejected}`,
    ].join('\n')
  }
  return content
}

/** Faithful text export: CSV for sheets (active sheet), markdown otherwise */
export function exportText(format: ArtifactFormat, body: ArtifactBody | undefined, content: string): { ext: string; text: string } {
  const sheet = asSheet(body)
  if (format === 'sheet' && sheet) {
    const csv = sheet.sheets
      .map((s) => {
        const esc = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
        const pre = (s.preRows ?? []).map((r) => r.map(esc).join(','))
        const lines = [s.columns, ...s.rows].map((r) => s.columns.map((_, i) => esc(r[i] ?? '')).join(','))
        return `# ${s.name}\n${[...pre, ...lines].join('\n')}`
      })
      .join('\n\n')
    return { ext: 'csv', text: csv }
  }
  return { ext: 'md', text: bodyToMarkdown(format, body, content) }
}

/** Apply a chat instruction as a tracked change appropriate to the format */
export function applyChatEdit(
  format: ArtifactFormat,
  body: ArtifactBody | undefined,
  content: string,
  instruction: string,
): { body?: ArtifactBody; content: string } {
  const text = instruction.trim()
  const sheet = asSheet(body)
  if (format === 'sheet' && sheet && sheet.sheets.length) {
    const sheets = sheet.sheets.map((s, idx) =>
      idx === 0 ? { ...s, rows: [...s.rows, padRow([text], s.columns.length)] } : s,
    )
    const next: SheetData = { sheets }
    return { body: next, content: bodyToMarkdown('sheet', next, content) }
  }
  const slides = asSlides(body)
  if (format === 'slides' && slides && slides.slides.length) {
    const last = slides.slides.length - 1
    const next: SlidesData = {
      slides: slides.slides.map((sl, i) => (i === last ? { ...sl, bullets: [...sl.bullets, text] } : sl)),
    }
    return { body: next, content: bodyToMarkdown('slides', next, content) }
  }
  const doc = asDoc(body)
  if (format === 'doc' && doc) {
    const next: DocData = { blocks: [...doc.blocks, { type: 'p', text }] }
    return { body: next, content: bodyToMarkdown('doc', next, content) }
  }
  // markdown
  const heading = '## Edits'
  const entry = `- ${text}`
  const nextContent = content.includes(heading) ? `${content}\n${entry}` : `${content.trimEnd()}\n\n${heading}\n${entry}`
  return { content: nextContent }
}

function padRow(values: string[], width: number): string[] {
  const r = values.slice(0, width)
  while (r.length < width) r.push('')
  return r
}
