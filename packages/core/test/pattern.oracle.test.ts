// THE key test (plan §13.4, task P2-CORE): core pixels and text are BYTE-IDENTICAL to the P1 oracle
// design/directions/d-dots/direction.mjs for every P1 matrix scene. The oracle is never edited here.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { paint as oracle } from '../../../design/directions/d-dots/direction.mjs';
import { paint } from '../domain/pattern.ts';

const fx = JSON.parse(readFileSync(new URL('../../../tools/p1/stub-sessions.json', import.meta.url), 'utf8'));
const STATES: string[] = fx.states;
type Sess = { name: string; hue_deg: number | null; alarm_text: string | null };
const sessions: Sess[] = fx.sessions;
const ALARMS: Record<string, string | null> = { 'needs-you': 'INPUT 4m', fault: 'ERROR 2m' };

// ---- the real P1 surface sizes (tools/p1/CONTRACT.md, capture_matrix.py, hosts/*) ----
type Surface = { id: string; scale: 'XL' | 'M' | 'S'; w: number; h: number };
const surfaces: Surface[] = [
  { id: 'desktop swatch 4x2', scale: 'S', w: 4, h: 2 },
  { id: 'desktop chip 22x2', scale: 'M', w: 22, h: 2 },
  { id: 'tui pill half 14x2', scale: 'S', w: 14, h: 2 },
  { id: 'tui pill bg 14x1', scale: 'S', w: 14, h: 1 },
];
for (const cols of [80, 120, 200]) {
  for (const h of [4, 2, 1]) surfaces.push({ id: `tui mantle ${cols} cols h${h}`, scale: 'M', w: cols - 2, h });
  const tw = Math.floor((cols - 2 - 3) / 4);                       // identity grid tiles (hosts/tui-stub-widget gridLayout)
  for (const h of [4, 2]) surfaces.push({ id: `tui grid tile ${tw}x${h}`, scale: 'S', w: tw, h });
}
const XL_SIZES: [number, number][] = [[320, 180], [240, 135], [160, 90], [57, 33], [100, 200]];
for (const [w, h] of XL_SIZES) { assert.ok(w * h <= 57600); }

let scenes = 0;
function compare(label: string, s: { scale: 'XL' | 'M' | 'S'; w: number; h: number }, state: string, sess: Sess, alarm: string | null, step: number, reducedMotion: boolean) {
  const session = { ...sess, alarm_text: alarm };
  const want = oracle({ scale: s.scale, w: s.w, h: s.h, state, session, t: step / 4 + 0.01, opts: { reducedMotion } });   // +0.01: floor(t*4) === step
  const got = paint({ scale: s.scale, w: s.w, h: s.h, look: state, hueDeg: sess.hue_deg, name: sess.name, alarmText: alarm, step, reducedMotion });
  scenes++;
  assert.equal(got.pixels.length, s.w * s.h * 4, `${label}: size`);
  assert.ok(got.pixels instanceof Uint8ClampedArray);
  if (Buffer.compare(Buffer.from(got.pixels.buffer), Buffer.from(want.pixels.buffer)) !== 0) {
    let at = 0; while (got.pixels[at] === want.pixels[at]) at++;
    assert.fail(`${label} ${state} step ${step}: pixels differ first at byte ${at} (px ${at >> 2}): got ${got.pixels[at]} want ${want.pixels[at]}`);
  }
  assert.deepEqual(got.text, want.text, `${label} ${state}: text`);
}

test('every state x every fixture session at every non-XL P1 surface, 8 working frames', () => {
  for (const s of surfaces) {
    for (const sess of sessions) {
      for (const state of STATES) {
        const steps = state === 'working' ? [0, 1, 2, 3, 4, 5, 6, 7] : [0];
        for (const step of steps) compare(s.id, s, state, sess, sess.alarm_text ?? ALARMS[state] ?? null, step, false);
      }
    }
  }
});

test('alarm text paths: INPUT/ERROR text is carried through at every non-XL surface (also when session alarm is null)', () => {
  for (const s of surfaces) for (const sess of sessions.slice(0, 4)) for (const state of ['needs-you', 'fault']) {
    compare(s.id, s, state, sess, ALARMS[state], 0, false);
  }
});

test('degraded (no binding, hue null): unknown look, name "unbound", no identity hue, on all surfaces and XL', () => {
  for (const s of [...surfaces, ...XL_SIZES.map(([w, h]) => ({ id: `XL ${w}x${h}`, scale: 'XL' as const, w, h }))]) {
    for (const state of STATES) compare(`degraded ${s.id}`, s, state, fx.degraded, null, 0, false);
  }
  const out = paint({ scale: 'XL', w: 160, h: 90, look: 'working', hueDeg: null, name: 'whatever', alarmText: 'INPUT 1m', step: 3, reducedMotion: false });
  assert.equal(out.text[0].str, 'unbound');
  assert.equal(out.text[1].str, '?');
});

test('XL: 6 states + degraded, all 20 sessions at 160x90; 3 sessions at all XL sizes; working >= 6 frames', () => {
  for (const sess of sessions) for (const state of STATES) compare('XL 160x90', { scale: 'XL', w: 160, h: 90 }, state, sess, sess.alarm_text ?? ALARMS[state] ?? null, 0, false);
  for (const [w, h] of XL_SIZES) for (const sess of [sessions[0], sessions[1], sessions[3]]) for (const state of STATES) {
    const steps = state === 'working' ? [0, 1, 2, 3, 4, 5, 6] : [0];
    for (const step of steps) compare(`XL ${w}x${h}`, { scale: 'XL', w, h }, state, sess, sess.alarm_text ?? ALARMS[state] ?? null, step, false);
  }
});

test('reduced motion: working is static (all steps byte-equal to step 0) and still matches the oracle', () => {
  for (const s of [surfaces[0], surfaces[1], { id: 'XL', scale: 'XL' as const, w: 160, h: 90 }]) {
    const frames = [0, 1, 2, 3, 4, 5].map(step => paint({ scale: s.scale, w: s.w, h: s.h, look: 'working', hueDeg: 115.75, name: 'ledger', alarmText: null, step, reducedMotion: true }).pixels);
    for (const f of frames) assert.equal(Buffer.compare(Buffer.from(f.buffer), Buffer.from(frames[0].buffer)), 0);
    for (const step of [0, 3, 5]) compare(`${s.id} reduced`, s, 'working', sessions[0], null, step, true);
  }
});

test('negative and very large steps keep oracle parity (the cloud wraps, it never throws)', () => {
  for (const step of [-1, -7, -1000, 123456]) {
    for (const s of [surfaces[0], surfaces[1], surfaces[10], { id: 'XL', scale: 'XL' as const, w: 160, h: 90 }]) {
      const session = sessions[0];
      const want = oracle({ scale: s.scale, w: s.w, h: s.h, state: 'working', session, t: step / 4 + 0.01, opts: {} });
      const got = paint({ scale: s.scale, w: s.w, h: s.h, look: 'working', hueDeg: session.hue_deg, name: session.name, alarmText: null, step, reducedMotion: false });
      scenes++;
      assert.equal(Buffer.compare(Buffer.from(got.pixels.buffer), Buffer.from(want.pixels.buffer)), 0, `step ${step} ${s.id}`);
    }
  }
});

test('behaviour: only working moves, working moves at 4x2 (>= 3 distinct frames of 4), working palette <= 48 colours', () => {
  const sess = sessions[0];
  const frame = (look: string, step: number, s = surfaces[0]) => Buffer.from(paint({ scale: s.scale, w: s.w, h: s.h, look, hueDeg: sess.hue_deg, name: sess.name, alarmText: null, step, reducedMotion: false }).pixels.buffer).toString('hex');
  for (const look of ['idle', 'review', 'needs-you', 'fault', 'unknown']) {
    for (const s of surfaces) assert.equal(frame(look, 0, s), frame(look, 5, s), `${look} ${s.id} must be static`);
  }
  assert.ok(new Set([0, 1, 2, 3].map(step => frame('working', step))).size >= 3);
  for (const s of surfaces.filter(x => x.w >= 20)) {
    const colours = new Set<number>();
    for (let step = 0; step < 16; step++) {
      const px = paint({ scale: s.scale, w: s.w, h: s.h, look: 'working', hueDeg: 207.75, name: 'quill', alarmText: null, step, reducedMotion: false }).pixels;
      for (let i = 0; i < px.length; i += 4) colours.add((px[i] << 16) | (px[i + 1] << 8) | px[i + 2]);
    }
    assert.ok(colours.size <= 48, `${s.id}: ${colours.size} colours`);
  }
});

test('XL stays within the internal paint budget for the sizes the host chooses (w*h <= 57600)', () => {
  for (const [w, h] of XL_SIZES) assert.ok(w * h <= 57600);
});

test('scene count floor (reported in the PR)', t => {
  t.diagnostic(`oracle scenes compared: ${scenes}`);
  assert.ok(scenes >= 3000, `only ${scenes} scenes were compared`);
});
