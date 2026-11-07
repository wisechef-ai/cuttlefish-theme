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

/** The root <svg> carrying the surface attributes and the dots. */
export function svgElement(
  jsx: Jsx,
  box: { width: number; height: number },
  attrs: Record<string, unknown>,
  dots: readonly DotLike[],
): unknown {
  return jsx('svg', {
    width: box.width,
    height: box.height,
    viewBox: `0 0 ${box.width} ${box.height}`,
    ...attrs,
    children: dotElements(jsx, dots),
  })
}
