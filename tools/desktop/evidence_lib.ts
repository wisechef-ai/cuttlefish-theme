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
