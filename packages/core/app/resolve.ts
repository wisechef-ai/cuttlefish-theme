// Use-case: everything a surface needs to draw one session RIGHT NOW. Composes the identity hue
// (domain/identity), the scatter (domain/pattern) and the motion budget (domain/motion). No I/O, no
// clock reads: `now` (seconds) is injected.
import { allocate } from '../domain/identity.ts';
import { fpsOf, nextFrameDelayMs, shouldAnimate, frameStep, twinkleAllowed, type Host, type IdleTwinkle } from '../domain/motion.ts';
import { labels, renderScene, type Cell, type Look, type Scale, type TextRun } from '../domain/pattern.ts';
import { TOKENS as T } from '../domain/tokens.ts';

const LOOKS: readonly string[] = ['idle', 'thinking', 'tool', 'review', 'needs-you', 'fault', 'unknown'];
/** A surface with no tool signal reports plain busy: that is `thinking` (CONTEXT-D2; stated in CONTRACT + doctor). */
const LEGACY: Record<string, Look> = { working: 'thinking' };

/** The longest history that still matters: the closing lag is 0.55 s, so 6 s settles every organ. */
export const SETTLE_S = 6;
/** Static states are drawn at this fixed instant, so they are byte-identical whatever `now` is. */
export const T_STATIC = 6;

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
  /** M / S: columns and rows in cells. XL: pixels (the grid is w/12 x h/24). */
  w: number;
  h: number;
  now: number;
  focused: boolean;
  visible: boolean;
  reducedMotion: boolean;
  /** When the session entered `state` (seconds); default: the organs have settled. */
  entered?: number;
  idleTwinkle?: IdleTwinkle;
  host?: Host;
}

export interface RenderModel {
  look: Look;
  name: string;
  hueDeg: number | null;
  animate: boolean;
  /** Frame index (0 when static). */
  step: number;
  nextFrameDelayMs: number | null;
  /** Grid the cells live on. */
  cols: number;
  rows: number;
  /** Visible organs only; foreground colour only, never a background. */
  cells: Cell[];
  text: TextRun[];
}

function resolveHue(s: SessionView | null | undefined): number | null {
  if (!s) return null;
  if (typeof s.hue_deg === 'number' && Number.isFinite(s.hue_deg)) return s.hue_deg;
  if (typeof s.lineage_root === 'string' && s.lineage_root.trim() !== '') return allocate(s.lineage_root, s.peers ?? []).hue_deg;
  return null;
}

/** Position seed: the lineage root keeps the constellation across renames; the name is the fallback. */
function seedOf(s: SessionView | null | undefined): string {
  return s?.lineage_root?.trim() || s?.name || 'unbound';
}

export function renderModel(i: RenderInput): RenderModel {
  const hueDeg = resolveHue(i.session);
  const degraded = hueDeg === null;
  // Never the last known state: no binding, or a state we do not know, is `unknown`.
  const wanted = LEGACY[i.state] ?? i.state;
  const look = (degraded || !LOOKS.includes(wanted) ? 'unknown' : wanted) as Look;
  const gate = { state: look, focused: i.focused, visible: i.visible, reducedMotion: i.reducedMotion, idleTwinkle: i.idleTwinkle, host: i.host };
  const animate = !degraded && shouldAnimate(gate);
  const step = animate ? frameStep(i.now, look) : 0;
  const tEval = animate ? step / fpsOf(look) : T_STATIC;
  const entered = animate ? Math.max(i.entered ?? tEval - SETTLE_S, tEval - SETTLE_S) : tEval - SETTLE_S;
  const [cols, rows] = i.scale === 'XL'
    ? [Math.max(1, Math.ceil(i.w / T.scales.XL.cell_px[0])), Math.max(1, Math.ceil(i.h / T.scales.XL.cell_px[1]))]
    : [Math.max(1, i.w), Math.max(1, i.h)];
  const density = i.scale === 'S' ? T.organs.density_S : T.organs.density;
  const twinkle = look === 'idle' && twinkleAllowed(i.idleTwinkle, i.host, i.reducedMotion) && animate;
  const [cells] = renderScene({
    seed: seedOf(i.session), hue: hueDeg, state: degraded ? 'degraded' : look, cols, rows,
    entered, times: [Math.max(tEval, entered)], density, twinkle,
  });
  const alarmText = look === 'needs-you' || look === 'fault' ? i.session?.alarm_text ?? null : null;
  return {
    look,
    name: degraded ? 'unbound' : (i.session as SessionView).name,
    hueDeg,
    animate,
    step,
    nextFrameDelayMs: animate ? nextFrameDelayMs({ ...gate, tSeconds: i.now }) : null,
    cols, rows, cells,
    text: labels(i.scale, i.w, look, i.session?.name ?? '', alarmText, degraded),
  };
}
