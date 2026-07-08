/**
 * Bulk import for Knowledge-pack sections — parse an uploaded spreadsheet (.xlsx /
 * .xlsm / .csv) into typed rows so a section can be populated at once instead of
 * one row at a time.
 *
 * Column order mirrors `exportSection` (lib/export.ts) exactly, so a section can
 * be exported, edited in Excel, and re-imported round-trip. Parsing is lenient:
 * a header row is auto-detected and dropped, blank rows are skipped, and merged
 * L1–L4 cells in a factor tree are forward-filled (same rule as the backend
 * ingest loader).
 */
import type {
  FactorTreeRow,
  InterviewCategory,
  InterviewQuestion,
  KnowledgeNote,
  KnowledgeTemplate,
  RuleCategory,
  RuleRow,
  RuleSeverity,
  TemplateKind,
} from './types'

// SheetJS is heavy (~400 kB) and already lazy-loaded by lib/export.ts — reuse the
// same on-demand import so it stays out of the main bundle.
type XLSXModule = typeof import('xlsx')
let xlsxPromise: Promise<XLSXModule> | null = null
function loadXLSX(): Promise<XLSXModule> {
  if (!xlsxPromise) xlsxPromise = import('xlsx')
  return xlsxPromise
}

/** File extensions accepted by the import picker. */
export const IMPORT_ACCEPT = '.xlsx,.xlsm,.csv'

function newId(prefix: string): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? `${prefix}-${crypto.randomUUID().slice(0, 8)}`
    : `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e4)}`
}

/** Read the first non-empty worksheet as a trimmed array-of-arrays of strings. */
async function parseSheet(file: File): Promise<string[][]> {
  const XLSX = await loadXLSX()
  const buf = await file.arrayBuffer()
  const wb = XLSX.read(buf, { type: 'array' })
  const sheetName = wb.SheetNames[0]
  if (!sheetName) return []
  const ws = wb.Sheets[sheetName]
  const aoa = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, blankrows: false, defval: '' })
  return aoa.map((row) => row.map((cell) => (cell == null ? '' : String(cell).trim())))
}

/** True if `row` looks like a header (first cell matches any expected column name). */
function isHeaderRow(row: string[], headers: string[]): boolean {
  const set = new Set(headers.map((h) => h.toLowerCase()))
  return row.slice(0, headers.length).some((c) => set.has(c.toLowerCase()))
}

function dropHeader(rows: string[][], headers: string[]): string[][] {
  return rows.length && isHeaderRow(rows[0], headers) ? rows.slice(1) : rows
}

const col = (row: string[], i: number): string => (row[i] ?? '').trim()

// ── factor tree: L1 · L2 · L3 · L4 · Indicator (merged L1–L4 forward-filled) ──
function toFactorRows(rows: string[][]): FactorTreeRow[] {
  const body = dropHeader(rows, ['L1', 'L2', 'L3', 'L4', 'Indicator'])
  const carry = ['', '', '', '']
  const out: FactorTreeRow[] = []
  for (const row of body) {
    if (!row.some((c) => c)) continue
    for (let i = 0; i < 4; i += 1) {
      const v = col(row, i)
      if (v) {
        carry[i] = v
        for (let j = i + 1; j < 4; j += 1) carry[j] = '' // deeper levels reset
      }
    }
    const indicator = col(row, 4)
    if (!indicator && !carry[3]) continue
    out.push({ l1: carry[0], l2: carry[1], l3: carry[2], l4: carry[3], indicator })
  }
  return out
}

// ── interview: Category · Role · Question ─────────────────────────────────────
const INTERVIEW_CATEGORIES: InterviewCategory[] = ['Leadership', 'Management', 'Operation', 'Data']
function toInterviewCategory(v: string): InterviewCategory {
  const hit = INTERVIEW_CATEGORIES.find((c) => c.toLowerCase() === v.toLowerCase())
  return hit ?? 'Operation'
}
function toInterviewQuestions(rows: string[][]): InterviewQuestion[] {
  const body = dropHeader(rows, ['Category', 'Role', 'Question'])
  const out: InterviewQuestion[] = []
  for (const row of body) {
    const question = col(row, 2)
    if (!question && !col(row, 1)) continue
    out.push({ category: toInterviewCategory(col(row, 0)), role: col(row, 1), question })
  }
  return out
}

// ── rules: Category · Severity · Name · Detail ────────────────────────────────
const RULE_CATEGORY: Record<string, RuleCategory> = {
  quality: 'quality', 'data quality': 'quality', 数据质量: 'quality',
  statistical: 'statistical', statistics: 'statistical', 统计: 'statistical',
  technical: 'technical', 技术: 'technical',
  business: 'business', 业务: 'business',
}
const RULE_SEVERITY: Record<string, RuleSeverity> = {
  block: 'block', warn: 'warn', warning: 'warn', info: 'info',
}
function toRuleRows(rows: string[][]): RuleRow[] {
  const body = dropHeader(rows, ['Category', 'Severity', 'Name', 'Detail'])
  const out: RuleRow[] = []
  for (const row of body) {
    const name = col(row, 2)
    const detail = col(row, 3)
    if (!name && !detail) continue
    out.push({
      id: newId('rule'),
      category: RULE_CATEGORY[col(row, 0).toLowerCase()] ?? 'business',
      severity: RULE_SEVERITY[col(row, 1).toLowerCase()] ?? 'warn',
      name,
      detail,
    })
  }
  return out
}

// ── notes: Title · Body · Tags (tags split on comma or slash) ─────────────────
function toKnowledgeNotes(rows: string[][]): KnowledgeNote[] {
  const body = dropHeader(rows, ['Title', 'Body', 'Tags'])
  const out: KnowledgeNote[] = []
  for (const row of body) {
    const title = col(row, 0)
    const noteBody = col(row, 1)
    if (!title && !noteBody) continue
    const tags = col(row, 2).split(/[,/]/).map((t) => t.trim()).filter(Boolean)
    out.push({ id: newId('note'), title, body: noteBody, tags })
  }
  return out
}

/** Parsed rows for exactly one section kind — a `KnowledgeTemplate` patch. */
export type ImportPatch = Partial<
  Pick<KnowledgeTemplate, 'factorRows' | 'interviewQuestions' | 'ruleRows' | 'knowledgeNotes'>
>

/** Count of rows in an import patch (for user feedback). */
export function patchRowCount(patch: ImportPatch): number {
  return (
    (patch.factorRows?.length ?? 0) +
    (patch.interviewQuestions?.length ?? 0) +
    (patch.ruleRows?.length ?? 0) +
    (patch.knowledgeNotes?.length ?? 0)
  )
}

/** Parse an uploaded file into rows for the given section kind. */
export async function parseSectionFile(kind: TemplateKind, file: File): Promise<ImportPatch> {
  const rows = await parseSheet(file)
  switch (kind) {
    case 'factor_tree':
      return { factorRows: toFactorRows(rows) }
    case 'interview':
      return { interviewQuestions: toInterviewQuestions(rows) }
    case 'rules':
      return { ruleRows: toRuleRows(rows) }
    case 'industry_knowledge':
    case 'general_knowledge':
      return { knowledgeNotes: toKnowledgeNotes(rows) }
    default:
      return {}
  }
}
