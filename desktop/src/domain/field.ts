// The renderers: field (XL, the focused chat's organ scatter on the user's own ground), swatch
// (S, every sidebar row) and strip (M, the status bar) — the same language at three scales —
// plus toSvg, an inert serialization for a data-URI background layer. Ink targets come from
// pattern.ts; this module turns a target |dL| into an alpha by exact inversion of the sRGB
// source-over composite the browser (and the acceptance instruments) perform. Pure throughout:
// same input, same dots, bit for bit.
import { effectiveDl, inkTargets, MAX_DL, planGround, radiusFactors, twinkleFactor, type GroundPlan } from './pattern.ts'
import { bloomFactor } from './motion.ts'
import { constellation, eyeSpotAt, type Constellation } from './organs.ts'
import { GLYPH_H, GLYPH_W, glyphExtras, glyphOf, STRIP_K, type GlyphExtra, type Shape } from './glyph.ts'
import { palette, type Palette } from './ink.ts'
import { deltaLOf, hexToRgb, rgbToHex, type Rgb } from './oklch.ts'
import type { Dot, FieldInput, PatternSpec, SwatchInput } from './types.ts'

const FIELD_TARGET = 190        // organs on a desktop-sized surface (~12 per classifier bin)
const FIELD_R = [0.062, 0.098] as const
const SPOT_SCALE_FIELD = 4.3
const SPOT_DL = 0.50
/** Reading lane: organs left of this fraction of the width are drawn smaller (radius only: the locked tests are per-dot ink; the median organ must stay near the right half's). */
const LANE_FRAC = 0.60, LANE_PX = 704, LANE_MAX = 0.70, TOP_PX = 64, BOTTOM = 0.12, DENSITY = 1.6

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
                   tMs: number, motion: 'still' | 'alive' | 'off', targets: number[], scales: number[]): Dot[] {
  const pig = core.pigmentFor(organPigmentOf(spec.base))
  return core.cons.organs.map((o, i): Dot => ({
    x: o.x, y: o.y,
    r: o.r * scales[i],
    color: pig.hex,
    alpha: alphaFor(effectiveDl(targets[i], intensity, bloom, twinkleFactor(o, i, seed, tMs, motion)), pig.rgb, core.plan, pig.maxDl),
    role: 'organ',
  }))
}

function eyeDot(core: RenderCore, seed: string, width: number, height: number, intensity: number, bloom: number): Dot {
  const pig = core.pigmentFor('spot')
  const at = eyeSpotAt(seed, width, height)
  const r = core.cons.medR * SPOT_SCALE_FIELD
  const margin = r + 0.5
  return {
    x: Math.min(width - margin, Math.max(margin, at.x)),
    y: Math.min(height - margin, Math.max(margin, at.y)),
    r,
    color: pig.hex,
    alpha: alphaFor(Math.min(pig.maxDl, SPOT_DL * intensity * bloom), pig.rgb, core.plan, pig.maxDl),
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
  // THE READING LANE. Organs live only in the open region of the surface: right of `lane` (the text and cards sit on the left;
  // measured on the real Desktop: cards end 680 px from the surface's left edge), below the header (64 px) and above the composer (12 %).
  const laneFrac = Math.min(LANE_MAX, Math.max(LANE_FRAC, LANE_PX / input.width))
  const lane = laneFrac * input.width
  const top = Math.min(0.12 * input.height, Math.max(0.05 * input.height, TOP_PX))
  const rw = input.width - lane, rh = input.height * (1 - BOTTOM) - top
  const local = constellation(input.seed, rw, rh, Math.round(FIELD_TARGET * (rw * rh) / (input.width * input.height) * DENSITY), FIELD_R[0], FIELD_R[1])
  const cons = { ...local, organs: local.organs.map(o => ({ ...o, x: o.x + lane, y: o.y + top })) }
  // clouds travel over the open region only; every other pattern is read by the classifier against the whole surface, so it keeps whole-surface coordinates
  const clouds = input.pattern.base === 'clouds'
  const targets = clouds
    ? inkTargets(input.pattern, local, rw, rh, plan, input.seed, { tMs: input.tMs, motion: input.motion, reducedMotion: input.reducedMotion, small: false })
    : inkTargets(input.pattern, cons, input.width, input.height, plan, input.seed, { tMs: input.tMs, motion: input.motion, reducedMotion: input.reducedMotion, small: false })
  const bloom = bloomFactor(input.sinceChangeMs, input.motion, input.reducedMotion)
  const core: RenderCore = { cons, plan, pigmentFor: k => pigment(plan, k) }
  // reduced motion is `off` for every time-dependent term (bloom above, twinkle here)
  const motion = input.reducedMotion ? 'off' : input.motion
  const scales = radiusFactors(input.pattern, cons, input.width, input.height)
  const dots = organDots(input.pattern, core, input.seed, input.intensity, bloom, input.tMs, motion, targets, scales)
  if (input.pattern.base === 'eyespot') dots.push(eyeDot(core, input.seed, input.width, input.height, input.intensity, bloom))
  return dots
}

/** What a mark is drawn with: the pigment's colour, and the shape's paint at the mark's scale (`k`) and dial (`on`). */
function shapeOf(e: GlyphExtra, pal: Palette, k: number, on: boolean): Shape {
  const colour = pal[e.pigment]
  const paint: Record<string, number | string> = e.stroke !== undefined
    ? { fill: 'none', stroke: colour, 'stroke-width': e.stroke * k, 'stroke-linejoin': 'miter', 'stroke-opacity': on ? 1 : 0 }
    : { fill: colour, 'fill-opacity': on ? (e.alpha ?? 1) : 0 }
  const geometry: Record<string, number | string> = e.k === 'rect'
    ? { x: (e.x ?? 0) * k, y: (e.y ?? 0) * k, width: (e.w ?? 0) * k, height: (e.h ?? 0) * k, rx: (e.rx ?? 0) * k }
    : e.k === 'ellipse'
      ? { cx: (e.cx ?? 0) * k, cy: (e.cy ?? 0) * k, rx: (e.rx ?? 0) * k, ry: (e.ry ?? 0) * k }
      : { d: (e.d ?? '').replace(/-?\d*\.?\d+/g, m => String(Number(m) * k)) }
  return { tag: e.k, attrs: { ...geometry, ...paint }, above: e.above === true }
}

/** A mark at scale k (1: the row swatch, 24×16; STRIP_K: the status strip, 21×14). OPAQUE: the dots are solid and the
 *  dial acts only as on/off (any intensity above 0 is full, between 0 and 1 is the dot's alpha), so the mark's shape and
 *  ink never depend on a fade. */
function renderMark(input: SwatchInput, k: number): { dots: Dot[]; width: number; height: number; extras: Shape[] } {
  const pal = palette(input.hueDeg, input.ground)
  const alpha = input.intensity > 0 ? Math.min(1, input.intensity) : 0
  const dots = glyphOf(input.pattern.base).map((g): Dot => ({
    x: g.x * k, y: g.y * k, r: g.r * k, color: pal[g.pigment], alpha,
    role: g.pigment === 'spot' ? 'eyespot' : 'organ',
  }))
  const extras = glyphExtras(input.pattern.base).map(e => shapeOf(e, pal, k, alpha > 0))
  return { dots, width: GLYPH_W * k, height: GLYPH_H * k, extras }
}

/** The sidebar row swatch: the state's mark in the session's hue, legible at a glance. */
export function renderSwatch(input: SwatchInput): { dots: Dot[]; width: number; height: number; extras: Shape[] } {
  return renderMark(input, 1)
}

/** The status-bar strip: the same mark at ×0.875, once, beside its words. */
export function renderStrip(input: SwatchInput): { dots: Dot[]; width: number; height: number; extras: Shape[] } {
  return renderMark(input, STRIP_K)
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
