// The v2.1 state MARKS (spec §2): what a sidebar row swatch (24×16) and the status strip (21×14) show. Five coarse
// features read at 1× next to core's grey bullet, each a different silhouette:
//   resting         one small soft oval (three merged dots + two paper flecks)
//   working         a large solid flat-bottomed cloud (three lobes on a flat base)
//   needs you       a FILLED chip with three bold paper bars (the loudest mark)
//   error           a HOLLOW pale square with its top-right corner missing (never filled)
//   finished unseen a round ringed eye with one dark core (four iris flecks)
// Pure geometry in design units (px at 1×). A mark is `dots` (circles, the domain's Dot[]) plus `extras` (rect, ellipse,
// path: never circles), and colour comes from palette() in ink.ts: the pigment NAMES below are resolved there.
import type { PatternKind } from './types.ts'

export type PigmentKind = 'chroma' | 'soft' | 'blanch' | 'spot'
export type ExtraPigment = 'chroma' | 'blanch' | 'paper' | 'wash'

export interface GlyphDot { x: number; y: number; r: number; pigment: PigmentKind }

/** One non-circle shape of a mark. `fill` shapes take `alpha` as fill-opacity; `stroke` shapes take the stroke width.
 *  `paper` shapes are drawn in the chat ground colour, so they read as holes cut out of a filled mark. */
export interface GlyphExtra {
  k: 'rect' | 'ellipse' | 'path'
  pigment: ExtraPigment
  above?: boolean
  fill?: boolean
  alpha?: number
  stroke?: number
  x?: number; y?: number; w?: number; h?: number   // rect (rx = corner radius)
  cx?: number; cy?: number; rx?: number; ry?: number // ellipse
  d?: string                                       // path (M, H, V, L, Q, Z; no arcs)
}

/** A rendered extra: a plain SVG node (tag + raw attributes), already in the mark's scale and colour. */
export interface Shape { tag: 'rect' | 'ellipse' | 'path'; attrs: Record<string, number | string>; above: boolean }

/** The row swatch box, in px. The strip is this × STRIP_K. */
export const GLYPH_W = 24
export const GLYPH_H = 16
export const STRIP_K = 0.875

const circ = (x: number, y: number, r: number, pigment: PigmentKind): GlyphDot => ({ x, y, r, pigment })
const fillOf = (pigment: ExtraPigment, alpha = 1, above = false): Pick<GlyphExtra, 'pigment' | 'fill' | 'alpha' | 'above'> =>
  ({ pigment, fill: true, alpha, above })
const strokeOf = (pigment: ExtraPigment, width: number, above = false): Pick<GlyphExtra, 'pigment' | 'stroke' | 'above'> =>
  ({ pigment, stroke: width, above })

const GLYPHS: Record<PatternKind, { dots: GlyphDot[]; extras: GlyphExtra[] }> = {
  // resting (r4): one soft UPRIGHT oval (10 wide, ~15 tall) with a visible mottle of paper holes; quiet ink
  mottle: {
    dots: [circ(12, 4.7, 4.3, 'soft'), circ(12, 8, 5.0, 'soft'), circ(12, 11.3, 4.3, 'soft')],
    extras: [
      { k: 'ellipse', cx: 10.6, cy: 4.6, rx: 1.0, ry: 1.0, ...fillOf('paper', 0.9, true) },
      { k: 'ellipse', cx: 13.2, cy: 8.4, rx: 1.1, ry: 1.1, ...fillOf('paper', 0.9, true) },
      { k: 'ellipse', cx: 11, cy: 11.6, rx: 0.9, ry: 0.9, ...fillOf('paper', 0.9, true) },
    ],
  },
  // working (r4): a solid cloud, three lobes on a flat base (≈ 17 × 10)
  clouds: {
    dots: [circ(6.8, 9.6, 3.3, 'chroma'), circ(12.4, 7.8, 4.4, 'chroma'), circ(17.6, 9.8, 3.1, 'chroma')],
    extras: [{ k: 'rect', x: 3.8, y: 9.8, w: 16.2, h: 3.9, rx: 1.9, ...fillOf('chroma') }],
  },
  // needs you (r4): a FILLED chip with TWO bold paper bars (they survive at 1×)
  zebra: {
    dots: [[6, 5.5], [12, 5.5], [18, 5.5], [6, 10.5], [12, 10.5], [18, 10.5]].map(([x, y]) => circ(x, y, 2.8, 'chroma')),
    extras: [
      { k: 'rect', x: 2.5, y: 2, w: 19, h: 12, rx: 3, ...fillOf('chroma') },
      { k: 'path', d: 'M4 12 L12 4', ...strokeOf('paper', 3.4, true) },
      { k: 'path', d: 'M11.5 12 L19.5 4', ...strokeOf('paper', 3.4, true) },
    ],
  },
  // error (r4): a HOLLOW pale frame, the top-right corner missing (a gap of 9 px of top edge + 7.5 px of right edge); never filled
  blanch: {
    dots: [circ(13, 1.5, 1.5, 'blanch'), circ(22, 9, 1.5, 'blanch')],
    extras: [
      { k: 'rect', x: 2, y: 1.5, w: 20, h: 13, rx: 1, ...fillOf('wash', 0.16) },
      { k: 'path', d: 'M13 1.5 H2 V14.5 H22 V9', ...strokeOf('blanch', 2.2) },
    ],
  },
  // finished unseen (r4): an almond / lens EYE: pale lens, crisp outline, iris ring, dark pupil, catch-light
  eyespot: {
    dots: [circ(3, 8, 0.7, 'chroma'), circ(21, 8, 0.7, 'chroma'), circ(12, 8, 2.8, 'spot')],   // LAST: the only 'spot' dot, role eyespot
    extras: [
      { k: 'path', d: 'M2 8 Q12 -2 22 8 Q12 18 2 8 Z', ...fillOf('chroma', 0.3) },
      { k: 'path', d: 'M2 8 Q12 -2 22 8 Q12 18 2 8 Z', ...strokeOf('chroma', 1.6) },
      { k: 'ellipse', cx: 12, cy: 8, rx: 4.4, ry: 4.4, ...strokeOf('chroma', 1.5) },
      { k: 'ellipse', cx: 13.3, cy: 6.6, rx: 0.9, ry: 0.9, ...fillOf('paper', 1, true) },
    ],
  },
}

/** The mark's dots in design units. An unknown base degrades to the calm mottle, never a throw. */
export function glyphOf(base: PatternKind): readonly GlyphDot[] {
  return Object.hasOwn(GLYPHS, base) ? GLYPHS[base].dots : GLYPHS.mottle.dots
}

/** The mark's non-circle shapes in design units, in draw order (below first; `above` ones are drawn after the dots). */
export function glyphExtras(base: PatternKind): readonly GlyphExtra[] {
  return Object.hasOwn(GLYPHS, base) ? GLYPHS[base].extras : GLYPHS.mottle.extras
}
