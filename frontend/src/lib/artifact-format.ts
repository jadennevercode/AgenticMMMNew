import type { ArtifactBody, ArtifactFormat, DocData, ReviewData, SheetData, SlidesData } from './types'

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
