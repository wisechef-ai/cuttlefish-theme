// The renderers: field (XL, the focused chat's organ scatter on the user's own ground), swatch
// (S, every sidebar row) and strip (M, the status bar) — the same language at three scales —
// plus toSvg, an inert serialization for a data-URI background layer. Ink targets come from
// pattern.ts; this module turns a target |dL| into an alpha by exact inversion of the sRGB
// source-over composite the browser (and the acceptance instruments) perform. Pure throughout:
// same input, same dots, bit for bit.
import { effectiveDl, inkTargets, MAX_DL, planGround, twinkleFactor, type GroundPlan } from './pattern.ts'
import { bloomFactor } from './motion.ts'
import { constellation, eyeSpotAt, type Constellation } from './organs.ts'
import { deltaLOf, hexToRgb, rgbToHex, type Rgb } from './oklch.ts'
import type { Dot, FieldInput, PatternSpec, SwatchInput } from './types.ts'

const FIELD_TARGET = 190        // organs on a desktop-sized surface (~12 per classifier bin)
const FIELD_R = [0.062, 0.098] as const
const SWATCH_W = 24, SWATCH_H = 12, SWATCH_TARGET = 16, SWATCH_R = [0.30, 0.42] as const
const STRIP_W = 64, STRIP_H = 12, STRIP_TARGET = 20, STRIP_R = [0.24, 0.34] as const
const BLANCH_CONTRACT = 0.55    // error closes the organs: expansion shrinks, position holds
const SPOT_SCALE_FIELD = 5.4, SPOT_SCALE_SMALL = 2.6
const SPOT_DL = 0.156

/** Invert the composite: the alpha at which `pigment` shows `target` |dL| on the ground. */
export function alphaFor(target: number, pigRgb: Rgb, plan: GroundPlan, maxDl: number): number {
  if (!(target > 0)) return 0
  if (target >= maxDl) return 1
  let lo = 0, hi = 1
  for (let i = 0; i < 16; i++) {
    const mid = (lo + hi) / 2
    if (deltaLOf(pigRgb, mid, plan.groundRgb, plan.groundL) < target) lo = mid; else hi = mid
  }
  return (lo + hi) / 2
}

interface RenderCore {
  cons: Constellation
  plan: GroundPlan
  pigmentFor: (kind: PigmentKind) => { hex: string; rgb: Rgb; maxDl: number }
}

function organDots(spec: PatternSpec, core: RenderCore, seed: string, intensity: number, bloom: number,
                   tMs: number, motion: 'still' | 'alive' | 'off', targets: number[]): Dot[] {
  const pig = core.pigmentFor(organPigmentOf(spec.base))
  const contracted = spec.base === 'blanch'
  return core.cons.organs.map((o, i): Dot => ({
    x: o.x, y: o.y,
    r: contracted ? o.r * BLANCH_CONTRACT : o.r,
    color: pig.hex,
    alpha: alphaFor(effectiveDl(targets[i], intensity, bloom, twinkleFactor(o, i, seed, tMs, motion)), pig.rgb, core.plan, pig.maxDl),
    role: 'organ',
  }))
}

function eyeDot(core: RenderCore, seed: string, width: number, height: number, intensity: number, bloom: number, small: boolean): Dot {
  const pig = core.pigmentFor('spot')
  const at = eyeSpotAt(seed, width, height)
  const r = core.cons.medR * (small ? SPOT_SCALE_SMALL : SPOT_SCALE_FIELD)
  const margin = r + 0.5
  return {
    x: Math.min(width - margin, Math.max(margin, at.x)),
    y: Math.min(height - margin, Math.max(margin, at.y)),
    r,
    color: pig.hex,
    alpha: alphaFor(Math.min(MAX_DL, SPOT_DL * intensity * bloom), pig.rgb, core.plan, pig.maxDl),
    role: 'eyespot',
  }
}

type PigmentKind = 'chroma' | 'blanch' | 'spot'

function pigment(plan: GroundPlan, kind: PigmentKind): { hex: string; rgb: Rgb; maxDl: number } {
  if (kind === 'blanch') return { hex: plan.blanch, rgb: hexToRgb(plan.blanch), maxDl: plan.blanchMaxDl }
  if (kind === 'spot') return { hex: plan.spot, rgb: hexToRgb(plan.spot), maxDl: plan.spotMaxDl }
  return { hex: plan.chroma, rgb: hexToRgb(plan.chroma), maxDl: plan.chromaMaxDl }
}

/** Organs carry the identity pigment (the eye-spot base included: only the ocellus itself is dark). */
const organPigmentOf = (base: PatternSpec['base']): PigmentKind => (base === 'blanch' ? 'blanch' : 'chroma')

/** The background field: a sparse organ scatter on the user's own ground, never a fill. */
export function renderField(input: FieldInput): Dot[] {
  const plan = planGround(input.hueDeg, input.ground)
  const cons = constellation(input.seed, input.width, input.height, FIELD_TARGET, FIELD_R[0], FIELD_R[1])
  const targets = inkTargets(input.pattern, cons, input.width, input.height, plan, input.seed, {
    tMs: input.tMs, motion: input.motion, reducedMotion: input.reducedMotion, small: false,
  })
  const bloom = bloomFactor(input.sinceChangeMs, input.motion, input.reducedMotion)
  const core: RenderCore = { cons, plan, pigmentFor: k => pigment(plan, k) }
  // reduced motion is `off` for every time-dependent term (bloom above, twinkle here)
  const motion = input.reducedMotion ? 'off' : input.motion
  const dots = organDots(input.pattern, core, input.seed, input.intensity, bloom, input.tMs, motion, targets)
  if (input.pattern.base === 'eyespot') dots.push(eyeDot(core, input.seed, input.width, input.height, input.intensity, bloom, false))
  return dots
}

function renderSmall(input: SwatchInput, w: number, h: number, target: number, rLo: number, rHi: number):
  { dots: Dot[]; width: number; height: number } {
  const plan = planGround(input.hueDeg, input.ground)
  const cons = constellation(input.seed, w, h, target, rLo, rHi)
  const targets = inkTargets(input.pattern, cons, w, h, plan, input.seed, { tMs: 0, motion: 'still', reducedMotion: false, small: true })
  const core: RenderCore = { cons, plan, pigmentFor: k => pigment(plan, k) }
  const dots = organDots(input.pattern, core, input.seed, input.intensity, 1, 0, 'still', targets)
  if (input.pattern.base === 'eyespot') dots.push(eyeDot(core, input.seed, w, h, input.intensity, 1, true))
  return { dots, width: w, height: h }
}

/** The sidebar row swatch: the same language at swatch scale, visible at a glance. */
export function renderSwatch(input: SwatchInput): { dots: Dot[]; width: number; height: number } {
  return renderSmall(input, SWATCH_W, SWATCH_H, SWATCH_TARGET, SWATCH_R[0], SWATCH_R[1])
}

/** The status-bar strip. */
export function renderStrip(input: SwatchInput): { dots: Dot[]; width: number; height: number } {
  return renderSmall(input, STRIP_W, STRIP_H, STRIP_TARGET, STRIP_R[0], STRIP_R[1])
}

/** Plain decimal, no exponent, no trailing zeros: safe inside an SVG attribute. */
function num(v: number): string {
  const s = Math.abs(v) < 1e-4 ? '0' : v.toFixed(3)
  return s.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
}

/** An inert SVG of the dots: circles only, no scripts, no links, no external references. */
export function toSvg(dots: readonly Dot[], width: number, height: number): string {
  const circles: string[] = []
  for (const d of dots) {
    if (!(d.alpha > 0) || !(d.r > 0)) continue
    const c = rgbToHex(hexToRgb(d.color))
    circles.push(`<circle cx="${num(d.x)}" cy="${num(d.y)}" r="${num(d.r)}" fill="${c}" opacity="${num(d.alpha)}"/>`)
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${num(width)}" height="${num(height)}">${circles.join('')}</svg>`
}
