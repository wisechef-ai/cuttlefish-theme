// The composer RIM (v2.1 §3): ONE system. Every state draws the same 10 px pill (same placement, same round caps, 1 px
// inset); only what fills the pill and how its outline is drawn changes, echoing the state's mark:
//   resting          ONE quiet hairline (no pill)                       working   a clean outline, a faint tint, five larger soft clouds
//   needs you        a static warning band: two end chips of bold stripes, a firm outline between them
//   error            the pale top edge of a box with ONE gap     finished unseen  the outline plus one lens-shaped eye at the left
// The band is a tree of plain nodes, rendered as React elements (the surface) or as SVG text (the dev sheets). Static:
// rendering it never wakes the loop (P3.2b). Colours are opaque, from palette() in ink.ts (identity, never state).
import { palette, type Palette, type PatternKind } from '../domain/index.ts'
import type { Jsx } from './svg.ts'

/** The composer rim's height in px (spec §3: the pill is 8.5 px tall inside it). */
export const RIM_HEIGHT = 10

export interface RimNode { tag: string; attrs: Record<string, string | number>; children?: RimNode[] }
export interface RimInput { base: PatternKind; hueDeg: number; ground: string; intensity: number; height: number }

const CAP_ID = 'cf-rim-cap'
const TRAINS_ID = 'cf-rim-trains'
const STRIPE_ID = 'cf-rim-stripes'
/** Each warning chip of the needs-you band is this wide (px). */
const CHIP_W = 96
/** The one pill every state shares: 1 px inside the rim, round caps. */
function pillAttrs(h: number): Record<string, string | number> {
  return { x: 0.75, y: 0.75, width: '100%', height: h - 1.5, rx: (h - 1.5) / 2 }
}

/** The band's nodes for one pattern base; an unknown base degrades to the calm outline. */
export function rimNodes(i: RimInput): RimNode[] {
  const pal: Palette = palette(i.hueDeg, i.ground)
  const h = i.height
  const pill = (stroke: string, width: number, dash?: string): RimNode => ({
    tag: 'rect', attrs: { ...pillAttrs(h), fill: 'none', stroke, 'stroke-width': width, ...(dash ? { 'stroke-dasharray': dash } : {}) },
  })
  const clip: RimNode = { tag: 'clipPath', attrs: { id: CAP_ID }, children: [{ tag: 'rect', attrs: pillAttrs(h) }] }
  const cap = (children: RimNode[]): RimNode => ({ tag: 'g', attrs: { 'clip-path': `url(#${CAP_ID})` }, children })
  const fillAll = (fill: string, extra: Record<string, string | number> = {}): RimNode => ({
    tag: 'rect', attrs: { x: 0, y: 0, width: '100%', height: h, fill, ...extra },
  })
  let body: RimNode[]
  switch (i.base) {
    case 'clouds': {
      // r5: a clean pill outline, a faint tint inside, and FIVE larger soft clouds spaced evenly (one per 20 % of the width, via an
      // objectBoundingBox tile); the lobes share one group opacity so overlaps do not darken. Static: nothing moves.
      const cloud: RimNode = { tag: 'g', attrs: { opacity: 0.55, fill: pal.chroma }, children: [
        { tag: 'circle', attrs: { cx: 40, cy: 5.6, r: 3.2 } }, { tag: 'circle', attrs: { cx: 46.4, cy: 4.3, r: 4.2 } },
        { tag: 'circle', attrs: { cx: 52.8, cy: 5.6, r: 3.4 } }, { tag: 'rect', attrs: { x: 37, y: 5.4, width: 19.6, height: 3.1, rx: 1.5 } } ] }
      const tile: RimNode = { tag: 'pattern', attrs: { id: TRAINS_ID, x: 0, y: 0, width: 0.2, height: 1, patternUnits: 'objectBoundingBox', patternContentUnits: 'userSpaceOnUse' }, children: [cloud] }
      return finish([{ tag: 'defs', attrs: {}, children: [clip, tile] }, cap([fillAll(pal.chroma, { 'fill-opacity': 0.08 }), fillAll(`url(#${TRAINS_ID})`)]), pill(pal.chroma, 1.2)], i)
    }
    case 'zebra': {
      // a static warning BAND: a 96 px chip of bold stripes at each end (a clear chip end), the firm outline between them
      const stripes: RimNode = { tag: 'pattern', attrs: { id: STRIPE_ID, width: 12, height: h, patternUnits: 'userSpaceOnUse', patternTransform: 'skewX(-45)' },
        children: [{ tag: 'rect', attrs: { x: 0, y: 0, width: 6, height: h, fill: pal.chroma } }] }
      const left: RimNode = { tag: 'rect', attrs: { x: 0, y: 0, width: CHIP_W, height: h, fill: `url(#${STRIPE_ID})` } }
      const right: RimNode = { tag: 'rect', attrs: { x: '100%', y: 0, width: CHIP_W, height: h, fill: `url(#${STRIPE_ID})`, transform: `translate(${-CHIP_W} 0)` } }
      const endL: RimNode = { tag: 'rect', attrs: { x: CHIP_W, y: 0.75, width: 1.5, height: h - 1.5, fill: pal.chroma } }
      const endR: RimNode = { tag: 'rect', attrs: { x: '100%', y: 0.75, width: 1.5, height: h - 1.5, fill: pal.chroma, transform: `translate(${-CHIP_W - 1.5} 0)` } }
      return finish([{ tag: 'defs', attrs: {}, children: [clip, stripes] }, pill(pal.chroma, 1.5), cap([left, right]), endL, endR], i)
    }
    case 'blanch': {
      // r5: the TOP EDGE of a box, pale and thin, with its two short returns and ONE clear gap (56 px at 62 % of the width): a broken, blanched
      // border. No pill, no track, no thumb (the r4 pill with a dash gap read as a scrollbar).
      const T = 1.2, fill = pal.blanch
      body = [
        { tag: 'rect', attrs: { x: 0.75, y: 0.75, width: '62%', height: T, fill } },
        { tag: 'rect', attrs: { x: '62%', y: 0.75, width: '38%', height: T, fill, transform: 'translate(56 0)' } },
        { tag: 'rect', attrs: { x: 0.75, y: 0.75, width: T, height: h - 1.5, fill } },
        { tag: 'rect', attrs: { x: '100%', y: 0.75, width: T, height: h - 1.5, fill, transform: `translate(${-(0.75 + T)} 0)` } },
      ]
      break
    }
    case 'eyespot':
      // the outline plus ONE lens-shaped eye (the mark's almond, in miniature) at the left: pale lens, solid iris, dark pupil
      body = [{ tag: 'defs', attrs: {}, children: [clip] }, pill(pal.chroma, 1),
        { tag: 'path', attrs: { d: 'M8 5 Q20 -2 32 5 Q20 12 8 5 Z', fill: pal.chroma, 'fill-opacity': 0.3, stroke: pal.chroma, 'stroke-width': 1.2 } },
        { tag: 'circle', attrs: { cx: 20, cy: h / 2, r: 2.6, fill: pal.chroma } },
        { tag: 'circle', attrs: { cx: 20, cy: h / 2, r: 1.6, fill: pal.spot } }]
      break
    case 'mottle':
    default:
      // resting (r5): ONE quiet hairline in the soft ink (no pill, no second line)
      body = [{ tag: 'rect', attrs: { x: 0, y: h - 1, width: '100%', height: 1, fill: pal.soft } }]
  }
  return finish(body, i)
}

/** Intensity 0 switches the band off (the same dial as the marks): every drawn node is transparent. */
function finish(nodes: RimNode[], i: RimInput): RimNode[] {
  if (i.intensity > 0) return nodes
  return nodes.map(n => (n.tag === 'defs' ? n : { ...n, attrs: { ...n.attrs, opacity: 0 } }))
}

/** The nodes as React elements through the host's jsx factory. */
export function rimElement(jsx: Jsx, i: RimInput): unknown {
  const build = (n: RimNode): unknown => jsx(n.tag, { ...n.attrs, ...(n.children ? { children: n.children.map(build) } : {}) })
  return jsx('svg', { width: '100%', height: i.height, 'aria-hidden': true, children: rimNodes(i).map(build) })
}

/** The nodes as SVG text (dev contact sheets only). */
export function rimSvg(i: RimInput & { width: number }): string {
  const text = (n: RimNode): string => {
    const attrs = Object.entries(n.attrs).map(([k, v]) => ` ${k}="${typeof v === 'string' && v.endsWith('%') ? `${(parseFloat(v) / 100) * i.width}` : v}"`).join('')
    return `<${n.tag}${attrs}>${(n.children ?? []).map(text).join('')}</${n.tag}>`
  }
  return `<svg width="${i.width}" height="${i.height}">${rimNodes(i).map(text).join('')}</svg>`
}
