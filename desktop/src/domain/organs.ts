// The fixed chromatophore constellation: a blue-noise-ish jittered hex lattice seeded by the
// session lineage root (blake2b stream, never a language built-in hash). Organs NEVER move and
// never change count — a state only changes their expansion (radius/ink), exactly like the elastic
// sac of a real chromatophore (motif: origin/feat/sparse-dots-preview tools/dots_preview.py).
// The constellation is a pure function of (seed, width, height); a small memo cache keeps a
// <= 10 fps re-render cheap without observable state.

import { seededStream } from './blake2b.ts'

export interface Organ {
  x: number; y: number   // fixed position in surface coordinates
  r: number              // settled radius in px (state may contract it, never move it)
  u: number              // iid [0,1): the organ's tonic tone (mottle variance, twinkle)
  twinkle: boolean       // one of the few organs that pulse under `alive`
}

export interface Constellation { organs: Organ[]; medR: number }

const cache = new Map<string, Constellation>()

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b)
  const mid = s.length >> 1
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

/**
 * A jittered hex lattice of ~`target` organs over width x height, radii in the
 * [rLo, rHi] fraction of the pitch. Twinklers are exactly the floor(4%) brightest-toned
 * organs: a deterministic count, so the alive twinkle can never touch more than 5% of them.
 */
export function constellation(seed: string, width: number, height: number, target: number, rLo: number, rHi: number): Constellation {
  const key = `${seed}|${width}x${height}|${target}|${rLo}|${rHi}`
  const hit = cache.get(key)
  if (hit) return hit
  const w = Math.max(4, width), h = Math.max(4, height)
  const n = Math.max(8, Math.round(target))
  const pitch = Math.sqrt((w * h) / (0.866 * n))
  const rowH = pitch * 0.866
  const cols = Math.max(2, Math.ceil(w / pitch))
  const rows = Math.max(2, Math.ceil(h / rowH))
  const maxR = pitch * rHi
  const margin = Math.min(maxR + 0.4, w / 3, h / 3)
  const rnd = seededStream(seed, 'organs')
  const organs: Organ[] = []
  for (let r = 0; r < rows; r++) {
    const off = (r & 1) === 1 ? pitch / 2 : 0
    for (let c = 0; c < cols; c++) {
      const x0 = (c + 0.5) * pitch + off
      const y0 = (r + 0.5) * rowH
      if (x0 > w - margin + pitch * 0.2 || y0 > h - margin + rowH * 0.2) continue
      const u = rnd()
      const jx = (rnd() * 2 - 1) * pitch * 0.30
      const jy = (rnd() * 2 - 1) * rowH * 0.30
      organs.push({
        x: Math.min(w - margin, Math.max(margin, x0 + jx)),
        y: Math.min(h - margin, Math.max(margin, y0 + jy)),
        r: pitch * (rLo + (rHi - rLo) * rnd()),
        u,
        twinkle: false,
      })
    }
  }
  const nTw = Math.floor(organs.length * 0.04)
  const byTone = [...organs].sort((a, b) => b.u - a.u)
  for (let i = 0; i < nTw; i++) byTone[i].twinkle = true
  const out: Constellation = { organs, medR: median(organs.map(o => o.r)) }
  if (cache.size > 64) cache.clear()
  cache.set(key, out)
  return out
}

/** Where the single ocellus sits: central band, seeded — one spot, never on the edge. */
export function eyeSpotAt(seed: string, width: number, height: number): { x: number; y: number } {
  const rnd = seededStream(seed, 'eyespot')
  const x = width * (0.32 + 0.36 * rnd())
  const y = height * (0.30 + 0.40 * rnd())
  return { x, y }
}
