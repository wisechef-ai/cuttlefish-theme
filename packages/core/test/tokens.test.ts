import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { TOKENS } from '../domain/tokens.ts';

test('inlined TOKENS deep-equals the frozen packages/core/tokens.json (bundles stay import-free)', () => {
  const json = JSON.parse(readFileSync(new URL('../tokens.json', import.meta.url), 'utf8'));
  assert.deepEqual(JSON.parse(JSON.stringify(TOKENS)), json);
});

test('TOKENS is deeply frozen: a consumer cannot retune the design at runtime', () => {
  assert.throws(() => { (TOKENS as any).ground.rgb[0] = 255; }, TypeError);
  assert.throws(() => { (TOKENS as any).identity.dot_chroma = 0.3; }, TypeError);
});
