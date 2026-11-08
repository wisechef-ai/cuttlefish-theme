// The composer RIM (v2.1 §3): ONE system. Every state draws the same 10 px pill (same placement, same round caps, 1 px
// inset); only what fills the pill and how its outline is drawn changes, echoing the state's mark:
//   resting          the outline alone (hairline)         working   small CLOUDS (the mark in miniature) on the outline
//   needs you        a static warning band: two end chips of bold stripes, a firm outline between them
//   error            a pale wash and ONE broken line (a single gap)       finished unseen  the outline plus one lens-shaped eye at the left
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
/** The clouds repeat on this tile (the adapter does not know the composer's width; a 480 px period is the design's tile). */
const TRAIN_TILE = 480
/** One miniature cloud (the mark's three lobes on a flat base), 15.8 px wide, 8 px tall, left edge at `x`. */
function cloudNodes(x: number, c: string): RimNode[] {
  const n = (v: number): number => Number(v.toFixed(2))
  return [
    { tag: 'circle', attrs: { cx: n(x + 3.4), cy: 5.4, r: 2.5, fill: c } },
    { tag: 'circle', attrs: { cx: n(x + 7.2), cy: 4.1, r: 3.2, fill: c } },
    { tag: 'circle', attrs: { cx: n(x + 11.2), cy: 5.5, r: 2.7, fill: c } },
    { tag: 'rect', attrs: { x: n(x + 1.2), y: 5.3, width: 13.4, height: 3, rx: 1.5, fill: c } },
  ]
}
/** Clouds over one tile: first at x = 30, then every 70 px plus a step of (k·41 mod 64): irregular, never evenly beaded. */
function trainCircles(_h: number, c: string): RimNode[] {
  const out: RimNode[] = []
  let x = 30, k = 0
  while (x < TRAIN_TILE - 40) { out.push(...cloudNodes(x, c)); k++; x += 16 + 54 + ((k * 41) % 64) }
  return out
}

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
      const trains: RimNode = { tag: 'pattern', attrs: { id: TRAINS_ID, width: TRAIN_TILE, height: h, patternUnits: 'userSpaceOnUse' }, children: trainCircles(h, pal.chroma) }
      return finish([{ tag: 'defs', attrs: {}, children: [clip, trains] }, cap([fillAll(`url(#${TRAINS_ID})`)]), pill(pal.chroma, 1)], i)
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
    case 'blanch':
      // pale, washed, ONE line with ONE break (pathLength 1000: a 25-unit gap, ≈ 40 px at a 1300 px composer), lighter than v2.1's heavy dashed frame
      body = [{ tag: 'defs', attrs: {}, children: [clip] }, cap([fillAll(pal.blanch, { 'fill-opacity': 0.16 })]),
        { tag: 'rect', attrs: { ...pillAttrs(h), fill: 'none', stroke: pal.blanch, 'stroke-width': 1.6, pathLength: 1000, 'stroke-dasharray': '975 25', 'stroke-dashoffset': -80 } }]
      break
    case 'eyespot':
      // the outline plus ONE lens-shaped eye (the mark's almond, in miniature) at the left: pale lens, solid iris, dark pupil
      body = [{ tag: 'defs', attrs: {}, children: [clip] }, pill(pal.chroma, 1),
        { tag: 'path', attrs: { d: 'M8 5 Q20 -2 32 5 Q20 12 8 5 Z', fill: pal.chroma, 'fill-opacity': 0.3, stroke: pal.chroma, 'stroke-width': 1.2 } },
        { tag: 'circle', attrs: { cx: 20, cy: h / 2, r: 2.6, fill: pal.chroma } },
        { tag: 'circle', attrs: { cx: 20, cy: h / 2, r: 1.6, fill: pal.spot } }]
      break
    case 'mottle':
    default:
      body = [{ tag: 'defs', attrs: {}, children: [clip] }, pill(pal.chroma, 1)]
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
