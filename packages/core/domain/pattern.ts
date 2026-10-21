// D2 "scatter": sparse chromatophore organs at FIXED positions that change appearance with the agent's
// state (CONTEXT-D2 section 0). A pure port of the Python oracle python/domain/dots.py.
// ORACLE RULE: test/dots.parity.test.ts requires EXACT glyph + rgb per organ against
// fixtures/dots-vectors.json (written by tools/gen-dots-vectors.py from the oracle). Do not "improve"
// this file without changing the oracle. Pure: no clock (time is an argument), no randomness (every
// number is a blake2b hash of its arguments). No background colour exists anywhere in this file.
import { blake2b, utf8 } from './blake2b.ts';
import { stepKinetics, FPS, type MotionState } from './motion.ts';
import { oklch, type RGB } from './oklch.ts';
import { TOKENS as T } from './tokens.ts';

export type Scale = 'XL' | 'M' | 'S';
export type Look = MotionState;
export type Pigment = 'id' | 'amber' | 'red' | 'glint' | 'grey';
export interface TextRun { x: number; y: number; str: string; fg: string; bg: string }
/** One visible organ: grid cell, glyph from the ladder, foreground rgb (never a background), expansion 0..1. */
export interface Cell { x: number; y: number; glyph: string; rgb: RGB; pigment: Pigment; e: number }

const TIER_L = T.identity.tier_lightness;
const TIER_HUE = T.identity.tier_hue_offset_deg;
const TIER_TONIC = T.identity.tier_tonic_expansion;
const TIER_CUT = T.identity.tier_weights_cumulative;
const TIER_C = T.identity.chroma;
const GLYPHS = T.organs.glyph_ladder;
const GLYPH_E = T.organs.glyph_thresholds;
const E_STEPS = T.organs.expansion_steps;
const L_CAP = T.organs.lightness_cap;
const L_GAIN = T.organs.lightness_gain, C_GAIN = T.organs.chroma_gain;
const AMBER = T.alarm.amber, RED = T.alarm.red, GLINT = T.alarm.glint, GREY = T.grey;
export const DENSITY = T.organs.density;
const BURST_EVERY = 0.25;

/** scale -> [cols, rows, density]; S raises the density: a 4x2 swatch at 10 % would usually hold no organ. */
export const SCALES: Readonly<Record<Scale, readonly [number, number, number]>> = Object.freeze({
  XL: [T.scales.XL.cols, T.scales.XL.rows, DENSITY], M: [T.scales.M.cols, T.scales.M.rows, DENSITY], S: [T.scales.S.cols, T.scales.S.rows, T.organs.density_S],
});

// ---------------------------------------------------------------- determinism

const memo = new Map<string, number>();
/** Deterministic uniform [0,1) from any parts: first 8 bytes (big endian) of blake2b-64 / 2^64. */
function h(...parts: (string | number)[]): number {
  const key = parts.join('|');
  let v = memo.get(key);
  if (v === undefined) {
    const d = blake2b(utf8(key), 8);
    const hi = ((d[0] << 24) | (d[1] << 16) | (d[2] << 8) | d[3]) >>> 0;
    const lo = ((d[4] << 24) | (d[5] << 16) | (d[6] << 8) | d[7]) >>> 0;
    v = (hi * 4294967296 + lo) / 18446744073709551616;
    if (memo.size > 1 << 16) memo.clear();
    memo.set(key, v);
  }
  return v;
}

// ---------------------------------------------------------------- the organs

export interface Organ { x: number; y: number; tier: number; phase: number; rate: number; alarm: number; e: number }

/** One candidate per cell kept with p=density, thinned so no two organs touch (8-neighbourhood). */
export function constellation(seed: string, cols: number, rows: number, density: number = DENSITY): Organ[] {
  const out: Organ[] = [];
  const taken = new Set<string>();
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      if (h('pos', seed, x, y) >= density) continue;
      let touch = false;
      for (let dx = -1; dx <= 1 && !touch; dx++) for (let dy = -1; dy <= 1; dy++) if (taken.has(`${x + dx},${y + dy}`)) { touch = true; break; }
      if (touch) continue;
      taken.add(`${x},${y}`);
      const r = h('tier', seed, x, y);
      const tier = r < TIER_CUT[0] ? 0 : r < TIER_CUT[1] ? 1 : 2;
      out.push({ x, y, tier, phase: h('ph', seed, x, y), rate: 0.7 + 0.6 * h('rt', seed, x, y), alarm: h('alarm', seed, x, y), e: 0 });
    }
  }
  return out;
}

// ---------------------------------------------------------------- neural drive per state

function bump(dt: number, rise: number, fall: number): number {
  if (dt < 0) return 0;
  if (dt < rise) return dt / rise;
  return Math.exp(-(dt - rise) / fall);
}

/** Smooth 2-D value noise in [0,1]: spatially coherent, so neighbours act together. */
export function vnoise(x: number, y: number, seed = 'n'): number {
  const xi = Math.floor(x), yi = Math.floor(y);
  const fx = x - xi, fy = y - yi;
  const sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
  const a = h(seed, xi, yi), b = h(seed, xi + 1, yi), c = h(seed, xi, yi + 1), d = h(seed, xi + 1, yi + 1);
  return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy;
}

type Burst = readonly [number, number, number, number];
const burstMemo = new Map<string, Burst[]>();
function bursts(k0: number, cols: number, rows: number): Burst[] {
  const key = `${k0}|${cols}|${rows}`;
  let v = burstMemo.get(key);
  if (!v) {
    const perTick = Math.max(1, Math.floor((cols * rows) / 650 + 0.5));   // same sparkle rate per area at any size
    v = [];
    for (let k = k0 - 4; k <= k0; k++) for (let j = 0; j < perTick; j++) v.push([h('bx', k, j) * cols, h('by', k, j) * rows, 5 + 7 * h('br', k, j), k * BURST_EVERY]);
    if (burstMemo.size > 8) burstMemo.clear();
    burstMemo.set(key, v);
  }
  return v;
}

const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

/** Target expansion 0..1 and pigment class for one organ. t = wall time, ts = time since entering the state. */
export function drive(o: Organ, state: string, t: number, ts: number, cols: number, rows: number, twinkle = true): [number, Pigment] {
  const tonic = TIER_TONIC[o.tier];
  switch (state) {
    case 'idle': {
      // Rare individual twitches (18 % of organ windows) -> ~1 organ / 1.5 s on a strip.
      const period = 9.0 / o.rate;
      const k = Math.floor((t + o.phase * period) / period);
      if (twinkle && h('tw', o.x, o.y, k) < 0.18) {
        const start = k * period - o.phase * period + h('tws', o.x, o.y, k) * period * 0.5;
        return [Math.min(1, tonic + 0.6 * bump(t - start, 0.12, 0.9)), 'id'];
      }
      return [tonic, 'id'];
    }
    case 'thinking': {
      // Coherent value-noise clouds advected left->right (~6 s per crossing), soft-thresholded.
      const u = o.x / Math.max(6.0, cols / 9.0) - t * 1.5;
      const v = o.y / Math.max(2.0, rows / 3.5);
      const n = 0.65 * vnoise(u, v, 'c1') + 0.35 * vnoise(2.1 * u + 7, 2.1 * v, 'c2');
      let cloud = clamp01((n - 0.48) / 0.22);
      cloud = cloud * cloud * (3 - 2 * cloud);
      return [0.24 + 0.72 * cloud, 'id'];
    }
    case 'tool': {
      // Sparkle bursts every 0.25 s; a ripple of 0.035 s per cell; the peak shows the iridophore glint.
      let level = 0.25;
      for (const [cx, cy, radius, start] of bursts(Math.floor(t / BURST_EVERY), cols, rows)) {
        const dx = (o.x - cx) / 2.0;   // cells are ~2:1 tall
        if (Math.abs(dx) > radius) continue;
        const dy = o.y - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > radius) continue;
        const onset = start + dist * 0.035;
        level = Math.max(level, 0.95 * Math.sqrt(1 - dist / radius) * bump(t - onset, 0.08, 0.45));
      }
      return [Math.min(1, level), level > 0.70 ? 'glint' : 'id'];
    }
    case 'review': {
      // A soft static mottle: vnoise blotches, organs hold e in 0.2..0.7. No motion.
      const n = vnoise(o.x / Math.max(4.0, cols / 16.0), o.y / Math.max(2.0, rows / 6.0), 'rv');
      return [0.2 + 0.5 * Math.min(1, Math.max(0, (n - 0.2) / 0.6)), 'id'];
    }
    case 'needs-you': {
      // Identity organs settle at 0.26; seeded organs (alarm<0.06) go amber and pulse in sync at 0.5 Hz.
      if (o.alarm < 0.06) {
        const pulse = 0.5 * (1 + Math.sin(2 * Math.PI * 0.5 * t));
        return [0.55 + 0.45 * pulse, 'amber'];
      }
      return [0.26, 'id'];
    }
    case 'fault':
      // Blanch (everything closes via the kinetics); after 0.6 s the alarm<0.10 organs flush red and hold.
      return o.alarm < 0.10 && ts > 0.6 ? [0.8, 'red'] : [0, 'id'];
    case 'unknown':
    case 'degraded':
      return [0.5, 'grey'];   // no identity claim: sparse grey organs, static
    default:
      throw new RangeError(`unknown state ${state}`);
  }
}

// ---------------------------------------------------------------- appearance

const paintMemo = new Map<string, [string, RGB | null]>();
/** Quantised to 10 steps + memoised: an organ costs a draw only when it visibly changes. */
export function appearance(tier: number, e: number, pigment: Pigment, hue: number | null): [string, RGB | null] {
  const q = Math.floor(e * E_STEPS + 0.5);
  const key = `${tier}|${q}|${pigment}|${hue}`;
  let v = paintMemo.get(key);
  if (!v) {
    v = paint(tier, q / E_STEPS, pigment, hue);
    if (paintMemo.size > 4096) paintMemo.clear();
    paintMemo.set(key, v);
  }
  return v;
}

function paint(tier: number, e: number, pigment: Pigment, hue: number | null): [string, RGB | null] {
  if (e < GLYPH_E[0]) return [' ', null];
  const g = GLYPHS[e < GLYPH_E[1] ? 1 : e < GLYPH_E[2] ? 2 : 3];
  if (pigment === 'grey' || hue === null) return [g, oklch(GREY.lightness, GREY.chroma, 0)];
  if (pigment === 'amber') return [g, oklch(AMBER.lightness * (0.80 + 0.20 * e), AMBER.chroma, AMBER.hue_deg)];
  if (pigment === 'red') return [g, oklch(RED.lightness * (0.82 + 0.18 * e), RED.chroma, RED.hue_deg)];
  if (pigment === 'glint') return [g, oklch(GLINT.lightness, GLINT.chroma, hue + GLINT.hue_offset_deg)];
  const L = TIER_L[tier] * (L_GAIN[0] + L_GAIN[1] * e);
  return [g, oklch(Math.min(L_CAP, L), TIER_C * (C_GAIN[0] + C_GAIN[1] * e), hue + TIER_HUE[tier])];
}

// ---------------------------------------------------------------- scenes

export interface SceneArgs {
  seed: string;
  /** Identity hue in degrees, or null when there is no binding (degraded). */
  hue: number | null;
  /** One of the 7 states, or 'degraded' (== unknown with no hue). */
  state: string;
  cols: number;
  rows: number;
  /** Wall time at which the session entered `state`, every organ closed. */
  entered: number;
  /** Ascending wall times, each >= entered. */
  times: readonly number[];
  density?: number;
  /** False = the idle-twinkle setting is off: idle holds its tonic tone. */
  twinkle?: boolean;
}

/** Cells at each time: fixed-step simulation at FPS[state] from `entered` (the oracle's `render`). Visible organs only. */
export function renderScene(a: SceneArgs): Cell[][] {
  const hue = a.state === 'degraded' ? null : a.hue;
  const sim = a.state === 'degraded' ? 'unknown' : a.state;
  const fps = (FPS as Record<string, number>)[sim];
  if (fps === undefined) throw new RangeError(`unknown state ${a.state}`);
  const twinkle = a.twinkle ?? true;
  const organs = constellation(a.seed, a.cols, a.rows, a.density ?? DENSITY);
  const out: Cell[][] = [];
  let i = 0;
  for (const t of a.times) {
    const n = Math.floor((t - a.entered) * fps);
    for (; i <= n; i++) {
      for (const o of organs) {
        const [target] = drive(o, sim, a.entered + i / fps, i / fps, a.cols, a.rows, twinkle);
        o.e = stepKinetics(o.e, target, 1 / fps);
      }
    }
    const cells: Cell[] = [];
    for (const o of organs) {
      const [, pig] = drive(o, sim, a.entered + n / fps, n / fps, a.cols, a.rows, twinkle);
      const [glyph, rgb] = appearance(o.tier, o.e, pig, hue);
      if (rgb) cells.push({ x: o.x, y: o.y, glyph, rgb, pigment: pig, e: o.e });
    }
    out.push(cells);
  }
  return out;
}

// ---------------------------------------------------------------- text (plates are the only painted background)

const INK = T.text_pairs[0].fg, PLATE = T.text_pairs[0].bg;
const ALARM_FG: Record<string, string> = { 'needs-you': T.text_pairs[1].fg, fault: T.text_pairs[2].fg };
const ALARM_BG: Record<string, string> = { 'needs-you': T.text_pairs[1].bg, fault: T.text_pairs[2].bg };

/**
 * Text where the surface carries text: XL name at (16,16) px with the alarm below it; M name left and
 * alarm right in cells (the alarm wins when both do not fit); the S swatch (w <= 8) has none, its row
 * carries the name. Degraded shows `unbound`, unknown shows `?`.
 */
export function labels(scale: Scale, w: number, look: string, name: string, alarmText: string | null | undefined, degraded: boolean): TextRun[] {
  const text: TextRun[] = [];
  const shown = degraded ? 'unbound' : name;
  const alarm = look === 'unknown' ? '?' : alarmText || null;
  const fg = ALARM_FG[look] ?? INK, bg = ALARM_BG[look] ?? PLATE;
  if (scale === 'XL') {
    text.push({ x: 16, y: 16, str: shown, fg: INK, bg: PLATE });
    if (alarm) text.push({ x: 16, y: 48, str: alarm, fg, bg });
  } else if (w > 8) {
    const label = ` ${shown} `.slice(0, w);
    const s = alarm ? ` ${alarm} ` : '';
    if (!alarm) text.push({ x: 0, y: 0, str: label, fg: INK, bg: PLATE });
    else if (label.length + s.length <= w) {
      text.push({ x: 0, y: 0, str: label, fg: INK, bg: PLATE });
      text.push({ x: w - s.length, y: 0, str: s, fg, bg });
    } else {
      text.push({ x: 0, y: 0, str: s.slice(0, w), fg, bg });
    }
  }
  return text;
}
