// v2.1 glyph model (dev-only design reference; docs/design/IMPLEMENTATION.md is the spec the coder follows).
// One source for the sheets, the renders and the contrast measurement. Pure: no DOM, no clock.
import { hexToLab, hexToRgb, oklchToHex, rgbToHex, oklabToRgb } from '../../desktop/src/domain/oklch.ts'

export const BOX = { w: 24, h: 16 }                 // the swatch box (O2.9 allows ≤ 28 × 16)
export const STATES = ['resting', 'working', 'needs_you', 'error', 'finished_unseen']
export const HUES = [205, 150, 285, 330, 105]       // sample identities (amber/red stay out, as allocate() does)

// ---- ink ---------------------------------------------------------------------------------------------------------
const lin = c => { const v = c / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
export const luminance = hex => { const { r, g, b } = hexToRgb(hex); return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b) }
export const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
export const MIN_CONTRAST = 3.6        // design target (the bar is 3.0): headroom for antialiasing and a tinted selected row
export const SELECT_ALLOWANCE = 0.10   // the selected row sits up to this much OKLab L toward the ink side of the ground

/** The ground a selected row could show: the plugin only knows the chat ground, so assume the worst tint toward the ink. */
export function worstRowGround(ground) {
  const lab = hexToLab(ground), dir = lab.L < 0.5 ? 1 : -1       // dir = which way ink moves (light ink on dark)
  const L = Math.min(0.99, Math.max(0.01, lab.L + dir * SELECT_ALLOWANCE))
  const { r, g, b } = oklabToRgb(L, lab.a, lab.b)
  return rgbToHex({ r, g, b })
}
/** The ink for (hue, chroma) on a ground: the nearest-to-ground lightness that still reaches MIN_CONTRAST on BOTH the ground
 *  and its worst selected tint. Bisection over OKLab L, like planGround. */
export function inkFor(hue, chroma, ground, minContrast = MIN_CONTRAST) {
  const lab = hexToLab(ground), dir = lab.L < 0.5 ? 1 : -1
  const grounds = [ground, worstRowGround(ground)]
  let lo = 0, hi = 1                                              // lo = too close to the ground side, hi = far side
  const ok = L => grounds.every(g => contrast(oklchToHex(L, chroma, hue), g) >= minContrast)
  // search L between the ground and the far extreme
  let a = lab.L, b = dir > 0 ? 0.97 : 0.04
  for (let i = 0; i < 24; i++) { const m = (a + b) / 2; if (ok(m)) b = m; else a = m }
  return oklchToHex(b, chroma, hue)
}
export const SOFT_CONTRAST = 3.35, SOFT_C = 0.07
export const CHROMA_C = 0.115, BLANCH_C = 0.012, BLANCH_CONTRAST = 3.35   // error is a bold dark-grey frame, never a faint one
export function palette(hue, ground) {
  const lab = hexToLab(ground), dir = lab.L < 0.5 ? 1 : -1
  const chroma = inkFor(hue, CHROMA_C, ground)
  const soft = inkFor(hue, SOFT_C, ground, SOFT_CONTRAST)        // resting: quieter than the rest, still ≥ 3:1
  const blanch = inkFor(hue, BLANCH_C, ground, BLANCH_CONTRAST)
  const spot = oklchToHex(dir > 0 ? 0.07 : 0.17, 0.03, hue)      // the pupil: near-black, ≥ 3:1 on the iris ink on both grounds
  return { chroma, soft, blanch, spot, wash: blanch, paper: ground }
}

// ---- glyph geometry (design units = px at 1×; the strip scales by STRIP_K) --------------------------------------------
export const STRIP_K = 0.875
const circ = (x, y, r, pig = 'chroma', role = 'organ') => ({ x, y, r, pig, role })

const bars = () => {
  const out = []
  for (const cx of [4.2, 12, 19.8]) {
    for (let t = -5.4; t <= 5.41; t += 1.2) {
      const d = circ(cx + t * Math.SQRT1_2, 8 - t * Math.SQRT1_2, 1.7)
      if (d.x - d.r >= 2.3 && d.x + d.r <= 21.7 && d.y - d.r >= 2.3 && d.y + d.r <= 13.7) out.push(d)
    }
  }
  return out
}
const ring = (n, cx, cy, rx, ry, r, pig, phase = 0) =>
  Array.from({ length: n }, (_, i) => { const a = phase + (2 * Math.PI * i) / n; return circ(cx + rx * Math.cos(a), cy + ry * Math.sin(a), r, pig) })

export const GLYPHS = {
  // resting (r4): ONE soft oval with a visible mottle: paper holes cut out of it. Quiet ink, ~16x9.
  resting: {
    dots: [circ(12, 5.4, 5.1, 'soft'), circ(12, 8, 5.9, 'soft'), circ(12, 10.6, 5.1, 'soft')],
    extras: [
      { k: 'ellipse', cx: 10.4, cy: 5.2, rx: 1.0, ry: 1.0, pig: 'paper', alpha: 0.9, above: true },
      { k: 'ellipse', cx: 13.6, cy: 8.4, rx: 1.1, ry: 1.1, pig: 'paper', alpha: 0.9, above: true },
      { k: 'ellipse', cx: 10.8, cy: 11.2, rx: 0.9, ry: 0.9, pig: 'paper', alpha: 0.9, above: true },
    ],
  },
  // working (r4): a solid cloud, three lobes, flat bottom
  working: {
    dots: [circ(6.8, 9.6, 3.3, 'chroma'), circ(12.4, 7.8, 4.4, 'chroma'), circ(17.6, 9.8, 3.1, 'chroma')],
    extras: [{ k: 'rect', x: 3.8, y: 9.8, w: 16.2, h: 3.9, rx: 1.9, pig: 'chroma', alpha: 1, fill: true }],
  },
  // needs you (r4): a filled chip with TWO bold paper bars (survive at 1x)
  needs_you: {
    dots: [[6, 5.5], [12, 5.5], [18, 5.5], [6, 10.5], [12, 10.5], [18, 10.5]].map(([x, y]) => circ(x, y, 2.8)),
    extras: [
      { k: 'rect', x: 2.5, y: 2, w: 19, h: 12, rx: 3, pig: 'chroma', alpha: 1, fill: true },
      { k: 'path', d: 'M4 12 L12 4', pig: 'paper', stroke: 3.4, above: true },
      { k: 'path', d: 'M11.5 12 L19.5 4', pig: 'paper', stroke: 3.4, above: true },
    ],
  },
  // error (r5): the PALEST mark: a washed hue-tinted plate, a thin outline at 3.2:1, a big open corner (8.5 px of top edge + 7 px of right edge)
  error: {
    dots: [circ(13, 2.5, 1.1, 'blanch'), circ(21, 9, 1.1, 'blanch')],
    extras: [
      { k: 'rect', x: 3, y: 2.5, w: 18, h: 11, rx: 1, pig: 'chroma', alpha: 0.24, fill: true },
      { k: 'path', d: 'M13 2.5 H3 V13.5 H21 V9', pig: 'blanch', stroke: 1.6 },
    ],
  },
  // finished unseen (r4): an almond/lens eye: pale lens, crisp outline, solid iris, dark pupil, catch-light; two corner dots
  finished_unseen: {
    dots: [circ(3, 8, 0.7, 'chroma'), circ(21, 8, 0.7, 'chroma'), circ(12, 8, 2.8, 'spot', 'eyespot')],
    extras: [
      { k: 'path', d: 'M2 8 Q12 -2 22 8 Q12 18 2 8 Z', pig: 'chroma', alpha: 0.30, fill: true },
      { k: 'path', d: 'M2 8 Q12 -2 22 8 Q12 18 2 8 Z', pig: 'chroma', stroke: 1.6 },
      { k: 'ellipse', cx: 12, cy: 8, rx: 4.4, ry: 4.4, pig: 'chroma', stroke: 1.5 },
      { k: 'ellipse', cx: 13.3, cy: 6.6, rx: 0.9, ry: 0.9, pig: 'paper', alpha: 1, above: true },
    ],
  },
}

// ---- svg --------------------------------------------------------------------------------------------------------------
const f = v => Number(v.toFixed(3))
/** SVG text of a swatch (k=1) or strip (k=STRIP_K) for one state: dots + extras. */
export function glyphSvg(state, hue, ground, k = 1) {
  const pal = palette(hue, ground), g = GLYPHS[state]
  const w = BOX.w * k, h = BOX.h * k
  const render = e => {
    const paint = e.stroke ? `fill="none" stroke="${pal[e.pig]}" stroke-width="${f(e.stroke * k)}" stroke-linejoin="miter"` : `fill="${pal[e.pig]}" fill-opacity="${e.alpha ?? 1}"`
    if (e.k === 'rect') return `<rect x="${f(e.x * k)}" y="${f(e.y * k)}" width="${f(e.w * k)}" height="${f(e.h * k)}" rx="${f((e.rx ?? 0) * k)}" ${e.stroke ? `fill="none" stroke="${pal[e.pig]}" stroke-width="${f(e.stroke * k)}"` : paint}/>`
    if (e.k === 'path') return `<path d="${e.d.replace(/-?\d*\.?\d+/g, m => f(Number(m) * k))}" ${paint}/>`
    return `<ellipse cx="${f(e.cx * k)}" cy="${f(e.cy * k)}" rx="${f(e.rx * k)}" ry="${f(e.ry * k)}" ${paint}/>`
  }
  const below = g.extras.filter(e => !e.above).map(render).join(''), above = g.extras.filter(e => e.above).map(render).join('')
  const dots = g.dots.map(d => `<circle cx="${f(d.x * k)}" cy="${f(d.y * k)}" r="${f(d.r * k)}" fill="${pal[d.pig]}"/>`).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${f(w)}" height="${f(h)}" viewBox="0 0 ${f(w)} ${f(h)}">${below}${dots}${above}</svg>`
}

export const RIM_H = 10
/** The composer rim: ONE system. Every state is the same 10 px pill (same placement, same round end caps, 1 px inset); the state only changes what
 *  fills it and how its outline is drawn, echoing its mark. */
export function rimSvg(state, hue, ground, width) {
  const pal = palette(hue, ground), h = RIM_H, c = pal.chroma, b = pal.blanch
  const pw = width - 1.5, ph = h - 1.5
  const pill = (extra = '') => `<rect x=".75" y=".75" width="${pw}" height="${ph}" rx="${ph / 2}" fill="none" ${extra}/>`
  const clip = `<clipPath id="cap"><rect x=".75" y=".75" width="${pw}" height="${ph}" rx="${ph / 2}"/></clipPath>`
  let body = ''
  // resting (r5): ONE quiet hairline in the soft ink; no pill, no double line
  if (state === 'resting') body = `<rect x="0" y="${h - 1}" width="${width}" height="1" fill="${pal.soft}"/>`
  if (state === 'working') {
    // r5: a clean pill outline, a faint tint inside, and five LARGER soft clouds spaced evenly (every 20 % of the width)
    const cloud = `<g opacity=".55" fill="${c}"><circle cx="40" cy="5.6" r="3.2"/><circle cx="46.4" cy="4.3" r="4.2"/><circle cx="52.8" cy="5.6" r="3.4"/><rect x="37" y="5.4" width="19.6" height="3.1" rx="1.5"/></g>`
    body = `<defs><pattern id="cl" x="0" y="0" width=".2" height="1" patternUnits="objectBoundingBox" patternContentUnits="userSpaceOnUse">${cloud}</pattern></defs><rect width="${width}" height="${h}" fill="${c}" fill-opacity=".08" clip-path="url(#cap)"/><rect width="${width}" height="${h}" fill="url(#cl)" clip-path="url(#cap)"/>${pill(`stroke="${c}" stroke-width="1.2"`)}`
  }
  if (state === 'needs_you') {
    const chip = x => `<g clip-path="url(#cap)"><rect x="${x}" y="0" width="96" height="${h}" fill="url(#s)"/></g>`
    body = `<defs><pattern id="s" width="12" height="${h}" patternUnits="userSpaceOnUse" patternTransform="skewX(-45)"><rect width="6" height="${h}" fill="${c}"/></pattern></defs>${pill(`stroke="${c}" stroke-width="1.5"`)}${chip(0)}${chip(width - 96)}<rect x="96" y=".75" width="1.5" height="${ph}" fill="${c}"/><rect x="${width - 97.5}" y=".75" width="1.5" height="${ph}" fill="${c}"/>`
  }
  if (state === 'error') {
    // r5: the TOP EDGE of a box, pale and thin, with its two short returns and ONE clear gap near the right end: a broken, blanched border. No track, no thumb.
    const t = 1.2, gl = 0.62 * width, gr = 0.62 * width + 56
    body = `<rect x=".75" y=".75" width="${f(gl - .75)}" height="${t}" fill="${b}"/><rect x="${f(gr)}" y=".75" width="${f(width - gr - .75)}" height="${t}" fill="${b}"/><rect x=".75" y=".75" width="${t}" height="${ph}" fill="${b}"/><rect x="${f(width - .75 - t)}" y=".75" width="${t}" height="${ph}" fill="${b}"/>`
  }
  if (state === 'finished_unseen') {
    body = `${pill(`stroke="${c}" stroke-width="1"`)}<path d="M8 5 Q20 -2 32 5 Q20 12 8 5 Z" fill="${c}" fill-opacity=".3" stroke="${c}" stroke-width="1.2"/><circle cx="20" cy="5" r="2.6" fill="${c}"/><circle cx="20" cy="5" r="1.6" fill="${pal.spot}"/>`
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${h}" viewBox="0 0 ${width} ${h}"><defs>${clip}</defs>${body}</svg>`
}

