/**
 * Pure helpers of the real-Desktop capture (dev only): /proc CPU maths, chromium process roles, CSV, hashing,
 * exclusion rectangles, raw-tree listing. No I/O except listRawFiles. Unit-tested in evidence_lib.test.ts.
 */
import { createHash } from 'node:crypto'
import * as fs from 'node:fs'
import * as path from 'node:path'

export type Role = 'renderer' | 'gpu' | 'main'
export type Rect = [number, number, number, number]
export interface Box { x: number; y: number; w: number; h: number }

const CLK_TCK = 100

/** utime + stime (clock ticks) of a /proc/<pid>/stat line; null when it is not one. The comm field may hold spaces and parens. */
export function parseStatTicks(text: string): number | null {
  const close = text.lastIndexOf(')')
  if (close < 0) return null
  const f = text.slice(close + 2).split(' ')
  if (f.length < 20) return null // utime and stime are fields 14 and 15 of the full line: indexes 11 and 12 here
  const u = Number(f[11]), s = Number(f[12])
  return Number.isFinite(u) && Number.isFinite(s) ? u + s : null
}

/** Percent of ONE core over `dtS` seconds between two tick counters. */
export function cpuPct(prevTicks: number, curTicks: number, dtS: number): number {
  if (!(dtS > 0)) throw new Error(`interval must be positive, got ${dtS}`)
  if (curTicks < prevTicks) throw new Error(`tick counter went backwards (${prevTicks} -> ${curTicks})`)
  return ((curTicks - prevTicks) / CLK_TCK / dtS) * 100
}

/** The chromium role of a process from its command line; the app's own root pid is `main`; anything else is not sampled. */
export function roleOf(cmdline: string, isAppRoot: boolean): Role | null {
  const m = cmdline.match(/--type=([\w-]+)/)
  if (m === null) return isAppRoot ? 'main' : null
  if (m[1] === 'renderer') return 'renderer'
  return m[1] === 'gpu-process' ? 'gpu' : null
}

export function csvOf(header: string[], rows: (string | number)[][]): string {
  return [header.join(','), ...rows.map(r => r.join(','))].join('\n') + '\n'
}

export function sha256Hex(data: string | Buffer): string {
  return createHash('sha256').update(data).digest('hex')
}

/** Boxes → integer [x,y,w,h] rectangles padded by `pad`, clipped to `region`; empty and off-region boxes are dropped. */
export function clipRects(boxes: Box[], region: Rect, pad: number): Rect[] {
  const [rx, ry, rw, rh] = region
  const out: Rect[] = []
  for (const b of boxes) {
    if (!(b.w > 0 && b.h > 0)) continue
    const x0 = Math.max(rx, Math.floor(b.x - pad)), y0 = Math.max(ry, Math.floor(b.y - pad))
    const x1 = Math.min(rx + rw, Math.ceil(b.x + b.w + pad)), y1 = Math.min(ry + rh, Math.ceil(b.y + b.h + pad))
    if (x1 > x0 && y1 > y0) out.push([x0, y0, x1 - x0, y1 - y0])
  }
  return out
}

/** Pixels covered by the union of the rectangles (overlaps counted once). */
export function unionCoverage(rects: Rect[]): number {
  const seen = new Set<string>()
  for (const [x, y, w, h] of rects) for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) seen.add(`${i},${j}`)
  return seen.size
}

export function windowFacts(ts: number[]): { first: number; last: number; span: number; maxGap: number } {
  if (ts.length < 2) throw new Error('a window needs two samples at least')
  let maxGap = 0
  for (let i = 1; i < ts.length; i++) maxGap = Math.max(maxGap, ts[i] - ts[i - 1])
  return { first: ts[0], last: ts[ts.length - 1], span: ts[ts.length - 1] - ts[0], maxGap }
}

/** Every file under `root` (recursive), relative posix path + sha256 of its bytes, sorted by path. */
export function listRawFiles(root: string): { path: string; sha256: string }[] {
  const rels: string[] = []
  const walk = (dir: string) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name)
      if (e.isDirectory()) walk(p)
      else if (e.isFile()) rels.push(path.relative(root, p).split(path.sep).join('/'))
    }
  }
  walk(root)
  return rels.sort().map(rel => ({ path: rel, sha256: sha256Hex(fs.readFileSync(path.join(root, rel))) }))
}

// ---- ev3 -----------------------------------------------------------------------------------------------------------------
/** The contract's own share rule (tests/acceptance/raw_evidence.py region_ok): exclusions may cover at most 25 % of a region. */
export const MAX_EXCLUDED_SHARE = 0.25
/** The harness' sanity floor for a small window: at least this many field pixels must stay measurable. Fixed here, never tuned to a run. */
export const MIN_MEASURED_PX = 200_000

export interface ExclusionVerdict { area: number; excluded: number; share: number; measured: number; ok: boolean; reason: string | null }

/** The honest small-window rule. A share above 25 % is allowed when at least MIN_MEASURED_PX pixels remain measurable (the reason
 *  reports it); fewer than that fails whatever the share. Both numbers are always reported. Mirrored in measure.py (exclusion_verdict). */
export function exclusionVerdict(area: number, excluded: number, minMeasured: number = MIN_MEASURED_PX): ExclusionVerdict {
  if (!(area > 0)) throw new Error(`region area must be positive, got ${area}`)
  const measured = area - excluded, share = excluded / area
  const base = { area, excluded, share, measured }
  if (measured < minMeasured) return { ...base, ok: false, reason: `${measured} px measured < ${minMeasured} px: too little field left to measure` }
  if (share <= MAX_EXCLUDED_SHARE) return { ...base, ok: true, reason: null }
  return { ...base, ok: true, reason: `small window: ${Math.round(share * 100)}% excluded (> 25%), ${measured} px measured (>= ${minMeasured})` }
}

export interface StripInput { box: Box | null; viewport: { w: number; h: number }; truncated: boolean; textOverflow: string }
export interface StripVerdict { box: Box | null; inside: boolean; clipped: boolean; text_overflow: string }

/** The status strip's DOM box against the viewport, and whether its text is cut (any element scrolls wider than its box). */
export function stripVerdict(s: StripInput): StripVerdict {
  const b = s.box
  const inside = b !== null && b.x >= 0 && b.y >= 0 && b.x + b.w <= s.viewport.w && b.y + b.h <= s.viewport.h
  return { box: b, inside, clipped: s.truncated, text_overflow: s.textOverflow }
}

/** The padded union of the boxes (the sidebar's rows), clipped to the screen; null when there is nothing to crop. */
export function sidebarRect(boxes: Box[], screen: { w: number; h: number }, pad: number): Rect | null {
  const live = boxes.filter(b => b.w > 0 && b.h > 0)
  if (live.length === 0) return null
  const x0 = Math.max(0, Math.floor(Math.min(...live.map(b => b.x)) - pad))
  const y0 = Math.max(0, Math.floor(Math.min(...live.map(b => b.y)) - pad))
  const x1 = Math.min(screen.w, Math.ceil(Math.max(...live.map(b => b.x + b.w)) + pad))
  const y1 = Math.min(screen.h, Math.ceil(Math.max(...live.map(b => b.y + b.h)) + pad))
  if (x1 <= x0 || y1 <= y0) return null
  return [x0, y0, x1 - x0, y1 - y0]
}

/** ffmpeg -vf for a crop followed by a nearest-neighbour upscale: pixels stay square (a reviewer's 2x crop, not a blur). */
export function cropFilter(r: Rect, factor: number): string {
  if (!(r[2] > 0 && r[3] > 0)) throw new Error(`empty crop ${JSON.stringify(r)}`)
  return `crop=${r[2]}:${r[3]}:${r[0]}:${r[1]},scale=iw*${factor}:ih*${factor}:flags=neighbor`
}

/** Distance of a point from the centre of a rectangle: 0 at the centre, 1 at the middle of an edge (per axis, normalised). */
export function centreDistance(cx: number, cy: number, r: Rect): number {
  const dx = (cx - (r[0] + r[2] / 2)) / (r[2] / 2), dy = (cy - (r[1] + r[3] / 2)) / (r[3] / 2)
  return Math.hypot(dx, dy)
}

// ---- hygiene -------------------------------------------------------------------------------------------------------------
/** A committed evidence file carries no user home and no tailnet address: the home prefix becomes <home>/ (the sandbox
 *  segments after it stay, so a relative path still has its sandboxes part), an address in the tailnet (CGNAT) range becomes <tailnet-ip>. */
export function scrubPath(s: string): string {
  return s.replace(/\/home\/[^/\s"']+\//g, '<home>/')
    .replace(/\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b/g, '<tailnet-ip>')
}

/** scrubPath on every string of a JSON-like value (a new value; the input is not changed). */
export function scrubDeep<T>(v: T): T {
  if (typeof v === 'string') return scrubPath(v) as unknown as T
  if (Array.isArray(v)) return v.map(x => scrubDeep(x)) as unknown as T
  if (v !== null && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, scrubDeep(x)])) as T
  return v
}
