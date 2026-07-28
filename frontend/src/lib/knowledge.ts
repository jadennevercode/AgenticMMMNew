/**
 * Knowledge-pack helpers — turn the flat KnowledgeTemplate list (one per section
 * kind) into industry-first "packs", and describe the editable sections.
 *
 * A pack = the set of industry-scoped templates sharing one (L1, L2). The
 * cross-industry general-knowledge section is handled separately.
 */
import { GENERAL_INDUSTRY, type KnowledgeTemplate, type TemplateKind } from './types'
import { industryPath } from './industries'

/** The editable sections inside an industry pack, in display order. */
export const PACK_SECTION_KINDS: TemplateKind[] = [
  'factor_tree',
  'interview',
  'rules',
  'industry_knowledge',
]

export const SECTION_META: Record<
  TemplateKind,
  { label: string; blurb: string }
> = {
  factor_tree: { label: 'Factor tree', blurb: 'L1–L4 hierarchy and indicators — the baseline factors for project modeling' },
  interview: { label: 'Interview', blurb: 'Layered interview questions, grouped by role / level' },
  rules: { label: 'Rules', blurb: 'Data quality / statistical / technical / business validation rules' },
  industry_knowledge: { label: 'Knowledge', blurb: 'Industry know-how notes for the AI to ground on' },
  general_knowledge: { label: 'General', blurb: 'Cross-industry methods and style, applied to every project' },
}

export interface Pack {
  l1: string
  l2?: string
  /** Stable identity for selection: `${l1}|${l2 ?? ''}`. */
  key: string
  /** Human-readable industry breadcrumb. */
  label: string
  /** One template per present section kind. */
  sections: Partial<Record<TemplateKind, KnowledgeTemplate>>
}

export function packKey(l1: string, l2?: string | null): string {
  return `${l1}|${l2 ?? ''}`
}

/** Resolve an industry (L1/L2) to a breadcrumb label, falling back to codes. */
function packLabel(l1: string, l2?: string): string {
  // industryPath needs a full L1/L2/L3 ref; for a pack we only have L1/L2, so we
  // derive labels from the L2 node directly and fall back to raw codes.
  const path = industryPath({ l1, l2: l2 ?? '', l3: '' })
  if (path !== '—') return path.split(' › ').slice(0, 2).join(' › ')
  return l2 ? `${l1} › ${l2}` : l1
}

/** A custom (cloned) section shadows the built-in of the same kind; among equals,
 *  the higher version wins. Returns true if `next` should replace `cur`. */
function preferSection(cur: KnowledgeTemplate | undefined, next: KnowledgeTemplate): boolean {
  if (!cur) return true
  if (cur.builtin !== next.builtin) return cur.builtin // replace builtin with custom
  return next.version > cur.version
}

/** Group industry-scoped templates into packs (excludes general knowledge). */
export function buildPacks(templates: KnowledgeTemplate[]): Pack[] {
  const byKey = new Map<string, Pack>()
  for (const t of templates) {
    if (t.kind === 'general_knowledge' || t.industryL1 === GENERAL_INDUSTRY) continue
    const key = packKey(t.industryL1, t.industryL2)
    let pack = byKey.get(key)
    if (!pack) {
      pack = {
        l1: t.industryL1,
        l2: t.industryL2 || undefined,
        key,
        label: packLabel(t.industryL1, t.industryL2 || undefined),
        sections: {},
      }
      byKey.set(key, pack)
    }
    if (preferSection(pack.sections[t.kind], t)) pack.sections[t.kind] = t
  }
  return [...byKey.values()].sort((a, b) => a.label.localeCompare(b.label))
}

/** Count of editable items across a pack's sections (for navigator badges). */
export function packItemCount(pack: Pack): number {
  let n = 0
  for (const t of Object.values(pack.sections)) {
    if (!t) continue
    n += t.factorRows.length + t.interviewQuestions.length + t.ruleRows.length + t.knowledgeNotes.length
  }
  return n
}
