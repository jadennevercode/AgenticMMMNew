/**
 * UI language layer (decision D4, 08 §7.3):
 * Internal architecture vocabulary stays in code/docs; UI copy uses plain
 * product English. Artifact/business CONTENT may be Chinese; product chrome
 * is English only.
 */

import {
  AlertTriangle,
  ArrowLeftRight,
  Cpu,
  Circle,
  CircleDot,
  Lightbulb,
  RotateCcw,
  Upload,
  UserCheck,
  type LucideIcon,
} from 'lucide-react'
import type { AutomationClass, ArtifactState, DeliverableState, InsightKind, TaskStatus } from './types'

/**
 * Terms that must never appear in user-visible copy.
 * Checked against src strings by scripts/copy-check.mjs (Phase C).
 */
export const BANNED_UI_TERMS = [
  'proposal',
  'gate',
  'insight engine',
  'automation class',
  'cognitive task',
  'mechanical task',
  'human-only',
  'context bus',
  'lineage triple',
  'dual-plane',
  'process plane',
  'collaboration plane',
  'deterministic engine',
  'copilot',
] as const

/** Behavior badge per automation class — describes behavior, not taxonomy */
export const CLASS_LABEL: Record<AutomationClass, { label: string; hint: string; icon: LucideIcon; ai?: boolean }> = {
  M: { label: 'Runs automatically', hint: 'Computed by rules — repeatable, no review needed', icon: Cpu },
  A: { label: 'AI draft', hint: 'AI drafts it; spot-check and adjust as needed', icon: CircleDot, ai: true },
  C: { label: 'AI analysis', hint: 'AI reasons and suggests; review before it counts', icon: Lightbulb, ai: true },
  H: { label: 'Your decision', hint: 'Only a person can settle this', icon: UserCheck },
}

/** Human-input task badge — distinct from a decision */
export const INPUT_BADGE = { label: 'Your input', hint: 'Provide material before the team can continue', icon: Upload }

/** Export/send task badge */
export const EXPORT_BADGE = { label: 'Export & send', hint: 'Download a template and send it out, then mark it done', icon: Upload }

export const STATUS_LABEL: Record<TaskStatus, { label: string; color: string }> = {
  pending: { label: 'Waiting', color: 'var(--color-status-pending)' },
  ready: { label: 'Queued', color: 'var(--color-status-ready)' },
  running: { label: 'In progress', color: 'var(--color-status-running)' },
  awaiting_human: { label: 'Needs decision', color: 'var(--color-status-waiting)' },
  done: { label: 'Done', color: 'var(--color-status-done)' },
}

export const ARTIFACT_STATE_LABEL: Record<ArtifactState, { label: string; variant: 'muted' | 'outline' | 'success' | 'locked' }> = {
  draft: { label: 'Draft', variant: 'muted' },
  proposed: { label: 'Awaiting review', variant: 'outline' },
  confirmed: { label: 'Confirmed', variant: 'success' },
  frozen: { label: 'Locked', variant: 'locked' },
}

/** Deliverable lifecycle on the artifact board — plain product words */
export const DELIVERABLE_STATE: Record<DeliverableState, { label: string; color: string; hint: string }> = {
  locked: { label: 'Locked', color: 'var(--color-status-pending)', hint: 'Waiting on earlier deliverables' },
  queued: { label: 'Queued', color: 'var(--color-status-ready)', hint: 'Ready to start' },
  building: { label: 'Building', color: 'var(--color-status-running)', hint: 'The team is working on it' },
  'needs-you': { label: 'Needs you', color: 'var(--color-status-waiting)', hint: 'A step needs your input or decision' },
  ready: { label: 'Ready', color: 'var(--color-status-done)', hint: 'Produced — review it' },
  confirmed: { label: 'Confirmed', color: 'var(--color-status-done)', hint: 'Locked in' },
}

export const INSIGHT_KIND_LABEL: Record<InsightKind, { label: string; icon: LucideIcon }> = {
  connection: { label: 'Connected the dots', icon: ArrowLeftRight },
  gap: { label: 'Coverage gap', icon: Circle },
  conflict: { label: 'Contradiction', icon: AlertTriangle },
  reference: { label: 'From past projects', icon: RotateCcw },
}

/** Wording for AI certainty — numbers stay internal */
export function confidenceWording(confidence: number): string {
  if (confidence >= 0.85) return 'High confidence'
  if (confidence >= 0.7) return 'Fairly confident'
  return 'Uncertain — please double-check'
}
