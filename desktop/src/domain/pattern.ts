// The colour-pattern language (C8): what each state's organs DO. An organ's position is fixed
// (organs.ts); a pattern only chooses each organ's ink — the |dL| its pigment should show on the
// ground — and the ocellus. Clouds lie along angle 90 (a band that travels at constant speed, so
// there is no dead spot in the drift), zebra along angle 0 (columns): both canonical orientations
// of the locked classifier. Error blanches: near-achromatic and, on every ground, LIGHTER than
// the same session's resting organs while still visible. The constants were tuned against the
// locked classifier over 20 identities x 3 grounds (test/unit/language.test.ts measures margins).
// Pure: time arrives as tMs, entropy only from blake2b.
import { blake2b, seededStream, utf8 } from './blake2b.ts'
import { hexToLab, hexToRgb, oklchToHex, rgbToOklab, type Rgb } from './oklch.ts'
import type { Constellation, Organ } from './organs.ts'
import type { Motion, PatternSpec } from './types.ts'

/** Ink ceilings the contract pins: resting near-invisible (p95 <= 0.05), everything text-safe (p95 <= 0.20). */
export const REST_LO = 0.012
export const REST_HI = 0.046
/** The settled resting field: ink in [REST_FIELD_LO, REST_FIELD_LO + REST_FIELD_SPAN], mean 0.025 (what error is paler than). */
const REST_FIELD_LO = 0.014, REST_FIELD_SPAN = 0.022
export const REST_MEAN = REST_FIELD_LO + REST_FIELD_SPAN / 2
const ZEBRA_BRIGHT = 0.158, ZEBRA_DIM = 0.013
const CLOUD_BASE = 0.020, CLOUD_AMP = 0.125, CLOUD_SIGMA = 118
/** Error sits this much LIGHTER than resting (dark grounds can afford more); light grounds keep dl >= 0.012. */
const BLANCH_LIGHTER_DARK = 0.016
const BLANCH_LIGHTER_LIGHT = 0.012
/** Small-canvas (swatch/strip) inks: a row swatch must be visible (mean dL >= 0.08). */
const SWATCH_LO = 0.085, SWATCH_SPAN = 0.055
const SWATCH_ZEBRA_BRIGHT = 0.150, SWATCH_ZEBRA_DIM = 0.035
const SWATCH_CLOUD_BASE = 0.040, SWATCH_CLOUD_AMP = 0.135
/** Ink ceiling (MAX_DL) and the pigment headroom at full alpha (FULL_DL). */
export const MAX_DL = 0.30
const FULL_DL = 0.40
const CHROMA_C = 0.105, BLANCH_C = 0.02, SPOT_C = 0.09
const TWINKLE_AMP = 0.55, TWINKLE_P_MIN = 7000, TWINKLE_P_SPAN = 5000
/** Stripe count across the surface. The field's 8 (4 cycles ≈ 2 dot pitches per band) survives the chat region being a
 *  crop of the window — at 6 the fundamental sat between spectral bins 2 and 3 and read 0.49 in real pixels. */
const FIELD_CYCLES = 4
const ZEBRA_SWELL = 2.2, ZEBRA_SHRINK = 0.55, BLANCH_SWELL = 3.2
export const CLOUD_TRAVEL_MS = 18000                                  // one band pass across the height

/** Direction the chromatic organs sit relative to the ground: toward white on dark, toward black on light. */
const dirOf = (lg: number): 1 | -1 => (lg < 0.5 ? 1 : -1)

export interface GroundPlan {
  groundRgb: Rgb
  groundL: number
  dir: 1 | -1
  chroma: string   // the identity pigment (hue exact, C ~ 0.10)
  blanch: string   // the pale near-achromatic pigment (C <= 0.03)
  spot: string     // the ocellus pigment (dark)
  chromaMaxDl: number
  blanchMaxDl: number
  spotMaxDl: number
}

const planCache = new Map<string, GroundPlan>()
const dlAt = (hex: string, gl: number): number => Math.abs(rgbToOklab(hexToRgb(hex)).L - gl)

/** Pigments for one (hue, ground): the chromatic pigment lands ~FULL_DL away from the ground at full alpha. */
export function planGround(hueDeg: number, ground: string): GroundPlan {
  const key = `${hueDeg.toFixed(3)}|${ground}`
  const hit = planCache.get(key)
  if (hit) return hit
  const rgb = hexToRgb(ground)
  const gl = hexToLab(ground).L
  const dir = dirOf(gl)
  let lo = 0.04, hi = 0.97
  for (let i = 0; i < 20; i++) {
    const mid = (lo + hi) / 2
    const d = dlAt(oklchToHex(mid, CHROMA_C, hueDeg), gl)
    if (dir > 0 ? d < FULL_DL : d > FULL_DL) lo = mid; else hi = mid
  }
  const chroma = oklchToHex((lo + hi) / 2, CHROMA_C, hueDeg)
  const blanch = oklchToHex(Math.min(0.97, Math.max(0.05, gl + dir * 0.26)), BLANCH_C, hueDeg)
  const spot = oklchToHex(Math.min(0.97, Math.max(0.03, gl - 0.30)), SPOT_C, hueDeg)
  const plan: GroundPlan = {
    groundRgb: rgb, groundL: gl, dir, chroma, blanch, spot,
    chromaMaxDl: dlAt(chroma, gl), blanchMaxDl: dlAt(blanch, gl), spotMaxDl: dlAt(spot, gl),
  }
  if (planCache.size > 256) planCache.clear()
  planCache.set(key, plan)
  return plan
}

/** Error ink: visible on every ground (dl >= 0.012), and LIGHTER than the same session's resting organs. */
export function blanchDl(plan: GroundPlan, small: boolean): number {
  const rest = small ? SWATCH_LO + SWATCH_SPAN * 0.4 : REST_MEAN
  return plan.dir > 0 ? rest + BLANCH_LIGHTER_DARK : rest - BLANCH_LIGHTER_LIGHT
}

const jitter = (u: number, span: number): number => 1 + span * (u - 0.5)
/** Resting ink is EVEN on the field — a narrow band, no bright outliers (a hotspot among faint dots reads as a mistake). */
const mottleDl = (u: number, small: boolean): number =>
  small ? SWATCH_LO + SWATCH_SPAN * u ** 1.5 : REST_FIELD_LO + REST_FIELD_SPAN * u

/** The passing cloud: one soft band; under still/alive it travels at constant speed (no dead spots).
 *  Its per-organ jitter is drawn from ONE seeded stream per render (a single hash, consumed in
 *  organ order — deterministic call after call) and keyed on the organ INDEX, not its mottle draw
 *  u — two patterns of one session must disagree organ-by-organ or a swatch could not tell
 *  resting from working. */
function cloudDl(y: number, center: number, sigma: number, j: number, small: boolean): number {
  const base = small ? SWATCH_CLOUD_BASE : CLOUD_BASE
  const amp = small ? SWATCH_CLOUD_AMP : CLOUD_AMP
  const bump = Math.exp(-((y - center) ** 2) / (2 * sigma * sigma))
  return (base + amp * bump) * jitter(j, 0.28)
}

/** A swatch-sized surface has only two or three lattice rows: a band placed between rows would
 *  light them all equally and the cloud would read as the resting mottle. Keying the band to the
 *  organs' y-RANK (a soft window over the y-sorted order) guarantees the bright/dark split on any
 *  lattice, and still renders as a horizontal band. The centre keeps 2σ of room at each edge so
 *  the window's mass — and the swatch's mean ink — never collapses. */
function cloudRankDl(rank: number, centre: number, sigmaR: number, j: number): number {
  return (SWATCH_CLOUD_BASE + SWATCH_CLOUD_AMP * Math.exp(-((rank - centre) ** 2) / (2 * sigmaR * sigmaR))) * jitter(j, 0.28)
}

const cloudJitter = (seed: string): () => number => seededStream(seed, 'cloud-ink')

const DIAG = Math.SQRT1_2

/** Which stripe an organ sits in: the position along the 45° axis the classifier projects on, in `cycles` bright+dim
 *  pairs across the whole surface. Bright when the phase is in the first half of its cycle. */
export function zebraBright(o: Organ, width: number, height: number, scale: number): boolean {
  const hi = (width + height) * DIAG
  const cycles = Math.min(8, Math.max(2, Math.round(FIELD_CYCLES * scale)))
  return (((o.x + o.y) * DIAG) / hi * cycles) % 1 < 0.5
}

function zebraDl(bright: boolean, u: number): number {
  return bright ? ZEBRA_BRIGHT * jitter(u, 0.14) : ZEBRA_DIM * (1 + u * 0.5)
}

/** Per-organ size on the field: stripe organs swell inside a band and shrink in the gap (so the eye sees bands of
 *  big dots, not a scatter); error organs swell into soft pale blobs (washed out) instead of crisp dots. Positions
 *  never change. */
export function radiusFactors(spec: PatternSpec, cons: Constellation, width: number, height: number): number[] {
  if (spec.base === 'zebra') return cons.organs.map(o => (zebraBright(o, width, height, spec.scale) ? ZEBRA_SWELL : ZEBRA_SHRINK))
  if (spec.base === 'blanch') return cons.organs.map(() => BLANCH_SWELL)
  if (spec.base === 'mottle') return cons.organs.map(o => cons.medR / o.r)   // even dots at rest: no oversized one stands out
  return cons.organs.map(() => 1)
}

/** Swatch stripes are drawn by the glyph; the field's zebra is diagonal. */

export interface InkOptions {
  tMs: number
  motion: Motion
  reducedMotion: boolean
  small: boolean
}

/** The density/contrast dials, folded into one shaper around each pattern's own floor. */
interface Shaper { (raw: number): number }

/** The passing cloud on a swatch-sized surface: a soft window over the organs' y-rank. */
function smallCloudInk(cons: Constellation, seed: string, shape: Shaper): number[] {
  const n = cons.organs.length
  const rank = new Array<number>(n)
  cons.organs.map((o, i) => [o.y, i] as const).sort((a, b) => a[0] - b[0]).forEach(([, i], k) => { rank[i] = k })
  const sigmaR = Math.max(1, n / 6)
  const centre = 2 * sigmaR + (n - 1 - 4 * sigmaR) * hashUnit(seed, 'cloudrow')
  const draw = cloudJitter(seed)
  return cons.organs.map((_o, i) => shape(cloudRankDl(rank[i], centre, sigmaR, draw())))
}

/** The passing cloud on the field: one soft band travelling at constant speed (no dead spots). */
function fieldCloudInk(spec: PatternSpec, cons: Constellation, height: number, seed: string, opts: InkOptions, shape: Shaper): number[] {
  const sigma = CLOUD_SIGMA * spec.scale
  const travel = height + 2 * sigma
  const y0 = height * (0.28 + 0.44 * hashUnit(seed, 'cloud'))
  const moving = opts.motion !== 'off' && !opts.reducedMotion
  const center = moving ? -sigma + (((y0 + sigma) + (travel * opts.tMs) / CLOUD_TRAVEL_MS) % travel) : y0
  const draw = cloudJitter(seed)
  return cons.organs.map(o => shape(cloudDl(o.y, center, sigma, draw(), false)))
}

/** The density/contrast dials folded around each pattern's floor, and the mottle mapper over it. */
function shaperFor(spec: PatternSpec, small: boolean): { shape: Shaper; mottle: (o: Organ) => number } {
  const amp = 0.7 + 0.3 * spec.density
  const span = 0.6 + 0.4 * spec.contrast
  const floor = small ? SWATCH_CLOUD_BASE : CLOUD_BASE
  const shape: Shaper = raw => floor + (raw - floor) * span * amp
  const mottle = (o: Organ): number => shape(mottleDl(o.u, small) * (spec.base === 'eyespot' ? 0.8 : 1))
  return { shape, mottle }
}

/** Per-organ target ink (|dL| on the ground) for one pattern, before intensity and bloom. */
export function inkTargets(spec: PatternSpec, cons: Constellation, width: number, height: number,
                           plan: GroundPlan, seed: string, opts: InkOptions): number[] {
  const { shape, mottle } = shaperFor(spec, opts.small)
  switch (spec.base) {
    case 'clouds':
      return opts.small ? smallCloudInk(cons, seed, shape) : fieldCloudInk(spec, cons, height, seed, opts, shape)
    case 'zebra':
      return cons.organs.map(o => shape(zebraDl(zebraBright(o, width, height, spec.scale), o.u)))
    case 'blanch':
      return cons.organs.map(() => blanchDl(plan, opts.small))
    case 'mottle':
    case 'eyespot':
      return cons.organs.map(mottle)
    default:
      return cons.organs.map(() => REST_LO)
  }
}

/** The alive twinkle: a deterministic few organs pulse slowly (never under still/off/reduced). */
export function twinkleFactor(o: Organ, index: number, seed: string, tMs: number, motion: Motion): number {
  if (motion !== 'alive' || !o.twinkle) return 1
  const p = TWINKLE_P_MIN + TWINKLE_P_SPAN * hashUnit(seed, `twinkle:${index}`)
  const phase = 2 * Math.PI * hashUnit(seed, `phase:${index}`)
  return 1 + TWINKLE_AMP * Math.sin((2 * Math.PI * tMs) / p + phase)
}

/** Ink with the intensity dial, the twinkle and the bloom applied, capped at MAX_DL. */
export const effectiveDl = (target: number, intensity: number, bloom: number, twinkle: number): number =>
  Math.min(MAX_DL, target * intensity * bloom * twinkle)

/** A deterministic uniform [0,1) from (seed, domain) — blake2b, never a language hash. */
export function hashUnit(seed: string, domain: string): number {
  const d = blake2b(utf8(`${seed}\0${domain}`), 8)
  let n = 0
  for (const b of d) n = n * 256 + b
  return n / 2 ** 64
}
