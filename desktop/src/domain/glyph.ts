// The state GLYPHS: what a row swatch (28×14) and the status strip show. The field speaks the language in
// texture, which is too fine at swatch size — a swatch there is a small PICTURE of the state, in the session's
// identity hue, the same shape for every session so the state reads before the hue does:
//   resting  = three soft dots (calm mottle)        working = a puffy cloud
//   needs you = three bold diagonal bars (zebra)    error   = a hollow pale ring (washed out)
//   finished unseen = one dark eye-spot in a pale halo
// Pure geometry: each spec is a circle in the 24×12 box with the ink (|dL| on the ground) it should show.
import type { PatternKind } from './types.ts'

export type PigmentKind = 'chroma' | 'blanch' | 'spot'
export interface GlyphDot { x: number; y: number; r: number; ink: number; pigment: PigmentKind }

/** The swatch box: 28×14 (O2.9 allows 28×16) — design units below are 24×12, scaled up by K. */
export const GLYPH_W = 28
export const GLYPH_H = 14
const K = GLYPH_W / 24
/** The eye-spot's ink on the ground (the field's ocellus uses the same). */
const SPOT_INK = 0.30

const MOTTLE: readonly GlyphDot[] = [
  { x: 6.5, y: 6.6, r: 2.3, ink: 0.24, pigment: 'chroma' },
  { x: 12, y: 4.4, r: 1.7, ink: 0.20, pigment: 'chroma' },
  { x: 17.5, y: 7.6, r: 2.1, ink: 0.22, pigment: 'chroma' },
]

const CLOUD: readonly GlyphDot[] = [
  { x: 7, y: 7.6, r: 3.2, ink: 0.15, pigment: 'chroma' },
  { x: 11.8, y: 5.4, r: 4.0, ink: 0.15, pigment: 'chroma' },
  { x: 16.8, y: 6.4, r: 3.6, ink: 0.15, pigment: 'chroma' },
  { x: 20.4, y: 8.2, r: 2.4, ink: 0.15, pigment: 'chroma' },
]

/** Three "/" bars, each a chain of four overlapping dots — bold, ink at the ceiling. */
const BARS: readonly GlyphDot[] = [0, 1, 2].flatMap(k =>
  [-3.6, -1.2, 1.2, 3.6].map((t): GlyphDot => ({ x: 5.5 + 6.5 * k + 0.8 * t, y: 6 - 1.1 * t, r: 1.5, ink: 0.30, pigment: 'chroma' })))

/** A hollow dashed oval of pale beads: the washed-out outline (twelve beads, clear gaps between them). */
const RING: readonly GlyphDot[] = Array.from({ length: 12 }, (_, i): GlyphDot => {
  const a = (2 * Math.PI * i) / 12
  return { x: 12 + 9.4 * Math.cos(a), y: 6 + 4.2 * Math.sin(a), r: 1.35, ink: 0.30, pigment: 'blanch' }
})

/** One bold dark eye-spot on a light chip: a pale block of small overlapping dots, the spot (LAST entry, the only
 *  'spot' pigment) at least twice the chip dots' radius. */
const EYE: readonly GlyphDot[] = [
  ...[3.2, 6, 8.8].flatMap(y => [4.6, 7.8, 11, 14.2, 17.4, 20.6].map((x): GlyphDot => ({ x, y, r: 1.55, ink: 0.10, pigment: 'chroma' }))),
  { x: 12, y: 6, r: 3.7, ink: SPOT_INK, pigment: 'spot' },
]

/** Design units (24×12) to the swatch box. */
function scaled(g: readonly GlyphDot[]): readonly GlyphDot[] {
  return g.map(d => ({ ...d, x: d.x * K, y: d.y * K, r: d.r * K }))
}

const GLYPHS: Record<PatternKind, readonly GlyphDot[]> = {
  mottle: scaled(MOTTLE), clouds: scaled(CLOUD), zebra: scaled(BARS), blanch: scaled(RING), eyespot: scaled(EYE),
}

/** The glyph of a pattern base, in the 28×14 box. An unknown base degrades to the calm mottle, never a throw. */
export function glyphOf(base: PatternKind): readonly GlyphDot[] {
  return Object.hasOwn(GLYPHS, base) ? GLYPHS[base] : GLYPHS.mottle
}

