import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { useSimStore } from '../../store/useSimStore'
import { TASKS } from '../../lib/scenario'
import { STAGES, STAGE_ORDER, AGENT_ORDER, AGENTS, AGENT_COLOR } from '../../lib/profiles'
import { STATUS_LABEL } from '../../lib/ui-language'
import { TaskBadge, StatusPill } from '../ui/primitives'
import { cn } from '../../lib/cn'
import type { AgentId, TaskBlueprint, TaskStatus } from '../../lib/types'

const COL_W = 280
const ROW_H = 104
const TOP = 64

type View = 'stage' | 'agent' | 'execution'
const VIEWS: { id: View; label: string }[] = [
  { id: 'stage', label: 'Stage' },
  { id: 'agent', label: 'Agent' },
  { id: 'execution', label: 'Human · AI · Auto' },
]

/** Execution kind from automation class: M→Automation, A/C→AI, H→Human */
function execKind(t: TaskBlueprint): 'auto' | 'ai' | 'human' {
  return t.class === 'M' ? 'auto' : t.class === 'H' ? 'human' : 'ai'
}

interface Column {
  key: string
  label: string
  tasks: TaskBlueprint[]
}

function columnsFor(view: View): Column[] {
  if (view === 'agent') {
    return AGENT_ORDER.map((a: AgentId) => ({
      key: a,
      label: AGENTS[a].name,
      tasks: TASKS.filter((t) => t.agent === a),
    })).filter((c) => c.tasks.length)
  }
  if (view === 'execution') {
    const groups: { key: string; label: string }[] = [
      { key: 'auto', label: 'Automation' },
      { key: 'ai', label: 'AI' },
      { key: 'human', label: 'Human' },
    ]
    return groups.map((g) => ({ ...g, tasks: TASKS.filter((t) => execKind(t) === g.key) }))
  }
  return STAGE_ORDER.map((sid) => ({
    key: sid,
    label: `S${STAGES[sid].index} · ${STAGES[sid].name}`,
    tasks: TASKS.filter((t) => t.stage === sid),
  }))
}

/* ── Nodes ── */
type TaskNodeData = { task: TaskBlueprint; status: TaskStatus }
type HeaderNodeData = { label: string; count: number }

function TaskNode({ data }: NodeProps<Node<TaskNodeData>>) {
  const { task, status } = data
  const color = STATUS_LABEL[status].color
  const awaiting = status === 'awaiting_human'
  return (
    <div
      className="w-[228px] rounded-lg border bg-card px-3 py-2.5 shadow-sm transition-shadow hover:shadow-md"
      style={{ borderColor: awaiting ? 'var(--color-warning)' : 'var(--color-border)' }}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-border" />
      <div className="flex items-center gap-2">
        <span aria-hidden className="size-2 shrink-0 rounded-[2px]" style={{ background: AGENT_COLOR[task.agent] }} />
        <span className="font-mono text-[10px] text-muted-foreground">{task.id}</span>
        <span className="ml-auto h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      </div>
      <p className="mt-1 truncate text-[12.5px] font-medium">{task.name}</p>
      <div className="mt-1.5 flex items-center justify-between gap-1">
        <TaskBadge task={task} />
        <StatusPill status={status} />
      </div>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-border" />
    </div>
  )
}

function HeaderNode({ data }: NodeProps<Node<HeaderNodeData>>) {
  return (
    <div className="w-[228px]">
      <p className="truncate font-mono text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {data.label} · {data.count}
      </p>
    </div>
  )
}

const nodeTypes = { task: TaskNode, header: HeaderNode }

function CanvasInner({ view }: { view: View }) {
  const tasks = useSimStore((s) => s.tasks)
  const selectTask = useSimStore((s) => s.selectTask)
  const navigate = useNavigate()

  const { nodes, edges } = useMemo(() => {
    const cols = columnsFor(view)
    const nodes: Node[] = []
    cols.forEach((col, c) => {
      nodes.push({
        id: `hdr-${col.key}`,
        type: 'header',
        position: { x: c * COL_W, y: 12 },
        data: { label: col.label, count: col.tasks.length },
        draggable: false,
        selectable: false,
      })
      col.tasks.forEach((t, r) => {
        nodes.push({
          id: t.id,
          type: 'task',
          position: { x: c * COL_W, y: TOP + r * ROW_H },
          data: { task: t, status: tasks[t.id]?.status ?? 'pending' },
          draggable: false,
        })
      })
    })
    const subtle = view !== 'stage'
    const edges: Edge[] = TASKS.flatMap((t) =>
      t.dependsOn.map((dep) => {
        const done = tasks[dep]?.status === 'done'
        return {
          id: `${dep}->${t.id}`,
          source: dep,
          target: t.id,
          animated: tasks[dep]?.status === 'running',
          style: {
            stroke: done ? 'var(--color-status-done)' : 'var(--color-border)',
            strokeWidth: 1.5,
            opacity: subtle && !done ? 0.35 : 1,
          },
        }
      }),
    )
    return { nodes, edges }
  }, [view, tasks])

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      fitView
      fitViewOptions={{ padding: 0.14 }}
      minZoom={0.4}
      maxZoom={1.4}
      proOptions={{ hideAttribution: true }}
      onNodeClick={(_, node) => {
        if (node.type !== 'task') return
        selectTask(node.id)
        navigate('/')
      }}
    >
      <Background gap={22} color="var(--color-border)" />
      <Controls showInteractive={false} />
    </ReactFlow>
  )
}

export default function WorkflowCanvas() {
  const [view, setView] = useState<View>('stage')
  return (
    <div className="relative h-[calc(100vh-52px)]">
      {/* view switcher */}
      <div className="absolute left-4 top-3 z-10 inline-flex items-center gap-1 rounded-lg border border-border bg-card/90 p-1 backdrop-blur">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => setView(v.id)}
            className={cn(
              'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
              view === v.id ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {v.label}
          </button>
        ))}
      </div>

      {/* remount per view so fitView re-frames the new layout */}
      <CanvasInner key={view} view={view} />

      <div className="absolute bottom-4 left-4 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card/90 px-3 py-2 text-[11px] text-muted-foreground backdrop-blur">
        {(['pending', 'running', 'awaiting_human', 'done'] as TaskStatus[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="size-1.5 rounded-full" style={{ background: STATUS_LABEL[s].color }} />
            {STATUS_LABEL[s].label}
          </span>
        ))}
        <span className="text-muted-foreground/70">· click a task to open it</span>
      </div>
    </div>
  )
}
