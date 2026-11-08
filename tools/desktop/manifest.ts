/** The manifest of evidence/v2 (shape: tests/acceptance/test_o7_desktop_evidence.py + contract/RAW-EVIDENCE.md + PARTS-2.md). Pure. */
import type { Box, Rect, StripVerdict } from './evidence_lib.ts'

export interface SessionSpec { stored_id: string; expected: string; dom_state: string; dom_dump: string; title: string }
export interface StillSpec { state: string; path: string; sha256: string; meta?: string; dom_dump?: string }
export interface CpuWindowSpec { file: string; dom_dump: string; roles: Record<string, string> }
export interface Pixels { organs_detected: number; p95_dL: number; mean_dL: number; lowK: number; highK: number; ground?: string; exclusion?: Exclusion }
export interface Exclusion { area: number; excluded_px: number; measured_px: number; share: number; reason: string | null }
export interface StripState extends StripVerdict { session: string; state: string }
export interface StripCheck { viewport: { w: number; h: number }; states: StripState[] }
export interface SidebarCrop { state: string; path: string; sha256: string; source: string }
export interface Measured {
  pixels: Record<string, Pixels>
  cpu: Record<string, { mean_pct: number; window_s: number }>
  field: { updates_per_s: number; hz: number; span_s: number }
}
export interface ManifestInput {
  commit: string; pluginSha: string; core: { version: string; sha: string; desktop_build: string }
  isolation: Record<string, unknown>
  video: { path: string; sha256: string; start_epoch: number }
  sessions: SessionSpec[]; stills: StillSpec[]; windows: Record<string, CpuWindowSpec>; order: string[]
  rows: number; timeline: unknown[]; measured: Measured; files: { path: string; sha256: string }[]; capturedAt: string
  /** the evidence directory relative to the repo: 'evidence/v2' (default) or e.g. 'evidence/v2-1280x800' */
  rel?: string
  stripCheck: StripCheck
  sidebarCrops?: SidebarCrop[]
}

const FIELD_STATES = ['resting', 'working', 'needs_you', 'error']
const BUDGET = { idle_pp: 1.0, working_pp: 6.0 } // fixed before measuring (PLAN.md §4); never moved here

export function buildManifest(i: ManifestInput): Record<string, unknown> {
  const rel = i.rel ?? 'evidence/v2'
  if (i.stripCheck.states.length === 0) throw new Error('the strip check has no focused state: nothing was checked')
  const strip_check = {
    viewport: i.stripCheck.viewport, states: i.stripCheck.states,
    all_inside: i.stripCheck.states.every(s => s.inside), any_clipped: i.stripCheck.states.some(s => s.clipped),
  }
  const exclusions = Object.fromEntries(Object.entries(i.measured.pixels).filter(([, p]) => p.exclusion).map(([k, p]) => [k, p.exclusion]))
  const field_pixels: Record<string, Pixels> = {}
  for (const s of FIELD_STATES) {
    if (!(s in i.measured.pixels)) throw new Error(`no measured pixels for ${s}`)
    const { organs_detected, p95_dL, mean_dL, lowK, highK } = i.measured.pixels[s]
    field_pixels[s] = { organs_detected, p95_dL, mean_dL, lowK, highK }
  }
  const cpu = (n: string) => {
    if (!(n in i.measured.cpu)) throw new Error(`no CPU window ${n}`)
    return Math.round(i.measured.cpu[n].mean_pct * 100) / 100
  }
  const rest = i.measured.pixels.resting
  return {
    schema: 'cf2-evidence/1', captured_at: i.capturedAt, commit: i.commit, plugin_js_sha256: i.pluginSha, core: i.core, isolation: i.isolation,
    capture: {
      video: i.video.path, video_sha256: i.video.sha256, video_start_epoch: i.video.start_epoch, rows_total: i.rows, rows_with_swatch: i.rows,
      sessions: i.sessions, stills: i.stills, timeline: i.timeline, strip_check, sidebar_crops: i.sidebarCrops ?? [],
    },
    field_pixels,
    perf: {
      sessions: i.rows, window_s: 60, budget: BUDGET,
      idle: { on_pct: cpu('idle_on'), off_pct: cpu('idle_off') },
      working: { on_pct: cpu('working_on'), off_pct: cpu('working_off'), field_updates_per_s: Math.round(i.measured.field.updates_per_s * 100) / 100 },
    },
    extra: {
      resting_idle: i.measured.pixels['resting-idle'] ?? null,
      error_vs_resting_mean_dL: i.measured.pixels.error.mean_dL - rest.mean_dL,
      grounds: groundsOf(i.measured.pixels),
      bloom: Object.fromEntries(Object.entries(i.measured.pixels).filter(([k]) => k.endsWith('.bloom'))),
      field_sampler: i.measured.field,
      exclusions,
    },
    raw: {
      root: `${rel}/raw`, files: i.files,
      idle_window: { dom_dump: 'dom/idle-window.json' },
      cpu: { idle_on: i.windows.idle_on.file, idle_off: i.windows.idle_off.file, working_on: i.windows.working_on.file, working_off: i.windows.working_off.file,
        working_field: 'cpu/working.field.csv' },
      cpu_windows: Object.fromEntries(Object.entries(i.windows).map(([k, v]) => [k, { file: v.file, dom_dump: v.dom_dump, roles: v.roles }])),
      cpu_order: i.order,
    },
  }
}

/** Per ground: the field states measured on it and error-minus-resting mean ΔL (REPORT ONLY: the conductor watches the margin).
 *  The first ground is the one the contract stills were taken on; `dark.*` stills are the extra ground when it could be captured. */
function groundsOf(px: Record<string, Pixels>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const on = (prefix: string, name: string) => {
    const get = (s: string) => px[prefix + s]
    if (!get('resting') || !get('error')) return
    out[name] = { ground: get('resting').ground ?? null, error_minus_resting_mean_dL: get('error').mean_dL - get('resting').mean_dL,
      mean_dL: Object.fromEntries(['resting', 'working', 'needs_you', 'error'].map(s => [s, get(s)?.mean_dL ?? null])) }
  }
  on('', 'default')
  on('dark.', 'dark')
  return out
}

/** Messages (each a list of painted parts, clipped to the region) with at least one part no exclusion rectangle covers:
 *  what a measured still would still show of the transcript. */
export function uncovered(messages: Box[][], exclude: Rect[], region: Rect): number {
  const [rx, ry, rw, rh] = region
  const shown = (b: Box): boolean => {
    const x0 = Math.max(rx, b.x), y0 = Math.max(ry, b.y), x1 = Math.min(rx + rw, b.x + b.w), y1 = Math.min(ry + rh, b.y + b.h)
    if (x1 <= x0 || y1 <= y0) return false
    return !exclude.some(e => e[0] <= x0 && e[1] <= y0 && e[0] + e[2] >= x1 && e[1] + e[3] >= y1)
  }
  return messages.filter(parts => parts.some(shown)).length
}
