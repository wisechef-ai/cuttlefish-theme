import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderModel } from '../app/resolve.ts';
import { paint } from '../domain/pattern.ts';
import { allocate, hueOfSlot } from '../domain/identity.ts';

const base = { scale: 'M' as const, w: 22, h: 2, now: 1.3, focused: true, visible: true, reducedMotion: false };
const sess = { name: 'ledger', hue_deg: 115.75, alarm_text: null };
const hex = (u: Uint8ClampedArray) => Buffer.from(u.buffer).toString('hex');

test('bound session: composes identity hue + pattern + motion; working animates the frame of `now`', () => {
  const m = renderModel({ ...base, session: sess, state: 'working' });
  const want = paint({ scale: 'M', w: 22, h: 2, look: 'working', hueDeg: 115.75, name: 'ledger', alarmText: null, step: 5, reducedMotion: false });
  assert.equal(m.look, 'working');
  assert.equal(m.animate, true);
  assert.equal(m.step, 5);                       // floor(1.3 * 4)
  assert.equal(hex(m.pixels), hex(want.pixels));
  assert.deepEqual(m.text, want.text);
  assert.equal(m.nextFrameDelayMs, 200);        // next boundary at 1.5 s
});

test('working but unfocused / hidden / reduced motion: static frame 0 and no timer', () => {
  const still = hex(paint({ scale: 'M', w: 22, h: 2, look: 'working', hueDeg: 115.75, name: 'ledger', alarmText: null, step: 0, reducedMotion: false }).pixels);
  for (const off of [{ focused: false }, { visible: false }, { reducedMotion: true }]) {
    const m = renderModel({ ...base, ...off, session: sess, state: 'working' });
    assert.equal(m.animate, false);
    assert.equal(m.nextFrameDelayMs, null);
    assert.equal(hex(m.pixels), still);
  }
});

test('degraded: no session, or a session with neither hue nor lineage root -> unknown look, name unbound, no hue', () => {
  for (const session of [null, undefined, { name: 'x', hue_deg: null }, { name: 'x', lineage_root: '  ' }]) {
    const m = renderModel({ ...base, w: 60, session: session as any, state: 'working' });
    assert.equal(m.look, 'unknown');
    assert.equal(m.hueDeg, null);
    assert.equal(m.name, 'unbound');
    assert.equal(m.animate, false);
    assert.equal(m.nextFrameDelayMs, null);
    assert.equal(m.text[0].str, ' unbound ');
    assert.ok(m.text.some(t => t.str.trim() === '?'));
  }
});

test('no registry hue but a lineage root: the same allocator with the peers it can see (default none)', () => {
  const m = renderModel({ ...base, session: { name: 'atlas', lineage_root: '20260930_112648_atl' }, state: 'idle' });
  assert.equal(m.hueDeg, allocate('20260930_112648_atl', []).hue_deg);
  const m2 = renderModel({ ...base, session: { name: 'atlas', lineage_root: '20260930_112648_atl', peers: [0, 1, 2, 3, 4] }, state: 'idle' });
  assert.equal(m2.hueDeg, allocate('20260930_112648_atl', [0, 1, 2, 3, 4]).hue_deg);
  assert.ok(m2.hueDeg! >= hueOfSlot(0));
});

test('registry hue wins over a lineage-root fallback', () => {
  const m = renderModel({ ...base, session: { name: 'a', hue_deg: 207.75, lineage_root: 'whatever' }, state: 'idle' });
  assert.equal(m.hueDeg, 207.75);
});

test('alarm text is shown only for needs-you and fault', () => {
  const s = { name: 'atlas', hue_deg: 299.75, alarm_text: 'INPUT 4m' };
  const w = 60;
  assert.ok(renderModel({ ...base, w, session: s, state: 'needs-you' }).text.some(t => t.str.includes('INPUT 4m')));
  assert.ok(!renderModel({ ...base, w, session: s, state: 'idle' }).text.some(t => t.str.includes('INPUT')));
});

test('unknown state with a bound session keeps the name but paints grey and carries "?"', () => {
  const m = renderModel({ ...base, w: 60, session: sess, state: 'unknown' });
  assert.equal(m.look, 'unknown');
  assert.equal(m.name, 'ledger');
  assert.ok(m.text.some(t => t.str.trim() === '?'));
});

test('an unrecognised state is treated as unknown, never as the last known state', () => {
  assert.equal(renderModel({ ...base, session: sess, state: 'bogus' as any }).look, 'unknown');
});
