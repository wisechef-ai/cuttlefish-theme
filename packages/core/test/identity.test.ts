import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import fc from 'fast-check';
import { allocate, hueOfSlot, preferredSlot, SLOTS } from '../domain/identity.ts';

const FC = { seed: 2909, numRuns: 400 };
const slotArb = fc.integer({ min: 0, max: SLOTS - 1 });
const rootArb = fc.string({ unit: 'grapheme', minLength: 1, maxLength: 40 }).filter(s => s.trim() !== '');

test('hueOfSlot is the 20-slot lattice on [110,340) and equals the P1 fixture hues', () => {
  const fx = JSON.parse(readFileSync(new URL('../../../tools/p1/stub-sessions.json', import.meta.url), 'utf8'));
  const lattice = Array.from({ length: SLOTS }, (_, k) => hueOfSlot(k));
  assert.equal(lattice[0], 115.75);
  assert.equal(lattice[19], 334.25);
  assert.deepEqual([...lattice].sort((a, b) => a - b), fx.sessions.map((s: any) => s.hue_deg).sort((a: number, b: number) => a - b));
  assert.throws(() => hueOfSlot(-1));
  assert.throws(() => hueOfSlot(20));
  assert.throws(() => hueOfSlot(1.5));
});

test('empty or whitespace lineage root is an error (caller degrades to unbound, never guesses)', () => {
  for (const bad of ['', '   ', '\n\t']) {
    assert.throws(() => preferredSlot(bad));
    assert.throws(() => allocate(bad, []));
  }
});

test('no peers: the allocation is the hashed preferred slot, not crowded', () => {
  const a = allocate('20260930_104729_led', []);
  assert.equal(a.slot, preferredSlot('20260930_104729_led'));
  assert.equal(a.hue_deg, hueOfSlot(a.slot));
  assert.equal(a.crowded, false);
});

test('all 20 slots held: slot falls back to preferred and crowded is surfaced', () => {
  const root = 'quill';
  const all = Array.from({ length: SLOTS }, (_, k) => k);
  const a = allocate(root, all);
  assert.deepEqual(a, { slot: preferredSlot(root), hue_deg: hueOfSlot(preferredSlot(root)), crowded: true });
  // >20 peers (duplicates) is still full occupancy
  assert.equal(allocate(root, [...all, ...all, 3]).crowded, true);
});

test('property: slot is never held by a peer while a free slot exists', () => {
  fc.assert(fc.property(rootArb, fc.array(slotArb, { maxLength: 19 }), (root, peers) => {
    fc.pre(new Set(peers).size < SLOTS);
    const a = allocate(root, peers);
    assert.ok(!peers.includes(a.slot));
    assert.equal(a.crowded, false);
  }), FC);
});

test('property: peer order and duplication do not change the result', () => {
  fc.assert(fc.property(rootArb, fc.array(slotArb, { maxLength: 25 }), fc.integer(), (root, peers, k) => {
    const base = allocate(root, peers);
    const shuffled = [...peers].sort((a, b) => ((a * 7919 + k) % 31) - ((b * 7919 + k) % 31));
    assert.deepEqual(allocate(root, shuffled), base);
    assert.deepEqual(allocate(root, [...peers, ...peers]), base);
  }), FC);
});

test('property: 20 sequential allocations (each seeing the earlier ones) fill 20 distinct slots', () => {
  fc.assert(fc.property(fc.uniqueArray(rootArb, { minLength: 20, maxLength: 20 }), roots => {
    const held: number[] = [];
    for (const r of roots) { const a = allocate(r, held); assert.equal(a.crowded, false); held.push(a.slot); }
    assert.equal(new Set(held).size, SLOTS);
  }), FC);
});

test('property: hue is always inside the identity arc [110, 340) and is the lattice hue of the slot', () => {
  fc.assert(fc.property(rootArb, fc.array(slotArb, { maxLength: 25 }), (root, peers) => {
    const a = allocate(root, peers);
    assert.ok(a.hue_deg >= 110 && a.hue_deg < 340);
    assert.equal(a.hue_deg, hueOfSlot(a.slot));
  }), FC);
});

test('capped farthest-point: with one peer the slot is preferred if >= CAP away, else pushed out to distance CAP', () => {
  // find roots by brute force so the test names behaviour, not hash values
  for (let i = 0; i < 400; i++) {
    const root = `r${i}`;
    const pref = preferredSlot(root);
    const peer = (pref + 1) % SLOTS;
    const a = allocate(root, [peer]);
    assert.ok(Math.abs(a.slot - peer) >= 3, `${root}: slot ${a.slot} peer ${peer}`);
  }
});

test('golden vectors: >= 2000 cases, every one reproduced exactly', () => {
  const fx = JSON.parse(readFileSync(new URL('../fixtures/identity-vectors.json', import.meta.url), 'utf8'));
  assert.ok(fx.cases.length >= 2000, `only ${fx.cases.length}`);
  const sizes = new Set(fx.cases.map((c: any) => c.peers.length));
  for (let n = 0; n <= 25; n++) assert.ok(sizes.has(n), `no case with ${n} peers`);
  assert.ok(fx.cases.some((c: any) => c.crowded), 'no crowded case');
  assert.ok(fx.cases.some((c: any) => new Set(c.peers).size < c.peers.length), 'no duplicate-peer case');
  assert.ok(fx.cases.some((c: any) => /[^\x00-\x7f]/.test(c.lineage_root)), 'no non-ASCII root');
  for (const c of fx.cases) {
    assert.equal(preferredSlot(c.lineage_root), c.preferred, c.lineage_root);
    assert.deepEqual(allocate(c.lineage_root, c.peers), { slot: c.slot, hue_deg: c.hue_deg, crowded: c.crowded }, JSON.stringify(c));
  }
});
