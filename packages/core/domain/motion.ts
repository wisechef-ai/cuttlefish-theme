// D1 (plan §8): only `working` moves, only while the surface is focused and visible, never under
// reduced motion, at most 4 frames per second (one dot per 0.25 s), and with NO timer at rest.
// The motif is a drifting band of contracted dots, the "passing cloud" display of cuttlefish skin
// (the plan cites Woo 2023 for it; the cadence here comes from D1, not from the paper).
// Pure: time is an argument, never read.

export interface AnimationGate { state: string; focused: boolean; visible: boolean; reducedMotion: boolean }

export const FPS = 4;
export const FRAME_MS = 1000 / FPS;   // 250

export function shouldAnimate(g: AnimationGate): boolean {
  return g.state === 'working' && g.focused && g.visible && !g.reducedMotion;
}

/** Frame index of the passing cloud at `tSeconds`: floor(t * 4). */
export function frameStep(tSeconds: number): number {
  return Math.floor(tSeconds * FPS);
}

/**
 * Milliseconds until the next frame boundary, or null when nothing should animate (the caller then
 * arms no timer at all). Always lands on the next step: frameStep(t + delay/1000) === frameStep(t) + 1.
 */
export function nextFrameDelayMs(g: AnimationGate & { tSeconds: number }): number | null {
  if (!shouldAnimate(g)) return null;
  const step = frameStep(g.tSeconds);
  let d = Math.max(1, Math.ceil(((step + 1) / FPS - g.tSeconds) * 1000));
  while (frameStep(g.tSeconds + d / 1000) === step) d++;   // float guard: never wake one frame early
  return d;
}
