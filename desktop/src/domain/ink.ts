// The v2.1 INK (spec §1): the pigments of the state marks (swatch, strip) and the composer rim, chosen so every mark holds
// ≥ 3.6:1 (WCAG 1.4.11 bar 3.0) on the row it sits in, selected or not. Sidebar rows are not on the chat ground, and the
// plugin only knows the ground, so the ink is checked against the ground AND a worst-case selected tint of it.
// Pure: same (hue, ground) in, same palette out. Reuses oklch.ts for every colour conversion.
import { hexToLab, hexToRgb, oklabToRgb, oklchToHex, rgbToHex } from './oklch.ts'

/** The design target for every mark ink (the bar is 3.0; the headroom covers antialiasing and a tinted selected row). */
export const MIN_CONTRAST = 3.6
/** Resting's soft ink: the quietest ink that still holds ≥ 3:1 on every row tint. */
export const SOFT_CONTRAST = 3.5
/** Error: a bold near-grey frame, never a faint one. */
export const BLANCH_CONTRAST = 4.5
/** The selected-row allowance in OKLab L, toward the ink side of the ground. */
export const SELECT_ALLOWANCE = 0.10
/** The identity pigment's chroma, and the near-achromatic error chroma (mean chroma must stay ≤ 0.03). */
export const CHROMA_C = 0.115
export const BLANCH_C = 0.012

export interface Palette {
  chroma: string    // the identity pigment (organs, bars, chips)
  soft: string      // resting: the quietest identity ink
  blanch: string    // error: near-achromatic
  spot: string      // the pupil: near-black on both grounds
  paper: string     // what a filled mark is drawn "out of": the chat ground itself
  wash: string      // error's pale plate (used only as a fill at low alpha, never as ink)
}

/** WCAG 2.x relative luminance of a '#rrggbb'. */
function luminance(hex: string): number {
  const lin = (c: number): number => { const v = c / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
  const { r, g, b } = hexToRgb(hex)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

/** WCAG contrast ratio of two '#rrggbb' colours (1 … 21). */
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

/** The ground a selected row could show: the ground moved `SELECT_ALLOWANCE` toward the ink side. */
export function worstRowGround(ground: string): string {
  const lab = hexToLab(ground), dir = lab.L < 0.5 ? 1 : -1
  const L = Math.min(0.99, Math.max(0.01, lab.L + dir * SELECT_ALLOWANCE))
  return rgbToHex(oklabToRgb(L, lab.a, lab.b))
}

/** The ink for (hue, chroma) on a ground: the lightness nearest the ground that still reaches `minContrast` on the ground
 *  AND on its worst selected tint. Bisection over OKLab L (24 steps), as planGround does. */
export function inkFor(hue: number, chroma: number, ground: string, minContrast = MIN_CONTRAST): string {
  const lab = hexToLab(ground), dir = lab.L < 0.5 ? 1 : -1
  const grounds = [ground, worstRowGround(ground)]
  const ok = (L: number): boolean => grounds.every(g => contrast(oklchToHex(L, chroma, hue), g) >= minContrast)
  let a = lab.L, b = dir > 0 ? 0.97 : 0.04          // a: the ground side (fails), b: the far side (holds)
  for (let i = 0; i < 24; i++) {
    const m = (a + b) / 2
    if (ok(m)) b = m; else a = m
  }
  return oklchToHex(b, chroma, hue)
}

const cache = new Map<string, Palette>()

/** The mark palette for one identity hue on one ground. Same input, same colours, bit for bit. */
export function palette(hue: number, ground: string): Palette {
  const key = `${hue.toFixed(3)}|${ground}`
  const hit = cache.get(key)
  if (hit !== undefined) return hit
  const dir = hexToLab(ground).L < 0.5 ? 1 : -1
  const out: Palette = {
    chroma: inkFor(hue, CHROMA_C, ground),
    soft: inkFor(hue, CHROMA_C, ground, SOFT_CONTRAST),
    blanch: inkFor(hue, BLANCH_C, ground, BLANCH_CONTRAST),
    spot: oklchToHex(dir > 0 ? 0.07 : 0.17, 0.03, hue),
    paper: ground,
    wash: '',
  }
  out.wash = out.blanch
  if (cache.size > 256) cache.clear()
  cache.set(key, out)
  return out
}
