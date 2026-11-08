// The composer RIM (v2.1 §3): ONE system. Every state draws the same 10 px pill (same placement, same round caps, 1 px
// inset); only what fills the pill and how its outline is drawn changes, echoing the state's mark:
//   resting          the outline alone (hairline)         working   lobe trains (cloud) filling the pill
//   needs you        diagonal stripes, a firm outline      error     a pale wash in a broken, firmer outline
//   finished unseen  the outline plus one eye (ring and pupil) at the left third
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
/** The cloud trains repeat on this tile (the adapter does not know the composer's width; a 600 px period is the design's tile). */
const TRAIN_TILE = 600
/** Five train shapes (lobe radii), cycled; spacing between trains is 40 px plus a seeded-looking step (k·37 mod 70). */
const TRAINS: readonly (readonly number[])[] = [[3.2, 4.6, 3.6], [3.8, 5, 4, 2.8], [3, 4.2], [3.6, 5, 4], [3, 4.4, 3.2]]

/** The lobe circles of the cloud trains over one tile: lobe i of a train sits 1.15·r past the one before it. */
function trainCircles(h: number, c: string): RimNode[] {
  const out: RimNode[] = []
  let x = 26, k = 0
  while (x < TRAIN_TILE - 40) {
    const t = TRAINS[k++ % TRAINS.length]
    let lx = x
    for (const r of t) {
      out.push({ tag: 'circle', attrs: { cx: Number(lx.toFixed(2)), cy: h / 2, r, fill: c } })
      lx += 1.15 * r
    }
    x = lx + 40 + ((k * 37) % 70)
  }
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
      const stripes: RimNode = { tag: 'pattern', attrs: { id: STRIPE_ID, width: 12, height: h, patternUnits: 'userSpaceOnUse', patternTransform: 'skewX(-45)' },
        children: [{ tag: 'rect', attrs: { x: 0, y: 0, width: 6, height: h, fill: pal.chroma } }] }
      return finish([{ tag: 'defs', attrs: {}, children: [clip, stripes] }, cap([fillAll(`url(#${STRIPE_ID})`)]), pill(pal.chroma, 1.5)], i)
    }
    case 'blanch':
      // the pale wash fills the pill; the outline is the firmer, broken frame (the mark's hollow square, drawn as a band)
      body = [{ tag: 'defs', attrs: {}, children: [clip] }, cap([fillAll(pal.blanch, { 'fill-opacity': 0.38 })]), pill(pal.blanch, 3, '40 14')]
      break
    case 'eyespot':
      body = [{ tag: 'defs', attrs: {}, children: [clip] }, pill(pal.chroma, 1),
        { tag: 'circle', attrs: { cx: 14, cy: h / 2, r: 3.9, fill: pal.chroma, 'fill-opacity': 0.3, stroke: pal.chroma, 'stroke-width': 1.2 } },
        { tag: 'circle', attrs: { cx: 14, cy: h / 2, r: 2.4, fill: pal.spot } }]
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
