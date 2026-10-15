import { test } from 'node:test';
import assert from 'node:assert/strict';
import { oklch } from '../domain/oklch.ts';

test('OKLCh to sRGB: black, white and neutral grey anchors', () => {
  assert.deepEqual(oklch(0, 0, 0), [0, 0, 0]);
  assert.deepEqual(oklch(1, 0, 123), [255, 255, 255]);
  const g = oklch(0.6, 0, 0);
  assert.equal(g[0], g[1]); assert.equal(g[1], g[2]);
});

test('out-of-gamut colours clip to 0..255 integers', () => {
  for (const [L, C, h] of [[0.7, 0.4, 30], [0.5, 0.35, 265], [0.95, 0.3, 140]] as const) {
    for (const v of oklch(L, C, h)) { assert.ok(Number.isInteger(v) && v >= 0 && v <= 255); }
  }
});

test('hue rotates the colour: red-ish at 30 deg, green-ish at 145, blue-ish at 265 (same L, C)', () => {
  const [r1, g1] = oklch(0.65, 0.15, 30), [r2, g2] = oklch(0.65, 0.15, 145), [, , b3] = oklch(0.65, 0.15, 265);
  assert.ok(r1 > g1); assert.ok(g2 > r2); assert.ok(b3 > 150);
});
