// C3 motion, as a pure decision. `still` (the default) animates only the working clouds and the
// one bloom after a state change; `alive` adds the resting twinkle; `off` and the OS
// prefers-reduced-motion switch animate nothing. The bloom kinetics are the organ oracle's
// (origin/feat/sparse-dots-preview tools/dots_preview.py): chromatophores OPEN fast (muscle,
// tau ~0.10 s) and CLOSE slowly (elastic sac, tau ~0.55 s) — so a state change snaps brighter,
// then settles. Pure: time arrives as an argument.
import type { Motion, PatternKind } from './types.ts'

/** The bloom tail: a state change blooms for "a few seconds" (the contract pins 800..4000 ms). */
export const BLOOM_MS = 2400

/** Bloom amplitude above the settled ink: the contract asks peak >= 1.5x settled. */
const BLOOM_AMP = 1.0
const TAU_OPEN = 100        // ms; opening is muscular and fast
const TAU_CLOSE = 550       // ms; closing is elastic and slow
const T_PEAK = 250          // ms; hand-over from the opening ramp to the closing decay

/** How much a state that changed `sinceChangeMs` ago is still blooming. 1 = settled. */
export function bloomFactor(sinceChangeMs: number, motion: Motion, reducedMotion: boolean): number {
  if (reducedMotion || motion === 'off' || sinceChangeMs >= BLOOM_MS) return 1
  const s = Math.max(0, sinceChangeMs)
  const env = s < T_PEAK ? 1 - Math.exp(-s / TAU_OPEN) : Math.exp(-(s - T_PEAK) / TAU_CLOSE)
  return 1 + BLOOM_AMP * env
}

/** Whether the budgeted loop should run, and at what rate (the adapter lane wires the loop). */
export function motionPlan(i: { motion: Motion; reducedMotion: boolean; pattern: PatternKind; sinceChangeMs: number }):
  { animate: boolean; fps: number } {
  if (i.reducedMotion || i.motion === 'off') return { animate: false, fps: 0 }
  if (i.pattern === 'clouds') return { animate: true, fps: 8 }
  if (i.motion === 'alive') return { animate: true, fps: 3 }
  if (i.sinceChangeMs < BLOOM_MS) return { animate: true, fps: 5 }
  return { animate: false, fps: 0 }
}
