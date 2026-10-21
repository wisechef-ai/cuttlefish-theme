import { test } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';
import { FPS, TAU_CLOSE, TAU_OPEN, frameStep, nextFrameDelayMs, shouldAnimate, stepKinetics, twinkleAllowed } from '../domain/motion.ts';

const STATES = ['idle', 'thinking', 'tool', 'review', 'needs-you', 'fault', 'unknown'];
const on = { focused: true, visible: true, reducedMotion: false };

test('kinetics: opening is the fast muscle (tau 0.10 s), closing the slow elastic sac (tau 0.55 s)', () => {
  assert.equal(TAU_OPEN, 0.1);
  assert.equal(TAU_CLOSE, 0.55);
  const opened = stepKinetics(0, 1, 0.1), closed = 1 - stepKinetics(1, 0, 0.1);
  assert.ok(opened > 2 * closed, `${opened} vs ${closed}`);
  assert.ok(Math.abs(opened - (1 - Math.exp(-1))) < 1e-12);
  assert.equal(stepKinetics(0.4, 0.4, 0.2), 0.4);
});

test('kinetics converge and never overshoot (a first-order lag)', () => {
  fc.assert(fc.property(fc.double({ min: 0, max: 1, noNaN: true }), fc.double({ min: 0, max: 1, noNaN: true }), fc.double({ min: 0.001, max: 1, noNaN: true }), (e, target, dt) => {
    const n = stepKinetics(e, target, dt);
    return (n >= Math.min(e, target) - 1e-12) && (n <= Math.max(e, target) + 1e-12);
  }), { seed: 2909 });
});

test('the motion budget: thinking / tool / needs-you animate; idle only when the twinkle setting allows; the rest cost 0 frames', () => {
  const animated: string[] = [];
  for (const state of STATES) if (shouldAnimate({ state, ...on, idleTwinkle: 'on' })) animated.push(state);
  assert.deepEqual(animated, ['idle', 'thinking', 'tool', 'needs-you']);
  assert.deepEqual(STATES.filter(state => shouldAnimate({ state, ...on, idleTwinkle: 'off' })), ['thinking', 'tool', 'needs-you']);
  assert.ok(FPS.thinking <= 10 && FPS.tool <= 10 && FPS['needs-you'] <= 8 && FPS.idle <= 4);
});

test('shouldAnimate is false whenever the surface is unfocused, hidden or in reduced motion', () => {
  for (const state of STATES) for (const off of [{ focused: false }, { visible: false }, { reducedMotion: true }]) {
    assert.equal(shouldAnimate({ state, ...on, idleTwinkle: 'on', ...off }), false, `${state} ${JSON.stringify(off)}`);
  }
});

test('idle twinkle `auto` is off under TMUX, Ghostty, cmux or reduced motion, on elsewhere; on/off are absolute (reduced motion still wins)', () => {
  assert.equal(twinkleAllowed('auto', {}, false), true);
  assert.equal(twinkleAllowed(undefined, {}, false), true);
  for (const host of [{ tmux: true }, { ghostty: true }, { cmux: true }]) assert.equal(twinkleAllowed('auto', host, false), false);
  assert.equal(twinkleAllowed('auto', {}, true), false);
  assert.equal(twinkleAllowed('on', { tmux: true }, false), true);
  assert.equal(twinkleAllowed('on', {}, true), false);
  assert.equal(twinkleAllowed('off', {}, false), false);
});

test('frameStep is per state: floor(t * fps)', () => {
  assert.equal(frameStep(1, 'thinking'), 10);
  assert.equal(frameStep(0.099, 'tool'), 0);
  assert.equal(frameStep(1, 'needs-you'), 8);
  assert.equal(frameStep(1, 'idle'), 4);
  assert.equal(frameStep(1, 'fault'), 6);
});

test('nextFrameDelayMs is null (no timer at rest) whenever shouldAnimate is false', () => {
  for (const state of STATES) for (const focused of [true, false]) for (const visible of [true, false]) for (const reducedMotion of [true, false]) for (const idleTwinkle of ['on', 'off'] as const) {
    const args = { state, focused, visible, reducedMotion, idleTwinkle, tSeconds: 3.3 };
    if (!shouldAnimate(args)) assert.equal(nextFrameDelayMs(args), null, JSON.stringify(args));
  }
});

test('nextFrameDelayMs while animating: lands on the next step boundary at the state fps, never faster', () => {
  for (const state of ['thinking', 'tool', 'needs-you']) {
    assert.equal(nextFrameDelayMs({ state, ...on, tSeconds: 0 }), 1000 / FPS[state as 'tool']);
    fc.assert(fc.property(fc.double({ min: 0, max: 1e5, noNaN: true }), t => {
      const d = nextFrameDelayMs({ state, ...on, tSeconds: t }) as number;
      return d >= 1 && frameStep(t + d / 1000, state) === frameStep(t, state) + 1 && d <= 1000 / FPS[state as 'tool'] + 1;
    }), { seed: 2909 });
  }
});
