import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderModel } from '../app/resolve.ts';
import { allocate, hueOfSlot } from '../domain/identity.ts';

const base = { scale: 'M' as const, w: 60, h: 2, now: 1.34, focused: true, visible: true, reducedMotion: false };
const sess = { name: 'ledger', hue_deg: 115.75, alarm_text: null };
const sig = (m: { cells: readonly { x: number; y: number; glyph: string; rgb: readonly number[] }[] }) => JSON.stringify(m.cells.map(c => [c.x, c.y, c.glyph, ...c.rgb]));

test('bound session: composes identity hue + scatter + motion; thinking animates the frame of `now`', () => {
  const m = renderModel({ ...base, session: sess, state: 'thinking' });
  assert.equal(m.look, 'thinking');
  assert.equal(m.animate, true);
  assert.equal(m.step, 13);                              // floor(1.34 * 10)
  assert.ok(m.cells.length > 0 && m.cells.every(c => c.rgb.length === 3 && c.glyph !== ' '));
  assert.equal(m.nextFrameDelayMs, 60);                  // next boundary at 1.4 s
  const later = renderModel({ ...base, now: 2.9, session: sess, state: 'thinking' });
  assert.notEqual(sig(later), sig(m), 'the cloud moved');
});

test('a surface with no tool signal reports busy as `working`: that is `thinking`', () => {
  assert.equal(renderModel({ ...base, session: sess, state: 'working' }).look, 'thinking');
});

test('thinking but unfocused / hidden / reduced motion: static and no timer', () => {
  for (const off of [{ focused: false }, { visible: false }, { reducedMotion: true }]) {
    const a = renderModel({ ...base, ...off, now: 1, session: sess, state: 'thinking' });
    const b = renderModel({ ...base, ...off, now: 99, session: sess, state: 'thinking' });
    assert.equal(a.animate, false);
    assert.equal(a.nextFrameDelayMs, null);
    assert.equal(sig(a), sig(b));
  }
});

test('the scatter never paints a ground: no background anywhere in the model', () => {
  const m = renderModel({ ...base, session: { ...sess, alarm_text: 'INPUT 4m' }, state: 'needs-you' }) as any;
  assert.equal(m.pixels, undefined);
  assert.ok(m.cells.every((c: any) => Object.keys(c).sort().join() === 'e,glyph,pigment,rgb,x,y'));
  assert.ok(m.cells.some((c: any) => c.pigment === 'amber'));
});

test('idle twinkle follows the setting: off holds still, on moves (and costs a timer)', () => {
  const at = (t: number, idleTwinkle: 'on' | 'off') => renderModel({ ...base, now: t, session: sess, state: 'idle', idleTwinkle });
  assert.equal(at(1, 'off').nextFrameDelayMs, null);
  assert.equal(sig(at(1, 'off')), sig(at(40, 'off')));
  assert.notEqual(at(1, 'on').nextFrameDelayMs, null);
  const frames = new Set<string>();
  for (let t = 0; t < 40; t += 0.25) frames.add(sig(at(t, 'on')));
  assert.ok(frames.size >= 4, `twinkle never showed (${frames.size})`);
});

test('degraded: no session, or a session with neither hue nor lineage root -> unknown look, name unbound, grey, no hue', () => {
  for (const session of [null, undefined, { name: 'x', hue_deg: null }, { name: 'x', lineage_root: '  ' }]) {
    const m = renderModel({ ...base, w: 60, session: session as any, state: 'thinking' });
    assert.equal(m.look, 'unknown');
    assert.equal(m.hueDeg, null);
    assert.equal(m.name, 'unbound');
    assert.equal(m.animate, false);
    assert.equal(m.nextFrameDelayMs, null);
    assert.equal(m.text[0].str, ' unbound ');
    assert.ok(m.text.some(t => t.str.trim() === '?'));
    assert.ok(m.cells.length > 0 && m.cells.every(c => c.pigment === 'grey' && c.rgb[0] === c.rgb[1] && c.rgb[1] === c.rgb[2]));
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
  assert.ok(renderModel({ ...base, session: s, state: 'needs-you' }).text.some(t => t.str.includes('INPUT 4m')));
  assert.ok(!renderModel({ ...base, session: s, state: 'idle' }).text.some(t => t.str.includes('INPUT')));
});

test('fault: blanch then only red organs remain; static', () => {
  const m = renderModel({ ...base, w: 120, h: 24, scale: 'S', session: { ...sess, alarm_text: 'ERROR 2m' }, state: 'fault' });
  assert.ok(m.cells.every(c => c.pigment === 'red'));
  assert.equal(m.animate, false);
  assert.ok(m.text.some(t => t.str.includes('ERROR 2m')));
});

test('XL takes pixels: the organ grid is w/12 x h/24', () => {
  const m = renderModel({ ...base, scale: 'XL', w: 960, h: 480, session: sess, state: 'review' });
  assert.deepEqual([m.cols, m.rows], [80, 20]);
  assert.ok(m.cells.length > 30);
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
