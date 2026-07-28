import { useEffect } from 'react'
import { useSimStore, currentStage } from '../../store/useSimStore'
import { ARTIFACTS, ARTIFACT_MAP } from '../../lib/artifacts-data'
import { artifactForTask, deliverableState } from '../../lib/artifact-graph'
import { StageSpine } from './StageSpine'
import { ArtifactColumn } from './ArtifactColumn'
import { ArtifactDetail } from './ArtifactDetail'

/**
 * Project = artifact-driven workspace, read as the hierarchy:
 *   Stage (spine, top) → Artifacts (column, left) → the build process (detail).
 * Activity + Assistant live in the floating dock (see AppShell).
 */
export default function ProjectView() {
  const tasks = useSimStore((s) => s.tasks)
  const artifacts = useSimStore((s) => s.artifacts)
  const viewedStageId = useSimStore((s) => s.viewedStageId)
  const selectedAssetId = useSimStore((s) => s.selectedAssetId)
  const selectAsset = useSimStore((s) => s.selectAsset)
  const setViewedStage = useSimStore((s) => s.setViewedStage)
  const selectedTaskId = useSimStore((s) => s.selectedTaskId)
  const selectTask = useSimStore((s) => s.selectTask)

  // Cross-navigation from the Workflow Canvas: a task selection focuses its artifact.
  useEffect(() => {
    if (!selectedTaskId) return
    const aid = artifactForTask(selectedTaskId)
    if (aid) {
      const stage = ARTIFACT_MAP.get(aid)?.stage
      if (stage) setViewedStage(stage === currentStage(tasks) ? null : stage)
      selectAsset(aid)
    }
    selectTask(null)
  }, [selectedTaskId, tasks, selectAsset, setViewedStage, selectTask])

  const stageId = viewedStageId ?? currentStage(tasks)
  const stageItems = ARTIFACTS.filter((a) => a.stage === stageId && !a.internal)
  const producedById = new Map(artifacts.map((a) => [a.id, a]))

  // Focus: the picked artifact if it's in this stage, else auto-focus what needs you.
  const inStage = stageItems.some((a) => a.id === selectedAssetId)
  const autoFocus =
    stageItems.find((a) => deliverableState(a.id, tasks, producedById.get(a.id)?.state) === 'needs-you') ??
    stageItems.find((a) => deliverableState(a.id, tasks, producedById.get(a.id)?.state) === 'building') ??
    stageItems.find((a) => producedById.has(a.id)) ??
    stageItems[0]
  const focusId = (inStage ? selectedAssetId : autoFocus?.id) ?? null

  const onPick = (id: string) => {
    const stage = ARTIFACT_MAP.get(id)?.stage
    if (stage) setViewedStage(stage === currentStage(tasks) ? null : stage)
    selectAsset(id)
  }

  return (
    <div className="flex flex-col lg:h-[calc(100vh-52px)]">
      <div className="shrink-0 border-b border-border">
        <StageSpine />
      </div>
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="min-h-[320px] shrink-0 border-b border-border lg:h-full lg:min-h-0 lg:w-72 lg:border-b-0 lg:border-r">
          <ArtifactColumn focusId={focusId} onPick={onPick} />
        </aside>
        <section className="min-h-[460px] min-w-0 flex-1">
          {focusId ? (
            <ArtifactDetail key={focusId} artifactId={focusId} onPick={onPick} />
          ) : (
            <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
              Select a deliverable on the left.
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
