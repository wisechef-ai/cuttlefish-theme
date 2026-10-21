// D2 kinetics + animation budget (CONTEXT-D2 section 0). Pure: time is an argument, never read.
//
// Kinetics: a first-order lag. The drive (pattern.ts) gives a TARGET expansion; the displayed
// expansion chases it with tau 0.10 s when opening (the muscle) and 0.55 s when closing (the
// elastic sac). That one asymmetry is most of why the skin reads as alive.
//
// Budget: only thinking, tool and needs-you animate (<= 10 / 10 / 8 fps). Idle twinkle runs at
// <= 4 fps and ONLY when the idle-twinkle setting allows. Everything else is static and costs
// 0 frames. Reduced motion means fully static.
import { TOKENS as T } from './tokens.ts';

export const TAU_OPEN = T.kinetics.tau_open_s;
export const TAU_CLOSE = T.kinetics.tau_close_s;

/** One lag step: the new displayed expansion after `dt` seconds chasing `target`. */
export function stepKinetics(e: number, target: number, dt: number): number {
  const tau = target > e ? TAU_OPEN : TAU_CLOSE;
  return e + (target - e) * (1 - Math.exp(-dt / tau));
}

export type MotionState = 'idle' | 'thinking' | 'tool' | 'review' | 'needs-you' | 'fault' | 'unknown';

/** Simulation / draw rate per state. Static states are simulated at this rate only so they settle. */
export const FPS: Readonly<Record<MotionState, number>> = Object.freeze({
  idle: T.states.idle.fps, thinking: T.states.thinking.fps, tool: T.states.tool.fps, review: T.states.review.fps,
  'needs-you': T.states['needs-you'].fps, fault: T.states.fault.fps, unknown: T.states.unknown.fps,
});

const ANIMATED: ReadonlySet<string> = new Set(['thinking', 'tool', 'needs-you']);

export type IdleTwinkle = 'auto' | 'on' | 'off';
/** Hosts whose terminal makes a 4 fps twinkle a cost (TMUX, Ghostty, cmux). */
export interface Host { tmux?: boolean; ghostty?: boolean; cmux?: boolean }

export interface AnimationGate {
  state: string;
  focused: boolean;
  visible: boolean;
  reducedMotion: boolean;
  /** Idle-twinkle setting; default 'auto'. */
  idleTwinkle?: IdleTwinkle;
  host?: Host;
}

/** May the idle organs twinkle? `auto` = off under TMUX / Ghostty / cmux or when reduced motion is requested. */
export function twinkleAllowed(setting: IdleTwinkle | undefined, host: Host | undefined, reducedMotion: boolean): boolean {
  if (reducedMotion) return false;
  const s = setting ?? 'auto';
  if (s === 'off') return false;
  if (s === 'on') return true;
  return !(host?.tmux || host?.ghostty || host?.cmux);
}

export function shouldAnimate(g: AnimationGate): boolean {
  if (!g.focused || !g.visible || g.reducedMotion) return false;
  if (ANIMATED.has(g.state)) return true;
  return g.state === 'idle' && twinkleAllowed(g.idleTwinkle, g.host, g.reducedMotion);
}

export function fpsOf(state: string): number {
  return (FPS as Record<string, number>)[state] ?? 0;
}

/** Frame index at `tSeconds` for `state`: floor(t * fps). */
export function frameStep(tSeconds: number, state: string): number {
  return Math.floor(tSeconds * fpsOf(state));
}

/**
 * Milliseconds until the next frame boundary, or null when nothing should animate (the caller then
 * arms no timer at all). Always lands on the next step: frameStep(t + delay/1000) === frameStep(t) + 1.
 */
export function nextFrameDelayMs(g: AnimationGate & { tSeconds: number }): number | null {
  if (!shouldAnimate(g)) return null;
  const fps = fpsOf(g.state);
  const step = frameStep(g.tSeconds, g.state);
  let d = Math.max(1, Math.ceil(((step + 1) / fps - g.tSeconds) * 1000));
  while (frameStep(g.tSeconds + d / 1000, g.state) === step) d++;   // float guard: never wake one frame early
  return d;
}
