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
export const SOFT_CONTRAST = 3.5
export const CHROMA_C = 0.115, BLANCH_C = 0.012, BLANCH_CONTRAST = 4.5   // error is a bold dark-grey frame, never a faint one
export function palette(hue, ground) {
  const lab = hexToLab(ground), dir = lab.L < 0.5 ? 1 : -1
  const chroma = inkFor(hue, CHROMA_C, ground)
  const soft = inkFor(hue, CHROMA_C, ground, SOFT_CONTRAST)        // resting: quieter than the rest, still ≥ 3:1
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
  // resting: ONE soft, small oval blob (three merged circles), the quietest ink, two paper flecks for the mottle. Not separate dots.
  resting: {
    dots: [circ(8.4, 8.4, 2.9, 'soft'), circ(12, 8, 3.3, 'soft'), circ(15.6, 8.4, 2.9, 'soft')],
    extras: [
      { k: 'ellipse', cx: 10.6, cy: 7.2, rx: 0.8, ry: 0.8, pig: 'paper', alpha: 0.45, above: true },
      { k: 'ellipse', cx: 14.2, cy: 9.2, rx: 0.7, ry: 0.7, pig: 'paper', alpha: 0.45, above: true },
    ],
  },
  // working: a large solid cloud, flat bottom, three lobes (the base rect under them is the flat bottom)
  working: {
    dots: [circ(6.4, 8.9, 4.4), circ(12.6, 6.6, 5.6), circ(18.2, 9.2, 4.0)],
    extras: [{ k: 'rect', x: 2.4, y: 9, w: 19.8, h: 4.9, rx: 2.4, pig: 'chroma', alpha: 1, fill: true }],
  },
  // needs you: a FILLED, saturated chip with three bold diagonal paper-coloured bars (the loudest mark)
  needs_you: {
    dots: [[5, 5], [12, 5], [19, 5], [5, 11], [12, 11], [19, 11]].map(([x, y]) => circ(x, y, 3)),
    extras: [
      { k: 'rect', x: 0.75, y: 0.75, w: 22.5, h: 14.5, rx: 3.5, pig: 'chroma', alpha: 1, fill: true },
      { k: 'path', d: 'M2.5 11.5 L11.5 2.5', pig: 'paper', stroke: 2.4, above: true },
      { k: 'path', d: 'M6.5 13.5 L17.5 2.5', pig: 'paper', stroke: 2.4, above: true },
      { k: 'path', d: 'M12.5 13.5 L21.5 4.5', pig: 'paper', stroke: 2.4, above: true },
    ],
  },
  // error: a HOLLOW pale chip with a big missing corner (top right), never filled; two round ends where the frame breaks
  error: {
    dots: [circ(13.4, 1.5, 1.6, 'blanch'), circ(22.5, 9.9, 1.6, 'blanch')],
    extras: [
      { k: 'rect', x: 2, y: 2, w: 20, h: 12, rx: 1, pig: 'wash', alpha: 0.14, fill: true },
      { k: 'path', d: 'M13.2 1.5 H1.5 V14.5 H22.5 V9.9', pig: 'blanch', stroke: 2.4 },
    ],
  },
  // finished unseen: pale disc, crisp ring, ONE big dark core, four iris flecks (round)
  finished_unseen: {
    dots: [...[45, 135, 225, 315].map(a => circ(12 + 5.5 * Math.cos((a * Math.PI) / 180), 8 + 5.5 * Math.sin((a * Math.PI) / 180), 0.6)), circ(12, 8, 4.5, 'spot', 'eyespot')],
    extras: [
      { k: 'ellipse', cx: 12, cy: 8, rx: 7, ry: 7, pig: 'chroma', alpha: 0.30, fill: true },
      { k: 'ellipse', cx: 12, cy: 8, rx: 7, ry: 7, pig: 'chroma', stroke: 1.6 },
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
  if (state === 'resting') body = pill(`stroke="${c}" stroke-width="1"`)
  if (state === 'working') {
    const lobes = (x, rs) => rs.map((r, i) => `<circle cx="${f(x + i * r * 1.15)}" cy="${h / 2}" r="${r}" fill="${c}"/>`).join('')
    const trains = [[3.2, 4.6, 3.6], [3.8, 5, 4, 2.8], [3, 4.2], [3.6, 5, 4], [3, 4.4, 3.2]]
    const out = []
    let x = 26, k = 0
    while (x < width - 40) { const t = trains[k++ % trains.length]; out.push(lobes(x, t)); x += t.reduce((s2, r) => s2 + r * 1.15, 0) + 40 + (k * 37) % 70 }
    body = `<g clip-path="url(#cap)">${out.join('')}</g>${pill(`stroke="${c}" stroke-width="1"`)}`
  }
  if (state === 'needs_you') {
    body = `<defs><pattern id="s" width="12" height="${h}" patternUnits="userSpaceOnUse" patternTransform="skewX(-45)"><rect width="6" height="${h}" fill="${c}"/></pattern></defs><rect width="${width}" height="${h}" fill="url(#s)" clip-path="url(#cap)"/>${pill(`stroke="${c}" stroke-width="1.5"`)}`
  }
  if (state === 'error') {
    body = `<rect width="${width}" height="${h}" fill="${pal.wash}" fill-opacity=".38" clip-path="url(#cap)"/>${pill(`stroke="${b}" stroke-width="3" stroke-dasharray="${Math.round(width * 0.42)} 14"`)}`
  }
  if (state === 'finished_unseen') {
    body = `${pill(`stroke="${c}" stroke-width="1"`)}<circle cx="14" cy="5" r="3.9" fill="${c}" fill-opacity=".3" stroke="${c}" stroke-width="1.2"/><circle cx="14" cy="5" r="2.4" fill="${pal.spot}"/>`
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${h}" viewBox="0 0 ${width} ${h}"><defs>${clip}</defs>${body}</svg>`
}

