import { useCallback, useEffect, useState } from 'react'

import { api } from '../api/client'
import { useSimStore, type BackendAssignment } from '../store/useSimStore'
import type { DataIntakeStatus } from '../lib/types'

/**
 * The 2.1 data gate's verdict, straight from the backend.
 *
 * Returns `null` for every gate that is NOT the data gate, so callers keep their
 * original file-presence rule for the S1 upload gates.
 *
 * Why this exists: the gate used to be judged twice with different rules. The
 * server accepted a resolved FactorTree↔DataAssets mapping; the UI insisted on
 * parsed files in the assignment's Project-Folder category. Data-Engine uploads
 * land under `raw_data`, not `data`, so a fully mapped project satisfied the
 * server and stayed permanently blocked on screen. There is now one judge, and
 * this hook is how the UI asks it.
 *
 * It re-reads on every state tick (`tick` advances as the run loop steps) so the
 * button unblocks as soon as the last factor row is resolved elsewhere.
 */
export function useIntakeStatus(assignment: BackendAssignment): DataIntakeStatus | null {
  const pid = useSimStore((s) => s.activeProjectId)
  const tick = useSimStore((s) => s.tick)
  const [status, setStatus] = useState<DataIntakeStatus | null>(null)

  const isDataGate = Boolean(assignment.requiresMapping || assignment.requiresManifest)

  const refresh = useCallback(() => {
    if (!pid || !isDataGate) return
    let cancelled = false
    void api
      .getFactorMap(pid)
      .then((m) => {
        if (!cancelled) setStatus(m.intake ?? null)
      })
      .catch(() => {
        // A failed probe must not silently unblock the gate: leaving `status`
        // null falls the caller back to the file-presence rule, which is the
        // conservative answer.
        if (!cancelled) setStatus(null)
      })
    return () => {
      cancelled = true
    }
  }, [pid, isDataGate])

  useEffect(() => refresh(), [refresh, tick])

  return isDataGate ? status : null
}
