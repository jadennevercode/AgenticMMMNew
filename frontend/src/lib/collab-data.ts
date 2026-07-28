import type { AssistantScriptEntry, InsightBlueprint, ProposalBlueprint } from './types'

/**
 * Collaboration-plane content is now produced at runtime by the backend and
 * arrives via /api/state → store.proposals / store.insights / store.assistant.
 *
 * These exports are intentionally EMPTY stubs kept only so the type re-exports
 * resolve; no mock content is shipped as a runtime data source.
 */

export const PROPOSALS: ProposalBlueprint[] = []

export const INSIGHTS: InsightBlueprint[] = []

export const ASSISTANT_SCRIPT: AssistantScriptEntry[] = []

export const ASSISTANT_FALLBACK =
  'I could not reach the project service. Try again, or open the asset and ask from there.'
