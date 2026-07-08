import type { ArtifactBody, ArtifactFormat } from './types'
import { asSheet, bodyToMarkdown } from './artifact-format'

// SheetJS is heavy (~400 kB) — load it on demand so it stays out of the main bundle.
type XLSXModule = typeof import('xlsx')
let xlsxPromise: Promise<XLSXModule> | null = null
function loadXLSX(): Promise<XLSXModule> {
  if (!xlsxPromise) xlsxPromise = import('xlsx')
  return xlsxPromise
}

/**
 * Universal artifact export. Sheet artifacts become a real multi-sheet .xlsx
 * (via SheetJS); every other format becomes a Markdown file. Triggers a browser
 * download with a filesystem-safe filename.
 */

function safeName(name: string): string {
  return name.replace(/[^\w一-龥 .-]+/g, '_').replace(/\s+/g, '_').slice(0, 80) || 'export'
}

/** Build a workbook from a sheet body. Sheet names are capped to Excel's 31 chars. */
function toWorkbook(XLSX: XLSXModule, body: ArtifactBody): import('xlsx').WorkBook {
  const sheet = asSheet(body)
  const wb = XLSX.utils.book_new()
  const used = new Set<string>()
  const sheets = sheet?.sheets.length ? sheet.sheets : [{ name: 'Sheet1', columns: [], rows: [] }]
  sheets.forEach((s, idx) => {
    const preRows = ('preRows' in s && s.preRows) ? s.preRows : []
    const aoa = [...preRows, s.columns, ...s.rows.map((r) => s.columns.map((_, i) => r[i] ?? ''))]
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    // Merge each non-empty banner (preRow) across the full column width, mirroring
    // the reference workbook's A1:G1 / A2:G2 merges.
    const width = Math.max(s.columns.length, 1)
    if (preRows.length && width > 1) {
      const merges = preRows
        .map((r, ri) => ({ row: ri, hasText: r.some((c) => String(c ?? '').trim() !== '') }))
        .filter((m) => m.hasText)
        .map((m) => ({ s: { r: m.row, c: 0 }, e: { r: m.row, c: width - 1 } }))
      if (merges.length) ws['!merges'] = [...(ws['!merges'] ?? []), ...merges]
    }
    let name = (s.name || `Sheet${idx + 1}`).replace(/[\\/?*[\]:]/g, ' ').slice(0, 31) || `Sheet${idx + 1}`
    while (used.has(name.toLowerCase())) name = `${name.slice(0, 28)}_${idx}`
    used.add(name.toLowerCase())
    XLSX.utils.book_append_sheet(wb, ws, name)
  })
  return wb
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export interface ExportableArtifact {
  name: string
  format: ArtifactFormat
  body?: ArtifactBody
  content: string
}

const XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

/** Export any artifact to a downloaded file (.xlsx for sheets, .md otherwise). */
export async function exportArtifact(inst: ExportableArtifact): Promise<void> {
  const base = safeName(inst.name)
  if (inst.format === 'sheet' && asSheet(inst.body)) {
    const XLSX = await loadXLSX()
    const wb = toWorkbook(XLSX, inst.body as ArtifactBody)
    const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' }) as ArrayBuffer
    downloadBlob(new Blob([out], { type: XLSX_MIME }), `${base}.xlsx`)
    return
  }
  const md = bodyToMarkdown(inst.format, inst.body, inst.content)
  downloadBlob(new Blob([md], { type: 'text/markdown;charset=utf-8' }), `${base}.md`)
}

/**
 * Download the Data Request as a ZIP of one .xlsx workbook per L3 (one sheet per
 * L4), built by the backend. `url` is the backend export endpoint.
 */
export async function exportDataRequestZip(url: string): Promise<void> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Data Request export failed: ${res.status}`)
  const blob = await res.blob()
  downloadBlob(blob, 'Data_Request.zip')
}

/** Export a plain 2D table (used by the Knowledge template editor). */
export async function exportTable(name: string, columns: string[], rows: string[][]): Promise<void> {
  const XLSX = await loadXLSX()
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet([columns, ...rows])
  XLSX.utils.book_append_sheet(wb, ws, name.slice(0, 31) || 'Template')
  const out = XLSX.write(wb, { bookType: 'xlsx', type: 'array' }) as ArrayBuffer
  downloadBlob(new Blob([out], { type: XLSX_MIME }), `${safeName(name)}.xlsx`)
}
