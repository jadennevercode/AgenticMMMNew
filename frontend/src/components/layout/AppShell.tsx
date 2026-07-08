import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useParams } from 'react-router-dom'
import {
  BookOpen,
  Database,
  FolderOpen,
  Inbox,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Pause,
  Play,
  RotateCcw,
  Settings,
  SquareStack,
  TriangleAlert,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { isLlmConfigured } from '../../lib/types'
import { industryPath } from '../../lib/industries'
import { Button } from '../ui/button'
import { Tooltip } from '../ui/misc'
import { cn } from '../../lib/cn'
import { FloatingDock } from './FloatingDock'

const NAV_KEY = 'agenticmmm.nav.expanded'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  badge?: number
  end?: boolean
}

function RailLink({ item, expanded }: { item: NavItem; expanded: boolean }) {
  const Icon = item.icon
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        cn(
          'group relative flex items-center gap-3 rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
          isActive ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground',
          !expanded && 'justify-center',
        )
      }
    >
      <span className="relative">
        <Icon className="size-[18px]" />
        {item.badge ? (
          <span className="absolute -right-1.5 -top-1.5 inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-warning px-0.5 font-mono text-[9px] text-foreground">
            {item.badge}
          </span>
        ) : null}
      </span>
      {expanded && <span className="truncate">{item.label}</span>}
    </NavLink>
  )
  return expanded ? link : <Tooltip content={item.label}>{link}</Tooltip>
}

export default function AppShell() {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()

  const playing = useSimStore((s) => s.playing)
  const running = useSimStore((s) => s.running)
  const autopilot = useSimStore((s) => s.autopilot)
  const tick = useSimStore((s) => s.tick)
  const tasks = useSimStore((s) => s.tasks)
  const decisions = useSimStore((s) => s.decisions)
  const error = useSimStore((s) => s.error)
  const meta = useSimStore((s) => s.activeMeta)
  const modelConfig = useSimStore((s) => s.modelConfig)
  const { run, pause, reset, loadProject, setAutopilot, loadModelConfig } = useSimStore.getState()
  const llmConfigured = isLlmConfigured(modelConfig)

  const [expanded, setExpanded] = useState(() => localStorage.getItem(NAV_KEY) !== '0')
  useEffect(() => {
    localStorage.setItem(NAV_KEY, expanded ? '1' : '0')
  }, [expanded])

  // Hydrate the active project from the backend whenever the route id changes.
  useEffect(() => {
    if (projectId) void loadProject(projectId)
  }, [projectId, loadProject])

  // Load the global model-service config once (drives the LLM run-gate).
  useEffect(() => { void loadModelConfig() }, [loadModelConfig])

  const active = playing || running
  const doneCount = TASKS.filter((t) => tasks[t.id]?.status === 'done').length
  const openDecisions = Object.values(decisions).filter((d) => d.status === 'open').length
  const waiting = TASKS.filter((t) => (t.decision || t.assignment) && tasks[t.id]?.status === 'awaiting_human').length
  // Show the prompt whenever a gate is actually waiting on the user — in
  // interactive (HITL) mode the run loop has already stopped, so don't gate on `active`.
  const blocked = waiting > 0

  const base = `/p/${projectId}`
  const nav: NavItem[] = [
    { to: base, label: 'Project', icon: LayoutDashboard, end: true },
    { to: `${base}/canvas`, label: 'Workflow Canvas', icon: Workflow },
    { to: `${base}/decisions`, label: 'Decisions', icon: Inbox, badge: openDecisions },
    { to: `${base}/data`, label: 'Data Engine', icon: Database },
    { to: `${base}/assets`, label: 'Assets', icon: FolderOpen },
    { to: `${base}/knowledge`, label: 'Knowledge', icon: BookOpen },
    { to: `${base}/settings`, label: 'Settings', icon: Settings },
  ]

  return (
    <div className="flex min-h-screen bg-background">
      {/* ── Left collapsible nav rail ── */}
      <aside
        className={cn(
          'sticky top-0 flex h-screen shrink-0 flex-col border-r border-border bg-card transition-[width] duration-200',
          expanded ? 'w-52' : 'w-14',
        )}
      >
        <Link
          to="/"
          aria-label="All projects"
          className={cn(
            'flex h-[52px] items-center border-b border-border transition-colors hover:bg-accent',
            expanded ? 'gap-2 px-3' : 'justify-center',
          )}
        >
          <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground">
            <SquareStack className="size-4" />
          </span>
          {expanded && <span className="font-semibold tracking-tight">AgenticMMM</span>}
        </Link>

        <nav aria-label="Main navigation" className="flex-1 space-y-1 p-2">
          {nav.map((item) => (
            <RailLink key={item.to} item={item} expanded={expanded} />
          ))}
        </nav>

        {expanded && (
          <div className="border-t border-border px-3 py-3 text-[11px] leading-relaxed text-muted-foreground">
            <p className="truncate font-medium text-foreground">{meta?.name ?? '…'}</p>
            <p className="mt-0.5 truncate">{meta?.brand}</p>
            {meta && <p className="mt-0.5 truncate">{industryPath(meta.industry)}</p>}
          </div>
        )}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? 'Collapse navigation' : 'Expand navigation'}
          className={cn(
            'flex h-10 items-center gap-2 border-t border-border px-3 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
            !expanded && 'justify-center',
          )}
        >
          {expanded ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
          {expanded && <span>Collapse</span>}
        </button>
      </aside>

      {/* ── Right: top bar + content ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[52px] shrink-0 items-center gap-4 border-b border-border bg-card/80 px-5 backdrop-blur-sm">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="hidden text-xs font-medium text-muted-foreground transition-colors hover:text-foreground md:inline"
          >
            ← All projects
          </button>
          {blocked && (
            <span className="hidden items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2.5 py-0.5 text-[11px] font-medium text-foreground md:inline-flex">
              <TriangleAlert className="size-3" />
              {waiting} waiting on you
            </span>
          )}
          {error && (
            <span className="hidden items-center gap-1.5 rounded-full border border-destructive/40 bg-destructive/10 px-2.5 py-0.5 text-[11px] font-medium text-destructive md:inline-flex">
              <TriangleAlert className="size-3" />
              Backend unavailable
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">
              Day {String(tick).padStart(2, '0')} · {doneCount}/{TASKS.length}
            </span>
            <Tooltip content={autopilot
              ? 'Autopilot: auto-satisfies upload & decision gates to run the whole case'
              : 'Interactive: stops at every upload & decision gate for your action'}>
              <label className="hidden cursor-pointer select-none items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground sm:flex">
                <input
                  type="checkbox"
                  className="size-3 accent-primary"
                  checked={autopilot}
                  onChange={(e) => setAutopilot(e.target.checked)}
                />
                Autopilot
              </label>
            </Tooltip>
            <Tooltip content={!llmConfigured ? 'Configure an LLM in Settings before running' : ''}>
              <Button
                size="sm"
                variant={!active && !llmConfigured ? 'outline' : undefined}
                onClick={active ? pause : (!llmConfigured ? () => navigate(`/p/${projectId}/settings`) : () => void run())}
              >
                {active ? <Pause /> : !llmConfigured ? <Settings /> : <Play />}
                {active ? 'Pause' : !llmConfigured ? 'Configure LLM' : autopilot ? 'Run all' : 'Run'}
              </Button>
            </Tooltip>
            <Button size="icon" variant="ghost" onClick={() => void reset()} aria-label="Reset">
              <RotateCcw />
            </Button>
          </div>
        </header>

        {/* Reminder: a project must have an LLM configured before it can run. */}
        {!llmConfigured && (
          <div className="flex items-center gap-2 border-b border-warning/40 bg-warning/10 px-5 py-2 text-[12px] text-foreground">
            <TriangleAlert className="size-3.5 shrink-0 text-warning" />
            <span className="min-w-0 flex-1">
              <strong className="font-semibold">Model not configured.</strong>{' '}
              Choose an LLM provider &amp; model in Settings to run this project. ASR (interview audio) is optional.
            </span>
            <Button size="sm" variant="outline" onClick={() => navigate(`/p/${projectId}/settings`)}>
              <Settings />Open Settings
            </Button>
          </div>
        )}

        <div className="min-h-0 flex-1">
          <Outlet />
        </div>
      </div>

      <FloatingDock />
    </div>
  )
}
