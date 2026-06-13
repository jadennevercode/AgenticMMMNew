import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  BookOpen,
  FolderOpen,
  Inbox,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Pause,
  Play,
  RotateCcw,
  SquareStack,
  StepForward,
  TriangleAlert,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import { useSimStore } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { PROJECT } from '../../lib/profiles'
import { Button } from '../ui/button'
import { Tooltip } from '../ui/misc'
import { cn } from '../../lib/cn'
import { FloatingDock } from './FloatingDock'

const TICK_INTERVAL_MS = 850
const NAV_KEY = 'agenticmmm.nav.expanded'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  badge?: number
}

function RailLink({ item, expanded }: { item: NavItem; expanded: boolean }) {
  const Icon = item.icon
  const link = (
    <NavLink
      to={item.to}
      end={item.to === '/'}
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
  const playing = useSimStore((s) => s.playing)
  const tick = useSimStore((s) => s.tick)
  const tasks = useSimStore((s) => s.tasks)
  const decisions = useSimStore((s) => s.decisions)
  const { play, pause, stepTick, reset } = useSimStore.getState()

  const [expanded, setExpanded] = useState(() => localStorage.getItem(NAV_KEY) !== '0')
  useEffect(() => {
    localStorage.setItem(NAV_KEY, expanded ? '1' : '0')
  }, [expanded])

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => useSimStore.getState().stepTick(), TICK_INTERVAL_MS)
    return () => clearInterval(id)
  }, [playing])

  const doneCount = TASKS.filter((t) => tasks[t.id]?.status === 'done').length
  const openDecisions = Object.values(decisions).filter((d) => d.status === 'open').length
  const waiting = TASKS.filter((t) => (t.decision || t.assignment) && tasks[t.id]?.status === 'awaiting_human').length
  const blocked = waiting > 0 && playing

  const nav: NavItem[] = [
    { to: '/', label: 'Project', icon: LayoutDashboard },
    { to: '/canvas', label: 'Workflow Canvas', icon: Workflow },
    { to: '/decisions', label: 'Decisions', icon: Inbox, badge: openDecisions },
    { to: '/assets', label: 'Assets', icon: FolderOpen },
    { to: '/knowledge', label: 'Knowledge', icon: BookOpen },
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
        <div className={cn('flex h-[52px] items-center border-b border-border', expanded ? 'gap-2 px-3' : 'justify-center')}>
          <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground">
            <SquareStack className="size-4" />
          </span>
          {expanded && <span className="font-semibold tracking-tight">AgenticMMM</span>}
        </div>

        <nav aria-label="Main navigation" className="flex-1 space-y-1 p-2">
          {nav.map((item) => (
            <RailLink key={item.to} item={item} expanded={expanded} />
          ))}
        </nav>

        {expanded && (
          <div className="border-t border-border px-3 py-3 text-[11px] leading-relaxed text-muted-foreground">
            <p className="font-medium text-foreground">{PROJECT.name}</p>
            <p className="mt-0.5">{PROJECT.window}</p>
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
          {blocked && (
            <span className="hidden items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2.5 py-0.5 text-[11px] font-medium text-foreground md:inline-flex">
              <TriangleAlert className="size-3" />
              {waiting} waiting on you
            </span>
          )}
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">
              Day {String(tick).padStart(2, '0')} · {doneCount}/{TASKS.length}
            </span>
            <Button size="sm" onClick={playing ? pause : play}>
              {playing ? <Pause /> : <Play />}
              {playing ? 'Pause' : 'Run'}
            </Button>
            <Button size="icon" variant="outline" onClick={stepTick} aria-label="Step one day">
              <StepForward />
            </Button>
            <Button size="icon" variant="ghost" onClick={reset} aria-label="Reset">
              <RotateCcw />
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1">
          <Outlet />
        </div>
      </div>

      <FloatingDock />
    </div>
  )
}
