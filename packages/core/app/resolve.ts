// Use-case: everything a surface needs to draw one session RIGHT NOW. Composes the identity hue
// (domain/identity), the pattern (domain/pattern) and the motion gate (domain/motion). No I/O, no
// clock reads: `now` (seconds) is injected.
import { allocate } from '../domain/identity.ts';
import { frameStep, nextFrameDelayMs, shouldAnimate } from '../domain/motion.ts';
import { paint, type Look, type Scale, type TextRun } from '../domain/pattern.ts';

const LOOKS: readonly string[] = ['idle', 'working', 'review', 'needs-you', 'fault', 'unknown'];

export interface SessionView {
  name: string;
  /** Hue from the identity registry (the persisted allocation). */
  hue_deg?: number | null;
  /** Fallback when the registry is unreachable: same allocator, peers it can see (default none). */
  lineage_root?: string | null;
  peers?: readonly number[];
  alarm_text?: string | null;
}

export interface RenderInput {
  session: SessionView | null | undefined;
  state: Look | string;
  scale: Scale;
  w: number;
  h: number;
  now: number;
  focused: boolean;
  visible: boolean;
  reducedMotion: boolean;
}

export interface RenderModel {
  look: Look;
  name: string;
  hueDeg: number | null;
  animate: boolean;
  step: number;
  nextFrameDelayMs: number | null;
  pixels: Uint8ClampedArray;
  text: TextRun[];
}

function resolveHue(s: SessionView | null | undefined): number | null {
  if (!s) return null;
  if (typeof s.hue_deg === 'number' && Number.isFinite(s.hue_deg)) return s.hue_deg;
  if (typeof s.lineage_root === 'string' && s.lineage_root.trim() !== '') return allocate(s.lineage_root, s.peers ?? []).hue_deg;
  return null;
}

export function renderModel(i: RenderInput): RenderModel {
  const hueDeg = resolveHue(i.session);
  const degraded = hueDeg === null;
  // Never the last known state: no binding, or a state we do not know, is `unknown`.
  const look = (degraded || !LOOKS.includes(i.state) ? 'unknown' : i.state) as Look;
  const animate = !degraded && shouldAnimate({ state: look, focused: i.focused, visible: i.visible, reducedMotion: i.reducedMotion });
  const step = animate ? frameStep(i.now) : 0;
  const alarmText = look === 'needs-you' || look === 'fault' ? i.session?.alarm_text ?? null : null;
  const painted = paint({
    scale: i.scale, w: i.w, h: i.h, look, hueDeg, name: i.session?.name ?? '', alarmText, step,
    reducedMotion: i.reducedMotion || !animate,
  });
  return {
    look,
    name: degraded ? 'unbound' : (i.session as SessionView).name,
    hueDeg,
    animate,
    step,
    nextFrameDelayMs: animate ? nextFrameDelayMs({ state: look, focused: i.focused, visible: i.visible, reducedMotion: i.reducedMotion, tSeconds: i.now }) : null,
    pixels: painted.pixels,
    text: painted.text,
  };
}
