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
  d?: string                                       // path (M, H, V, L only)
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
  mottle: {
    dots: [circ(8.4, 8.4, 2.9, 'soft'), circ(12, 8, 3.3, 'soft'), circ(15.6, 8.4, 2.9, 'soft')],
    extras: [
      { k: 'ellipse', cx: 10.6, cy: 7.2, rx: 0.8, ry: 0.8, ...fillOf('paper', 0.45, true) },
      { k: 'ellipse', cx: 14.2, cy: 9.2, rx: 0.7, ry: 0.7, ...fillOf('paper', 0.45, true) },
    ],
  },
  clouds: {
    dots: [circ(6.4, 8.9, 4.4, 'chroma'), circ(12.6, 6.6, 5.6, 'chroma'), circ(18.2, 9.2, 4.0, 'chroma')],
    extras: [{ k: 'rect', x: 2.4, y: 9, w: 19.8, h: 4.9, rx: 2.4, ...fillOf('chroma') }],
  },
  zebra: {
    dots: [[5, 5], [12, 5], [19, 5], [5, 11], [12, 11], [19, 11]].map(([x, y]) => circ(x, y, 3, 'chroma')),
    extras: [
      { k: 'rect', x: 0.75, y: 0.75, w: 22.5, h: 14.5, rx: 3.5, ...fillOf('chroma') },
      { k: 'path', d: 'M2.5 11.5 L11.5 2.5', ...strokeOf('paper', 2.4, true) },
      { k: 'path', d: 'M6.5 13.5 L17.5 2.5', ...strokeOf('paper', 2.4, true) },
      { k: 'path', d: 'M12.5 13.5 L21.5 4.5', ...strokeOf('paper', 2.4, true) },
    ],
  },
  blanch: {
    dots: [circ(13.4, 1.5, 1.6, 'blanch'), circ(22.5, 9.9, 1.6, 'blanch')],
    extras: [
      { k: 'rect', x: 2, y: 2, w: 20, h: 12, rx: 1, ...fillOf('wash', 0.14) },
      { k: 'path', d: 'M13.2 1.5 H1.5 V14.5 H22.5 V9.9', ...strokeOf('blanch', 2.4) },
    ],
  },
  eyespot: {
    dots: [
      ...[45, 135, 225, 315].map(a => {
        const t = (a * Math.PI) / 180
        return circ(12 + 5.5 * Math.cos(t), 8 + 5.5 * Math.sin(t), 0.6, 'chroma')
      }),
      circ(12, 8, 4.5, 'spot'),                                   // LAST: the only 'spot' dot, role eyespot
    ],
    extras: [
      { k: 'ellipse', cx: 12, cy: 8, rx: 7, ry: 7, ...fillOf('chroma', 0.3) },
      { k: 'ellipse', cx: 12, cy: 8, rx: 7, ry: 7, stroke: 1.6, pigment: 'chroma' },
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
