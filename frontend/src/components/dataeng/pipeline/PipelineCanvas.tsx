import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background, Controls, Handle, Position, ReactFlow,
  applyNodeChanges,
  type Connection, type Edge, type Node, type NodeChange, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { TransformPipeline } from '../../../lib/types'
import { cn } from '../../../lib/cn'

const SOURCE_PREFIX = 'source:'

const KIND_LABEL: Record<string, string> = {
  field_map: 'Field map', enum_map: 'Enum map', join: 'Join', union: 'Union',
  aggregate: 'Aggregate', filter: 'Filter', derive: 'Derive', custom_sql: 'SQL',
}

export interface CanvasProps {
  pipeline: TransformPipeline
  sources: string[]
  statusByStep: Record<string, string> // step id → success|error|'' (from last build)
  selected: string | null              // selected node id (step id or 'source:t')
  onSelect: (id: string | null) => void
  onConnect: (sourceId: string, targetStepId: string) => void
  onDisconnect: (sourceId: string, targetStepId: string) => void
}

interface PipeNodeData extends Record<string, unknown> {
  title: string
  subtitle?: string
  color: string
  tone: 'source' | 'step' | 'mart'
  hasTarget: boolean // raw sources originate connections only — no inbound handle
}

function statusColor(status?: string): string {
  if (status === 'success') return '#10b981'
  if (status === 'error') return '#f43f5e'
  return '#94a3b8'
}

/** Layered left-to-right layout: sources at depth 0, steps at 1 + max(input depth). */
function layout(pipe: TransformPipeline, sources: string[]): Map<string, { x: number; y: number }> {
  const depth = new Map<string, number>()
  sources.forEach((s) => depth.set(`${SOURCE_PREFIX}${s}`, 0))
  const byId = new Map(pipe.steps.map((s) => [s.id, s]))
  const resolve = (id: string, seen: Set<string>): number => {
    if (depth.has(id)) return depth.get(id)!
    if (seen.has(id)) return 1
    seen.add(id)
    const step = byId.get(id)
    const d = step && step.inputs.length
      ? 1 + Math.max(...step.inputs.map((i) => resolve(i, seen)))
      : 1
    depth.set(id, d)
    return d
  }
  pipe.steps.forEach((s) => resolve(s.id, new Set()))
  const perLevel = new Map<number, number>()
  const pos = new Map<string, { x: number; y: number }>()
  const place = (id: string) => {
    const d = depth.get(id) ?? 0
    const row = perLevel.get(d) ?? 0
    perLevel.set(d, row + 1)
    pos.set(id, { x: d * 250, y: row * 110 })
  }
  sources.forEach((s) => place(`${SOURCE_PREFIX}${s}`))
  pipe.steps.forEach((s) => place(s.id))
  return pos
}

const HANDLE_CLS = 'size-3 rounded-[3px] border-[1.5px] border-primary bg-background transition-transform hover:scale-125'

/** Custom node: card + explicit, larger connection handles. */
function PipeNode({ data }: NodeProps) {
  const d = data as PipeNodeData
  return (
    <div className={cn('min-w-40 max-w-52 rounded-md px-2.5 py-1.5 text-left',
      d.tone === 'mart' && 'ring-1 ring-primary/40')}>
      {d.hasTarget && (
        <Handle type="target" position={Position.Left} className={HANDLE_CLS}
          title="Drop a connection here to feed this step" />
      )}
      <div className="flex items-center gap-1.5">
        <span className="size-2 shrink-0 rounded-full" style={{ background: d.color }} />
        <span className="truncate font-mono text-[11px] font-semibold">{d.title}</span>
      </div>
      {d.subtitle && <div className="mt-0.5 truncate text-[9px] uppercase tracking-wide opacity-60">{d.subtitle}</div>}
      <Handle type="source" position={Position.Right} className={HANDLE_CLS}
        title="Drag from here to connect into another step" />
    </div>
  )
}

const NODE_TYPES = { pipe: PipeNode }

export function PipelineCanvas({
  pipeline, sources, statusByStep, selected, onSelect, onConnect, onDisconnect,
}: CanvasProps) {
  const positions = useMemo(() => layout(pipeline, sources), [pipeline, sources])
  const [nodes, setNodes] = useState<Node[]>([])

  const builtNodes = useMemo<Node[]>(() => {
    const out: Node[] = sources.map((s) => {
      const id = `${SOURCE_PREFIX}${s}`
      return {
        id, type: 'pipe',
        position: positions.get(id) ?? { x: 0, y: 0 },
        data: { title: s, subtitle: 'raw source', color: '#0ea5e9', tone: 'source', hasTarget: false } satisfies PipeNodeData,
        style: nodeStyle(selected === id),
      }
    })
    for (const step of pipeline.steps) {
      const isOut = step.id === (pipeline.outputStep || pipeline.steps[pipeline.steps.length - 1]?.id)
      out.push({
        id: step.id, type: 'pipe',
        position: positions.get(step.id) ?? { x: 250, y: 0 },
        data: {
          title: step.name || step.id,
          color: statusColor(statusByStep[step.id]),
          subtitle: isOut ? `${KIND_LABEL[step.kind]} · output` : KIND_LABEL[step.kind],
          tone: isOut ? 'mart' : 'step',
          hasTarget: true,
        } satisfies PipeNodeData,
        style: nodeStyle(selected === step.id),
      })
    }
    return out
  }, [pipeline, sources, positions, statusByStep, selected])

  // Reconcile the rendered node set with the derived one WITHOUT discarding manual
  // drag positions: keep the live position for nodes that still exist, only add /
  // remove / restyle. (Rebuilding wholesale on every selection reset arrangement.)
  useEffect(() => {
    setNodes((prev) => {
      const posById = new Map(prev.map((n) => [n.id, n.position]))
      return builtNodes.map((n) => {
        const live = posById.get(n.id)
        return live ? { ...n, position: live } : n
      })
    })
  }, [builtNodes])

  const edges = useMemo<Edge[]>(
    () => pipeline.steps.flatMap((step) =>
      step.inputs.map((inp) => ({
        id: `${inp}->${step.id}`, source: inp, target: step.id,
        animated: false, style: { strokeWidth: 1.5 },
      }))),
    [pipeline])

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => setNodes((ns) => applyNodeChanges(changes, ns)),
    [])
  const handleConnect = useCallback((c: Connection) => {
    if (c.source && c.target && !c.target.startsWith(SOURCE_PREFIX)) onConnect(c.source, c.target)
  }, [onConnect])
  const handleEdgesDelete = useCallback((removed: Edge[]) => {
    for (const e of removed) onDisconnect(e.source, e.target)
  }, [onDisconnect])

  // Reject invalid drags visibly (cursor stays "no-drop") instead of silently
  // dropping them: no self-loop, never feed a raw source, and no cycles.
  const isValidConnection = useCallback((c: Connection | Edge): boolean => {
    const { source, target } = c
    if (!source || !target) return false
    if (target.startsWith(SOURCE_PREFIX)) return false
    if (source === target) return false
    const byId = new Map(pipeline.steps.map((s) => [s.id, s]))
    const dependsOn = (a: string, b: string, seen = new Set<string>()): boolean => {
      const step = byId.get(a)
      if (!step) return false // raw sources have no inputs
      for (const inp of step.inputs) {
        if (inp === b) return true
        if (!seen.has(inp)) { seen.add(inp); if (dependsOn(inp, b, seen)) return true }
      }
      return false
    }
    return !dependsOn(source, target) // adding source→target must not close a loop
  }, [pipeline])

  // Remount (and re-fit) when the node set itself changes — fitView only runs on
  // init, and the nodes arrive async from the workspace status call.
  const flowKey = `${sources.length}:${pipeline.steps.map((s) => s.id).join(',')}`

  return (
    <div className="h-72 rounded-md border border-border bg-background">
      <ReactFlow
        key={flowKey}
        nodeTypes={NODE_TYPES}
        nodes={nodes}
        edges={edges}
        onNodesChange={handleNodesChange}
        onConnect={handleConnect}
        onEdgesDelete={handleEdgesDelete}
        isValidConnection={isValidConnection}
        onNodeClick={(_, node) => onSelect(node.id)}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        minZoom={0.15}
        proOptions={{ hideAttribution: true }}
        deleteKeyCode={['Backspace', 'Delete']}
        nodesConnectable
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}

function nodeStyle(isSelected: boolean): React.CSSProperties {
  return {
    padding: 0,
    borderRadius: 8,
    border: isSelected ? '1.5px solid var(--primary)' : '1px solid var(--border)',
    background: 'var(--card)',
    color: 'var(--card-foreground)',
    boxShadow: isSelected ? '0 0 0 3px color-mix(in oklch, var(--primary) 15%, transparent)' : 'none',
    width: 'auto',
  }
}
