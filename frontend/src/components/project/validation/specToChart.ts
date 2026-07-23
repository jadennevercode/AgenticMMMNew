import type { ValidationField, ValidationSpec } from '../../../lib/types'

/**
 * Translate an app-owned preset (`ValidationSpec`) into a Graphic Walker chart
 * object (`IChart`) for the installed GW version (0.4.84).
 *
 * Intent — period on X, the KPI metric + factor overlays on Y (`value` measure
 * split by `metric`), filtered to this L3, bar-vs-line per `overlayKind`.
 *
 * We deliberately DO NOT import from `@kanaries/graphic-walker` here: importing a
 * value from GW would pull the (large) library into this module's chunk and defeat
 * the dynamic import in `ExploreTab`. Instead the two default objects below mirror
 * GW 0.4.84's own `emptyEncodings()` / default config+layout exactly (verified
 * against `dist/graphic-walker.es.js`). A GW upgrade only needs to touch this file.
 */

/** GW 0.4.84 `IVisualConfigNew` defaults (geoms overridden per preset). */
const CONFIG_BASE = {
  defaultAggregated: true,
  coordSystem: 'generic',
  limit: -1,
} as const

/** GW 0.4.84 `IVisualLayout` defaults for a fresh chart. */
const DEFAULT_LAYOUT = {
  showActions: false,
  showTableSummary: false,
  stack: 'stack',
  interactiveScale: false,
  zeroScale: true,
  size: { mode: 'auto', width: 320, height: 200 },
  format: {},
  resolve: { x: false, y: false, color: false, opacity: false, shape: false, size: false },
} as const

/** All 16 `DraggableFieldState` channels — every one must be present. */
const EMPTY_ENCODINGS = {
  dimensions: [] as unknown[],
  measures: [] as unknown[],
  rows: [] as unknown[],
  columns: [] as unknown[],
  color: [] as unknown[],
  opacity: [] as unknown[],
  size: [] as unknown[],
  shape: [] as unknown[],
  radius: [] as unknown[],
  theta: [] as unknown[],
  longitude: [] as unknown[],
  latitude: [] as unknown[],
  geoId: [] as unknown[],
  details: [] as unknown[],
  filters: [] as unknown[],
  text: [] as unknown[],
}

export function specToChart(spec: ValidationSpec, fields: ValidationField[]): unknown {
  const byId = new Map(fields.map((f) => [f.fid, f]))
  const has = (fid: string) => byId.has(fid)
  const nameOf = (fid: string) => byId.get(fid)?.name ?? fid
  const dim = (fid: string) => ({
    fid,
    name: nameOf(fid),
    semanticType: byId.get(fid)?.semanticType ?? 'nominal',
    analyticType: 'dimension' as const,
  })
  const mea = (fid: string) => ({
    fid,
    name: nameOf(fid),
    semanticType: 'quantitative' as const,
    analyticType: 'measure' as const,
    aggName: 'sum',
  })

  // The field pool GW shows in its shelves — the real dataset dimensions/measures.
  const dimensions = fields
    .filter((f) => f.analyticType === 'dimension')
    .map((f) => dim(f.fid))
  const measures = fields
    .filter((f) => f.analyticType === 'measure')
    .map((f) => mea(f.fid))

  const xFid = spec.encoding.x && has(spec.encoding.x) ? spec.encoding.x : 'period'
  const metrics = [spec.encoding.yKpi, ...spec.encoding.yOverlay].filter(Boolean)

  const columns = has(xFid) ? [dim(xFid)] : []
  const rows = has('value') ? [mea('value')] : []
  const color = metrics.length > 1 && has('metric') ? [dim('metric')] : []

  const filters: unknown[] = []
  const l3Values = [spec.filter.l3, spec.filter.kpiL3].filter((v): v is string => Boolean(v))
  if (has('l3') && l3Values.length) {
    filters.push({ ...dim('l3'), rule: { type: 'one of', value: l3Values } })
  }
  if (has('metric') && metrics.length) {
    filters.push({ ...dim('metric'), rule: { type: 'one of', value: metrics } })
  }

  return {
    visId: spec.specId,
    name: spec.title || spec.l3,
    encodings: { ...EMPTY_ENCODINGS, dimensions, measures, columns, rows, color, filters },
    config: { ...CONFIG_BASE, geoms: [spec.encoding.overlayKind === 'bar' ? 'bar' : 'line'] },
    layout: DEFAULT_LAYOUT,
  }
}
