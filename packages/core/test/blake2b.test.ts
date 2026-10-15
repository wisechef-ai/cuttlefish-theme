import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { blake2b, utf8 } from '../domain/blake2b.ts';

const hex = (u: Uint8Array) => Array.from(u, b => b.toString(16).padStart(2, '0')).join('');
const fx = JSON.parse(readFileSync(new URL('../fixtures/blake2b-vectors.json', import.meta.url), 'utf8'));

test('RFC 7693 appendix A: BLAKE2b-512("abc")', () => {
  assert.equal(
    hex(blake2b(utf8('abc'), 64)),
    'ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d1' +
    '7d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923',
  );
});

test('empty input, 32-byte digest', () => {
  assert.equal(hex(blake2b(new Uint8Array(0), 32)), '0e5751c026e543b2e8ab2eb06099daa1d1e5df47778f7787faab45cdf12fe3a8');
});

test(`matches python hashlib on every fixture case (>= 200, non-ASCII included)`, () => {
  assert.ok(fx.cases.length >= 200, `only ${fx.cases.length} cases`);
  assert.ok(fx.cases.some((c: any) => /[^\x00-\x7f]/.test(c.msg)), 'fixture has no non-ASCII case');
  for (const c of fx.cases) assert.equal(hex(blake2b(utf8(c.msg), c.size)), c.digest, `size ${c.size} msg ${JSON.stringify(c.msg).slice(0, 40)}`);
});

test('digest length is honoured and out-of-range sizes throw', () => {
  for (const n of [1, 17, 64]) assert.equal(blake2b(utf8('x'), n).length, n);
  assert.throws(() => blake2b(utf8('x'), 0));
  assert.throws(() => blake2b(utf8('x'), 65));
});

test('input is not mutated and utf8() encodes astral code points as 4 bytes', () => {
  const m = utf8('🐙');
  assert.deepEqual(Array.from(m), [0xf0, 0x9f, 0x90, 0x99]);
  const before = Array.from(m);
  blake2b(m, 32);
  assert.deepEqual(Array.from(m), before);
});
