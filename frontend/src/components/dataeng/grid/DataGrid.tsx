import { useMemo, useRef, useState } from 'react'
import {
  type ColumnDef, type SortingState, flexRender, getCoreRowModel,
  getFilteredRowModel, getSortedRowModel, useReactTable,
} from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowDown, ArrowUp, Loader2, Search } from 'lucide-react'
import type { ColumnStat } from '../../../lib/types'
import { cn } from '../../../lib/cn'
import { ColumnProfile } from './ColumnProfile'

/**
 * The data grid every Data Engine surface reads from.
 *
 * Built on TanStack Table (column model, sorting, filtering) and TanStack Virtual
 * (row windowing) rather than a hand-rolled `<table>`, so a wide result with
 * hundreds of rows stays responsive and the interactions behave the way people
 * expect from a spreadsheet: click a header to sort, type to filter, numbers
 * right-aligned, missing values visibly missing rather than blank.
 *
 * Each header carries its column's profile — see {@link ColumnProfile}.
 */

const ROW_HEIGHT = 26
const NUMERIC_TYPES = ['int', 'float', 'double', 'decimal', 'real', 'bigint', 'hugeint']

export interface DataGridProps {
  columns: string[]
  rows: string[][]
  stats?: ColumnStat[]
  /** Total rows behind the result; `rows` may be a capped window of it. */
  totalRows?: number
  loading?: boolean
  error?: string
  emptyMessage?: string
  /** Grid body height. Defaults to filling the parent. */
  className?: string
}

export function DataGrid({
  columns, rows, stats = [], totalRows, loading, error,
  emptyMessage = 'No rows to show yet.', className,
}: DataGridProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [filter, setFilter] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const statOf = useMemo(
    () => new Map(stats.map((s) => [s.name, s])), [stats])

  const columnDefs = useMemo<ColumnDef<string[]>[]>(
    () => columns.map((name, index) => ({
      id: name,
      accessorFn: (row) => row[index] ?? '',
      header: name,
      sortingFn: isNumeric(statOf.get(name)) ? numericSort : 'alphanumeric',
    })),
    [columns, statOf])

  const table = useReactTable({
    data: rows,
    columns: columnDefs,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const model = table.getRowModel()
  const virtualizer = useVirtualizer({
    count: model.rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })
  const items = virtualizer.getVirtualItems()
  const padTop = items.length ? items[0].start : 0
  const padBottom = items.length
    ? virtualizer.getTotalSize() - items[items.length - 1].end : 0

  const shown = model.rows.length
  const capped = totalRows !== undefined && totalRows > rows.length

  return (
    <div className={cn('flex min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-background', className)}>
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-muted/40 px-3 py-1.5">
        <div className="flex min-w-0 items-center gap-1.5 rounded-md border border-transparent bg-background/70 px-2 py-1 transition-colors focus-within:border-primary/50">
          <Search className="size-3 shrink-0 text-muted-foreground" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter rows"
            className="w-32 min-w-0 bg-transparent text-[11px] outline-none placeholder:text-muted-foreground/70"
          />
        </div>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {loading && <Loader2 className="mr-1 inline size-3 animate-spin" />}
          {filter ? `${shown.toLocaleString()} of ` : ''}
          {(totalRows ?? rows.length).toLocaleString()} rows · {columns.length} columns
        </span>
        {capped && (
          <span className="rounded-full bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
            showing first {rows.length.toLocaleString()}
          </span>
        )}
        {sorting.length > 0 && (
          <button type="button" onClick={() => setSorting([])}
            className="ml-auto text-[10px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
            clear sort
          </button>
        )}
      </div>

      {error ? (
        <div className="flex flex-1 items-center justify-center p-6">
          <p className="max-w-lg whitespace-pre-wrap rounded-md border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-center font-mono text-[11px] text-rose-700">
            {error}
          </p>
        </div>
      ) : columns.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-6 text-center text-[11px] text-muted-foreground">
          {emptyMessage}
        </div>
      ) : (
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-separate border-spacing-0 text-[11px]">
            <thead>
              <tr>
                {table.getHeaderGroups()[0].headers.map((header) => {
                  const stat = statOf.get(header.column.id)
                  const sorted = header.column.getIsSorted()
                  return (
                    <th key={header.id}
                      className="sticky top-0 z-10 border-b border-border bg-muted/95 px-2.5 py-1.5 text-left align-top backdrop-blur">
                      <button type="button" onClick={header.column.getToggleSortingHandler()}
                        className="flex w-full items-center gap-1 text-left transition-colors hover:text-primary">
                        <span className="truncate font-semibold">{header.column.id}</span>
                        {sorted === 'asc' && <ArrowUp className="size-3 shrink-0 text-primary" />}
                        {sorted === 'desc' && <ArrowDown className="size-3 shrink-0 text-primary" />}
                        <span className="ml-auto shrink-0 font-mono text-[9px] font-normal text-muted-foreground/70">
                          {shortType(stat?.type)}
                        </span>
                      </button>
                      <div className="mt-1 w-full min-w-28">
                        <ColumnProfile stat={stat} />
                      </div>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {padTop > 0 && <tr style={{ height: padTop }} />}
              {items.map((item) => {
                const row = model.rows[item.index]
                return (
                  <tr key={row.id} className="group" style={{ height: ROW_HEIGHT }}>
                    {row.getVisibleCells().map((cell) => {
                      const value = cell.getValue() as string
                      const numeric = isNumeric(statOf.get(cell.column.id))
                      return (
                        <td key={cell.id}
                          className={cn(
                            'max-w-72 truncate border-b border-border/50 px-2.5 transition-colors group-hover:bg-accent/40',
                            numeric && 'text-right tabular-nums',
                          )}
                          title={value}>
                          {value === ''
                            ? <span className="text-muted-foreground/40">∅</span>
                            : flexRender(cell.column.columnDef.cell ?? ((c) => c.getValue()), cell.getContext())}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
              {padBottom > 0 && <tr style={{ height: padBottom }} />}
            </tbody>
          </table>
          {shown === 0 && (
            <p className="p-6 text-center text-[11px] text-muted-foreground">
              No rows match “{filter}”.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

const isNumeric = (stat: ColumnStat | undefined) =>
  !!stat && NUMERIC_TYPES.some((t) => stat.type.includes(t))

const numericSort = (a: { getValue: (id: string) => unknown }, b: { getValue: (id: string) => unknown }, id: string) => {
  const x = Number(a.getValue(id))
  const y = Number(b.getValue(id))
  if (Number.isNaN(x) && Number.isNaN(y)) return 0
  if (Number.isNaN(x)) return -1
  if (Number.isNaN(y)) return 1
  return x - y
}

function shortType(type: string | undefined): string {
  if (!type) return ''
  if (type.includes('varchar') || type.includes('text')) return 'text'
  if (type.includes('timestamp')) return 'time'
  if (type.includes('date')) return 'date'
  if (type.includes('bool')) return 'bool'
  if (NUMERIC_TYPES.some((t) => type.includes(t))) return type.includes('int') ? 'int' : 'num'
  return type.slice(0, 6)
}
