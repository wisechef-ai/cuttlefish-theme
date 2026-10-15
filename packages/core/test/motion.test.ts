import { test } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';
import { frameStep, nextFrameDelayMs, shouldAnimate } from '../domain/motion.ts';

const STATES = ['idle', 'working', 'review', 'needs-you', 'fault', 'unknown'];

test('shouldAnimate is true for exactly one cell of the truth table: working, focused, visible, motion allowed', () => {
  const trues: string[] = [];
  for (const state of STATES) for (const focused of [true, false]) for (const visible of [true, false]) for (const reducedMotion of [true, false]) {
    if (shouldAnimate({ state, focused, visible, reducedMotion })) trues.push(`${state}/${focused}/${visible}/${reducedMotion}`);
  }
  assert.deepEqual(trues, ['working/true/true/false']);
});

test('frameStep: one dot per 0.25 s, i.e. at most 4 distinct frames per second', () => {
  assert.equal(frameStep(0), 0);
  assert.equal(frameStep(0.249), 0);
  assert.equal(frameStep(0.25), 1);
  assert.equal(frameStep(1), 4);
  assert.equal(frameStep(2.99), 11);
  fc.assert(fc.property(fc.double({ min: 0, max: 1e6, noNaN: true }), t => frameStep(t + 1) - frameStep(t) === 4), { seed: 2909 });
});

test('nextFrameDelayMs is null (no timer at rest) whenever shouldAnimate is false', () => {
  for (const state of STATES) for (const focused of [true, false]) for (const visible of [true, false]) for (const reducedMotion of [true, false]) {
    const args = { state, focused, visible, reducedMotion, tSeconds: 1.1 };
    if (!shouldAnimate(args)) assert.equal(nextFrameDelayMs(args), null, JSON.stringify(args));
  }
});

test('nextFrameDelayMs while animating: lands on the next step boundary, never faster than 4 fps', () => {
  const on = { state: 'working', focused: true, visible: true, reducedMotion: false };
  assert.equal(nextFrameDelayMs({ ...on, tSeconds: 0 }), 250);
  assert.equal(nextFrameDelayMs({ ...on, tSeconds: 0.1 }), 150);
  fc.assert(fc.property(fc.double({ min: 0, max: 1e6, noNaN: true }), t => {
    const d = nextFrameDelayMs({ ...on, tSeconds: t }) as number;
    assert.ok(d >= 1 && d <= 250);
    assert.equal(frameStep(t + d / 1000), frameStep(t) + 1);
    return true;
  }), { seed: 2909 });
});
