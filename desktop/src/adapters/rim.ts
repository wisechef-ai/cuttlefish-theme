// The composer RIM (C1/C6): one clean thin band above the composer that echoes the state's glyph — never texture.
//   resting = a hairline          working = a row of overlapping cloud puffs   needs you = bold diagonal stripes
//   error   = broad pale dashes, colourless (the swatch's hollow dashed oval, drawn wide)    finished unseen = a hairline with one dark eye-spot
// Identity hue throughout (error is the near-achromatic pale pigment); the state speaks through shape and ink.
// The band is a tree of plain nodes, rendered as React elements (the surface) or as SVG text (the dev sheets).
import { alphaFor, hexToRgb, planGround, type GroundPlan, type PatternKind } from '../domain/index.ts'
import type { Jsx } from './svg.ts'

export interface RimNode { tag: string; attrs: Record<string, string | number>; children?: RimNode[] }
export interface RimInput { base: PatternKind; hueDeg: number; ground: string; intensity: number; height: number }

const SPOT_INK = 0.3
const STRIPE_ID = 'cf-rim-stripes'
const DASH_ID = 'cf-rim-dashes'

/** The fill + opacity that shows `ink` (|dL|) of a pigment on this ground. */
function inkOf(plan: GroundPlan, hex: string, maxDl: number, ink: number, intensity: number): Record<string, string | number> {
  const alpha = alphaFor(Math.min(0.3, ink * intensity), hexToRgb(hex), plan, maxDl)
  return { fill: hex, opacity: Number(alpha.toFixed(3)) }
}

/** The band's nodes for one pattern base; an unknown base degrades to the hairline. Width is '100%' of the composer. */
export function rimNodes(i: RimInput): RimNode[] {
  const plan = planGround(i.hueDeg, i.ground)
  const h = i.height
  const chroma = (ink: number) => inkOf(plan, plan.chroma, plan.chromaMaxDl, ink, i.intensity)
  const hair: RimNode = { tag: 'rect', attrs: { x: 0, y: h - 1, width: '100%', height: 1, ...chroma(0.08) } }
  switch (i.base) {
    case 'clouds':
      // the glyph's cloud, as a row: fourteen banks of six overlapping puffs (same family as the sidebar blob)
      return Array.from({ length: 14 }, (_, i): RimNode => ({
        tag: 'svg', attrs: { x: `${2 + 7 * i}%`, y: 0, width: 34, height: h, overflow: 'visible' },
        children: [[3, 0.38], [8, 0.5], [13, 0.46], [18, 0.5], [23, 0.46], [28, 0.38]].map(([cx, k]): RimNode => (
          { tag: 'circle', attrs: { cx, cy: h / 2, r: h * k, ...chroma(0.30) } })),
      }))
    case 'zebra':
      return [
        { tag: 'defs', attrs: {}, children: [{ tag: 'pattern', attrs: { id: STRIPE_ID, width: 12, height: h, patternUnits: 'userSpaceOnUse', patternTransform: 'skewX(-45)' },
          children: [{ tag: 'rect', attrs: { x: 0, y: 0, width: 6, height: h, ...chroma(0.30) } }] }] },
        { tag: 'rect', attrs: { x: 0, y: 0, width: '100%', height: h, fill: `url(#${STRIPE_ID})` } },
      ]
    case 'blanch': {
      // broad pale dashes (the swatch's hollow dashed oval, drawn wide): colourless, unlike every other band
      const dash = inkOf(plan, plan.blanch, plan.blanchMaxDl, 0.30, i.intensity)
      return [
        { tag: 'defs', attrs: {}, children: [{ tag: 'pattern', attrs: { id: DASH_ID, width: 30, height: h, patternUnits: 'userSpaceOnUse' },
          children: [{ tag: 'rect', attrs: { x: 2, y: 0.5, width: 20, height: h - 1, rx: 2.5, ...dash } }] }] },
        { tag: 'rect', attrs: { x: 0, y: 0, width: '100%', height: h, fill: `url(#${DASH_ID})` } },
      ]
    }
    case 'eyespot':
      return [hair, { tag: 'circle', attrs: { cx: h * 3, cy: h / 2, r: h * 0.46, ...inkOf(plan, plan.spot, plan.spotMaxDl, SPOT_INK, i.intensity) } }]
    default:
      return [hair]
  }
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
