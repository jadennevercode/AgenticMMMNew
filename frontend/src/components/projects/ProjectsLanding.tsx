import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Plus, Settings, SquareStack, Trash2, TriangleAlert } from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { industryPath } from '../../lib/industries'
import type { ProjectListItem } from '../../lib/types'
import { Button } from '../ui/button'
import { cn } from '../../lib/cn'
import NewProjectForm from './NewProjectForm'

const STATUS_META: Record<ProjectListItem['status'], { label: string; cls: string }> = {
  complete: { label: '已完成', cls: 'border-success/40 bg-success/10 text-success' },
  running: { label: '运行中', cls: 'border-primary/40 bg-primary/10 text-primary' },
  blocked: { label: '待处理', cls: 'border-warning/40 bg-warning/10 text-foreground' },
  draft: { label: '草稿', cls: 'border-border bg-muted text-muted-foreground' },
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function ProjectCard({
  project,
  onOpen,
  onDelete,
}: {
  project: ProjectListItem
  onOpen: () => void
  onDelete: () => void
}) {
  const status = STATUS_META[project.status]
  const pct = project.tasksTotal ? Math.round((project.tasksDone / project.tasksTotal) * 100) : 0

  return (
    <article
      onClick={onOpen}
      className="group relative flex cursor-pointer flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-2">
        <span className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium', status.cls)}>
          {status.label}
        </span>
        <button
          type="button"
          aria-label="Delete project"
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="rounded-md p-1.5 text-muted-foreground opacity-0 transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>

      <div className="min-w-0">
        <h3 className="truncate text-[15px] font-semibold leading-snug tracking-tight">{project.name}</h3>
        <p className="mt-1 truncate text-sm text-muted-foreground">{project.brand}</p>
      </div>

      <p className="truncate font-mono text-[11px] text-muted-foreground">{industryPath(project.industry)}</p>

      <div className="mt-auto space-y-2">
        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn('h-full rounded-full transition-[width] duration-500', project.status === 'complete' ? 'bg-success' : 'bg-primary')}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span className="font-mono">
            {project.tasksDone}/{project.tasksTotal} 步 · {formatDate(project.createdAt)}
          </span>
          <span className="inline-flex items-center gap-1 font-medium text-foreground opacity-0 transition-opacity group-hover:opacity-100">
            打开 <ArrowRight className="size-3" />
          </span>
        </div>
      </div>
    </article>
  )
}

export default function ProjectsLanding() {
  const navigate = useNavigate()
  const projects = useSimStore((s) => s.projects)
  const loading = useSimStore((s) => s.projectsLoading)
  const error = useSimStore((s) => s.error)
  const { loadProjects, deleteProject } = useSimStore.getState()

  const [showForm, setShowForm] = useState(false)

  useEffect(() => {
    void loadProjects()
  }, [loadProjects])

  async function handleDelete(project: ProjectListItem) {
    if (!window.confirm(`删除项目「${project.name}」？此操作不可撤销。`)) return
    await deleteProject(project.id)
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Atmospheric header band */}
      <header className="relative overflow-hidden border-b border-border">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/10 via-transparent to-transparent" />
        <div className="relative mx-auto flex max-w-6xl flex-col gap-6 px-6 py-12 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-muted-foreground">
              <span className="grid size-6 place-items-center rounded-md bg-primary text-primary-foreground">
                <SquareStack className="size-3.5" />
              </span>
              AgenticMMM
            </div>
            <h1 className="mt-4 text-4xl font-semibold tracking-tight">项目</h1>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              管理历史 MMM 项目，或新建一个项目开始端到端的多智能体建模流程。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button size="lg" variant="outline" onClick={() => navigate('/settings')} aria-label="模型服务设置">
              <Settings />
              设置
            </Button>
            <Button size="lg" onClick={() => setShowForm(true)}>
              <Plus />
              新建项目
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        {error && !projects.length && (
          <div className="mb-6 flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <TriangleAlert className="size-4" />
            无法连接后端服务（{error}）。请确认后端已启动。
          </div>
        )}

        {loading && !projects.length ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-48 animate-pulse rounded-2xl border border-border bg-card" />
            ))}
          </div>
        ) : projects.length ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onOpen={() => navigate(`/p/${project.id}`)}
                onDelete={() => void handleDelete(project)}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-border py-20 text-center">
            <span className="grid size-12 place-items-center rounded-2xl bg-muted text-muted-foreground">
              <SquareStack className="size-6" />
            </span>
            <div>
              <p className="font-medium">还没有项目</p>
              <p className="mt-1 text-sm text-muted-foreground">新建第一个项目，开始 MMM 建模流程。</p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus />
              新建项目
            </Button>
          </div>
        )}
      </main>

      {showForm && <NewProjectForm onClose={() => setShowForm(false)} />}
    </div>
  )
}
