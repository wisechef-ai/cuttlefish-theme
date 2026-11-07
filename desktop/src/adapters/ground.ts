// The ground the field paints on: the user's own chat-surface background, READ
// (never overridden). parseGround turns whatever getComputedStyle reports into
// the '#rrggbb' the domain speaks; anything else (oklch(), named colours, empty)
// is null and the caller keeps its last known ground. Pure: a string in, a
// string out.
import { rgbToHex } from '../domain/index.ts'

/** `rgb(1, 2, 3)` / `rgba(1, 2, 3, …)` — what a resolved CSS colour usually reports as. */
const FUNC_RGB = /^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,[^)]*)?\)$/
const HEX_RGB = /^#[0-9a-f]{6}$/i

/** A computed colour to a '#rrggbb' ground, or null when it is not one we can paint on. */
export function parseGround(computed: string): string | null {
  if (typeof computed !== 'string') return null
  const s = computed.trim()
  if (HEX_RGB.test(s)) return s.toLowerCase()
  const m = FUNC_RGB.exec(s)
  if (!m) return null
  return rgbToHex({ r: Number(m[1]), g: Number(m[2]), b: Number(m[3]) })
}
