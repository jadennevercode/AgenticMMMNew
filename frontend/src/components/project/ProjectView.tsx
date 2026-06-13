import { StageTasksSidebar } from './StageTasksSidebar'
import { TaskWorkbench } from '../workbench/TaskWorkbench'
import { ArtifactsPanel } from '../assets/ArtifactsPanel'

/**
 * Project = 3-column workspace:
 *  left  — current-stage task list
 *  center— what needs you (decision / input)
 *  right — artifacts
 * Activity + Assistant live in the floating dock (see AppShell).
 */
export default function ProjectView() {
  return (
    <div className="flex flex-col lg:h-[calc(100vh-52px)] lg:flex-row">
      <aside className="min-h-[360px] shrink-0 border-b border-border lg:h-full lg:min-h-0 lg:w-72 lg:border-b-0 lg:border-r">
        <StageTasksSidebar />
      </aside>
      <section className="min-h-[460px] min-w-0 flex-1 border-b border-border lg:h-full lg:min-h-0 lg:border-b-0">
        <TaskWorkbench />
      </section>
      <aside className="min-h-[460px] shrink-0 lg:h-full lg:min-h-0 lg:w-[400px] lg:border-l lg:border-border">
        <ArtifactsPanel />
      </aside>
    </div>
  )
}
