// The ground the field paints on: the user's own chat-surface background, READ
// (never overridden). parseGround turns what getComputedStyle resolves a colour
// to into the '#rrggbb' the domain speaks. Engines resolve a colour to
// `rgb(r, g, b)` / `rgba(…)`, the space form `rgb(r g b / a)`, or — for
// color-mix(in srgb) — `color(srgb r g b / a)` (components 0..1). Anything else
// (oklch(), an unresolved token stream, empty), or any colour that is not fully
// opaque, is null and the caller keeps its fallback. Pure: a string in, a string out.
import { rgbToHex } from '../domain/index.ts'

const NUM = '(\\d*\\.?\\d+)'
const ALPHA = `(?:\\s*[,/]\\s*(\\d*\\.?\\d+%?))?`
/** `rgb(1, 2, 3)` / `rgba(1, 2, 3, a)` / `rgb(1 2 3 / a)` (0..255). */
const FUNC_RGB = new RegExp(`^rgba?\\(\\s*${NUM}\\s*[,\\s]\\s*${NUM}\\s*[,\\s]\\s*${NUM}${ALPHA}\\s*\\)$`)
/** `color(srgb 0.1 0.2 0.3 / a)` (0..1). */
const COLOR_SRGB = new RegExp(`^color\\(\\s*srgb\\s+${NUM}\\s+${NUM}\\s+${NUM}${ALPHA}\\s*\\)$`)
const HEX_RGB = /^#[0-9a-f]{6}$/i

/** The alpha group as a number: absent means opaque. */
function opaque(alpha: string | undefined): boolean {
  if (alpha === undefined) return true
  return alpha.endsWith('%') ? parseFloat(alpha) >= 100 : Number(alpha) >= 1
}

/** A computed colour to a '#rrggbb' ground, or null when it is not one we can paint on. */
export function parseGround(computed: string): string | null {
  if (typeof computed !== 'string') return null
  const s = computed.trim()
  if (HEX_RGB.test(s)) return s.toLowerCase()
  const f = FUNC_RGB.exec(s)
  if (f) return opaque(f[4]) ? rgbToHex({ r: Number(f[1]), g: Number(f[2]), b: Number(f[3]) }) : null
  const c = COLOR_SRGB.exec(s)
  if (c) return opaque(c[4]) ? rgbToHex({ r: Number(c[1]) * 255, g: Number(c[2]) * 255, b: Number(c[3]) * 255 }) : null
  return null
}
