// The budgeted loop's decision logic (C3): whether a frame is worth drawing,
// and how long ago the focused state changed. The clock is carried beside the
// loop because the loop's `now` (a rAF timestamp in the real host, the driver's
// t in the fakes) is the only time source the painter may use — the ctx timers
// and the draw clock are different clocks. A state change is remembered as
// PENDING until the first frame after it: the bloom then starts at that frame,
// so a change that lands during a long park still blooms (C7), while the
// initial sight (no change) parks the loop immediately.
import { motionPlan } from '../domain/index.ts'
import type { CfView } from './view.ts'

/** Draw-clock state: `lastNow` is the last frame's timestamp, `changeAt` the anchored change. */
export interface LoopClock {
  lastNow: number
  changeAt: number | null
  pending: boolean
}

export function initialClock(): LoopClock {
  return { lastNow: 0, changeAt: null, pending: false }
}

/** Arm the bloom: the next frame anchors it. */
export function noteStateChange(c: LoopClock): void {
  c.pending = true
}

/** A frame at `now`: anchor a pending change here, and return the sinceChangeMs this frame paints with. */
export function drawClock(c: LoopClock, now: number): number {
  if (c.pending) {
    c.changeAt = now
    c.pending = false
  }
  c.lastNow = now
  return sinceChangeOf(c, now)
}

/** SinceChangeMs as the idle probe sees it (no frame needed): a pending change counts as now. */
export function idleSince(c: LoopClock): number {
  if (c.pending) return 0
  return sinceChangeOf(c, c.lastNow)
}

function sinceChangeOf(c: LoopClock, now: number): number {
  return c.changeAt === null ? Number.POSITIVE_INFINITY : Math.max(0, now - c.changeAt)
}

/** The domain's motionPlan as a frame decision over the view. */
export function wantsFrame(v: CfView, sinceChangeMs: number): boolean {
  return motionPlan({ motion: v.motion, reducedMotion: v.reducedMotion, pattern: v.pattern.base, sinceChangeMs }).animate
}
