// The painter (C7, ruling R-S1): the field and the composer ring as ONE style
// text the runtime writes into its single owned <style>. The field is the
// domain's organ scatter serialized to an inert SVG data-URI layer on
// [data-chat-surface], composited over the user's own ground BY REFERENCE —
// never a fill, never a background-color. The ring token carries the identity
// hue only: the state speaks through pattern and motion, never through the ring.
import { planGround, renderField, toSvg } from '../domain/index.ts'
import { seedOfStored, type CfView } from './view.ts'

/** The composer ring colour: the identity hue's pigment on this ground — a function of hue, never of state. */
export function ringOf(hueDeg: number, ground: string): string {
  return planGround(hueDeg, ground).chroma
}

/** Rendered texts by input: a working loop revisits the same frames every cloud cycle, and an SVG of ~190 organs
 *  costs ~4 ms to build, so the repeats are served from here. Bounded; cleared whole when full. */
const memo = new Map<string, string>()
const MEMO_CAP = 160

/** The whole owned CSS for the current view: two rules, nothing else (P5/P7 allowlists). */
export function fieldCss(v: CfView): string {
  const key = JSON.stringify([v.focusedStored, v.width, v.height, v.hueDeg, v.ground, v.pattern, v.settings.intensity,
    v.motion, v.reducedMotion, v.tMs, v.sinceChangeMs])
  const hit = memo.get(key)
  if (hit !== undefined) return hit
  const css = buildCss(v)
  if (memo.size >= MEMO_CAP) memo.clear()
  memo.set(key, css)
  return css
}

function buildCss(v: CfView): string {
  const svg = toSvg(
    renderField({
      seed: seedOfStored(v.focusedStored),
      width: v.width,
      height: v.height,
      hueDeg: v.hueDeg,
      ground: v.ground,
      pattern: v.pattern,
      intensity: v.settings.intensity,
      motion: v.motion,
      reducedMotion: v.reducedMotion,
      tMs: v.tMs,
      sinceChangeMs: v.sinceChangeMs,
    }),
    v.width,
    v.height,
  )
  const layer = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
  return (
    `[data-chat-surface]{--ui-chat-surface-background:transparent;` +
    `background:${layer} 0 0/${v.width}px ${v.height}px no-repeat,var(--cf-ground);` +
    `--dt-composer-ring:${ringOf(v.hueDeg, v.ground)}}` +
    ':root{--cf-ground:var(--ui-chat-surface-background)}'
  )
}
