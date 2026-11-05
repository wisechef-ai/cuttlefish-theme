// ACCEPTANCE CONTRACT — measuring instruments (locked; see contract/README.md).
// Pure functions that MEASURE a rendered model. They never import the implementation.
// Their own correctness is pinned against published reference values in instruments.test.ts.

export interface Rgb { r: number; g: number; b: number }          // 0..255 sRGB
export interface Lab { L: number; a: number; b: number }           // OKLab
export interface Lch { L: number; C: number; h: number }           // OKLCH, h in degrees [0, 360)

/** The shape every renderer in desktop/src/domain returns (see contract/README.md §API). */
export interface Dot {
  x: number; y: number; r: number
  color: string            // '#rrggbb' — the organ's own pigment colour, before compositing
  alpha: number            // 0..1, composited over the ground
  role: 'organ' | 'eyespot'
}

export function hexToRgb(hex: string): Rgb {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) throw new Error(`not a #rrggbb colour: ${hex}`)
  const n = parseInt(m[1], 16)
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 }
}

const toLinear = (c: number): number => {
  const v = c / 255
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

/** sRGB → OKLab (Björn Ottosson 2020, the published matrices). */
export function rgbToOklab({ r, g, b }: Rgb): Lab {
  const R = toLinear(r), G = toLinear(g), B = toLinear(b)
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B)
  const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B)
  const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B)
  return {
    L: 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    a: 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
    b: 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
  }
}

export function oklabToLch({ L, a, b }: Lab): Lch {
  const h = (Math.atan2(b, a) * 180) / Math.PI
  return { L, C: Math.hypot(a, b), h: (h + 360) % 360 }
}

export const lchOf = (hex: string): Lch => oklabToLch(rgbToOklab(hexToRgb(hex)))

/** Source-over compositing in sRGB space (what a browser does for a non-linear-blended background layer). */
export function composite(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  const a = Math.min(1, Math.max(0, alpha))
  return { r: fg.r * a + bg.r * (1 - a), g: fg.g * a + bg.g * (1 - a), b: fg.b * a + bg.b * (1 - a) }
}

/** |ΔL| (OKLab) between a dot as it appears on the ground and the bare ground. */
export function dotDeltaL(d: Dot, ground: string): number {
  const bg = hexToRgb(ground)
  return Math.abs(rgbToOklab(composite(hexToRgb(d.color), d.alpha, bg)).L - rgbToOklab(bg).L)
}

/** Shortest angular distance in degrees. */
export const hueDistance = (a: number, b: number): number => {
  const d = Math.abs(((a - b) % 360 + 360) % 360)
  return Math.min(d, 360 - d)
}

export function mean(xs: readonly number[]): number {
  if (xs.length === 0) throw new Error('mean of empty sample')
  return xs.reduce((s, x) => s + x, 0) / xs.length
}

/** Nearest-rank percentile, p in (0, 100]. */
export function percentile(xs: readonly number[], p: number): number {
  if (xs.length === 0) throw new Error('percentile of empty sample')
  const s = [...xs].sort((a, b) => a - b)
  const rank = Math.ceil((p / 100) * s.length)
  return s[Math.min(s.length, Math.max(1, rank)) - 1]
}

export function median(xs: readonly number[]): number {
  if (xs.length === 0) throw new Error('median of empty sample')
  const s = [...xs].sort((a, b) => a - b)
  const mid = s.length >> 1
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2
}

const visible = (dots: readonly Dot[]): Dot[] => dots.filter(d => d.alpha > 0 && d.r > 0)

/** Mean and p95 of |ΔL| over every visible dot. */
export function lightnessStats(dots: readonly Dot[], ground: string): { mean: number; p95: number; n: number } {
  const v = visible(dots).map(d => dotDeltaL(d, ground))
  if (v.length === 0) return { mean: 0, p95: 0, n: 0 }
  return { mean: mean(v), p95: percentile(v, 95), n: v.length }
}

/** Fraction of the surface covered by visible discs (overlap ignored: an upper bound). */
export function coverage(dots: readonly Dot[], width: number, height: number): number {
  return visible(dots).reduce((s, d) => s + Math.PI * d.r * d.r, 0) / (width * height)
}

/** Mean OKLCH chroma of the visible dots' own pigment. */
export function meanChroma(dots: readonly Dot[]): number {
  const v = visible(dots)
  return v.length === 0 ? 0 : mean(v.map(d => lchOf(d.color).C))
}

/**
 * Banding spectrum. Every dot (visible or not: organ positions are fixed, so the bin census does not depend on the
 * state) is projected on the axis at `angleDeg`; each of `bins` bins holds the MEAN per-organ ink
 * (ink = ΔL of the dot on the ground; a closed or transparent organ inks 0). Returns the relative amplitudes
 * A_k = 2|DFT_k| / (bins × mean) for k = 1 .. bins/2 − 1. Empty bins take the profile mean (no false edges).
 */
export function bandSpectrum(dots: readonly Dot[], ground: string, width: number, height: number,
                             angleDeg: number, bins = BINS): number[] {
  const th = (angleDeg * Math.PI) / 180
  const ux = Math.cos(th), uy = Math.sin(th)
  const corners = [[0, 0], [width, 0], [0, height], [width, height]].map(([x, y]) => x * ux + y * uy)
  const lo = Math.min(...corners), hi = Math.max(...corners)
  const sum = new Array<number>(bins).fill(0)
  const cnt = new Array<number>(bins).fill(0)
  for (const d of dots) {
    if (d.role !== 'organ') continue
    const p = d.x * ux + d.y * uy
    const i = Math.min(bins - 1, Math.max(0, Math.floor(((p - lo) / (hi - lo)) * bins)))
    sum[i] += d.alpha > 0 && d.r > 0 ? dotDeltaL(d, ground) : 0
    cnt[i] += 1
  }
  const filled = sum.map((s, i) => (cnt[i] ? s / cnt[i] : NaN))
  const known = filled.filter(v => !Number.isNaN(v))
  const mu = known.length ? mean(known) : 0
  if (mu <= 0) return new Array<number>(bins / 2 - 1).fill(0)
  const prof = filled.map(v => (Number.isNaN(v) ? mu : v))
  const out: number[] = []
  for (let k = 1; k < bins / 2; k++) {
    let re = 0, im = 0
    for (let n = 0; n < bins; n++) {
      re += prof[n] * Math.cos((2 * Math.PI * k * n) / bins)
      im -= prof[n] * Math.sin((2 * Math.PI * k * n) / bins)
    }
    out.push((2 * Math.hypot(re, im)) / (bins * mu))
  }
  return out
}

export const CANONICAL_ANGLES = [0, 45, 90, 135] as const
/** 16 bins: ~9 organs per bin on the 1200×800 corpus surface keeps the random-tier noise floor well under the
 *  stripe / cloud thresholds while still resolving 3+ stripe periods (k = 3..7). */
export const BINS = 16

/** lowK = RMS of A_1..A_2 (one or two broad bands: clouds); highK = RMS of A_3.. (repeating stripes: zebra). */
export function banding(dots: readonly Dot[], ground: string, width: number, height: number):
  { lowK: number; highK: number; angle: number } {
  let best = { lowK: 0, highK: 0, angle: 0 }
  for (const a of CANONICAL_ANGLES) {
    const s = bandSpectrum(dots, ground, width, height, a)
    const lowK = Math.hypot(s[0], s[1])
    const highK = Math.hypot(...s.slice(2))
    if (Math.max(lowK, highK) > Math.max(best.lowK, best.highK)) best = { lowK, highK, angle: a }
  }
  return best
}

/** Largest radius over the median organ radius, and the same for the runner-up (an eye-spot is ONE outlier). */
export function spotRatios(dots: readonly Dot[]): { first: number; second: number } {
  const v = visible(dots)
  const organs = v.filter(d => d.role === 'organ').map(d => d.r)
  if (organs.length === 0) return { first: 0, second: 0 }
  const med = median(organs)
  const radii = v.map(d => d.r).sort((a, b) => b - a)
  return { first: radii[0] / med, second: (radii[1] ?? 0) / med }
}

/** Positions of the fixed organs, as a canonical string (state and time must never move an organ). */
export function organKey(dots: readonly Dot[]): string {
  return dots.filter(d => d.role === 'organ').map(d => `${d.x.toFixed(2)},${d.y.toFixed(2)}`).sort().join(';')
}
