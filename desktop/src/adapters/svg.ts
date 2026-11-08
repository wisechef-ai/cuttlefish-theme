// The SVG element builder the surfaces share: the domain's dots as React
// elements with the RAW numbers — no rounding, no reformatting — so what a
// sidebar swatch paints is bit-for-bit what the domain computed (the property
// tests compare exactly this against their oracle). The jsx factory is passed
// IN, keeping this module pure and free of the SDK.
export type Jsx = (type: unknown, props: Record<string, unknown>) => unknown

export interface DotLike {
  x: number
  y: number
  r: number
  color: string
  alpha: number
}

/** Every visible dot as a <circle>: zero-ink dots are skipped, not drawn hollow. */
export function dotElements(jsx: Jsx, dots: readonly DotLike[]): unknown[] {
  const out: unknown[] = []
  for (const d of dots) {
    if (!(d.alpha > 0) || !(d.r > 0)) continue
    out.push(jsx('circle', { cx: d.x, cy: d.y, r: d.r, fill: d.color, opacity: d.alpha }))
  }
  return out
}

/** A non-circle shape of a mark: its SVG tag and raw attributes (the domain has already scaled and coloured it). */
export interface ShapeLike {
  tag: string
  attrs: Record<string, unknown>
  above: boolean
}

/** The root <svg> carrying the surface attributes, the mark's extras and its dots. Extras draw BELOW the dots unless marked
 *  `above` (the paper bars and flecks sit on top of a filled mark); a mark with no extras is just its dots. */
export function svgElement(
  jsx: Jsx,
  box: { width: number; height: number },
  attrs: Record<string, unknown>,
  dots: readonly DotLike[],
  extras: readonly ShapeLike[] = [],
): unknown {
  const shape = (x: ShapeLike): unknown => jsx(x.tag, x.attrs)
  return jsx('svg', {
    width: box.width,
    height: box.height,
    viewBox: `0 0 ${box.width} ${box.height}`,
    ...attrs,
    children: [
      ...extras.filter(x => !x.above).map(shape),
      ...dotElements(jsx, dots),
      ...extras.filter(x => x.above).map(shape),
    ],
  })
}

/** The thinnest readable band: the whole tile, scaled to `height`, repeated across the full width. */
export function bandElement(
  jsx: Jsx,
  box: { width: number; height: number },
  height: number,
  dots: readonly DotLike[],
): unknown {
  const id = 'cf-rim-tile'
  const tile = jsx('pattern', {
    id,
    width: box.width,
    height: box.height,
    patternUnits: 'userSpaceOnUse',
    patternTransform: `scale(${height / box.height})`,
    children: dotElements(jsx, dots),
  })
  return jsx('svg', {
    width: '100%',
    height,
    'aria-hidden': true,
    children: [jsx('defs', { children: tile }), jsx('rect', { width: '100%', height: '100%', fill: `url(#${id})` })],
  })
}
