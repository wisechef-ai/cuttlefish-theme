// Unit: identity allocation — the hue a session owns. Structure ported from
// origin/v22 packages/core/domain (slots on an arc, farthest-point from peers).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { allocate, ARC_END, ARC_START, hueDistance, hueOfSlot, preferredSlot, SLOTS } from '../../src/domain/identity.ts'

const ROOT = '20261105_090000_1f3a5c'

test('the arc avoids amber/red: every slot hue lies in [110, 340)', () => {
  for (let k = 0; k < SLOTS; k++) {
    const h = hueOfSlot(k)
    assert.ok(h >= ARC_START && h < ARC_END, `slot ${k} hue ${h} outside the arc`)
  }
})

test('allocate is deterministic and does not need peers to be reproducible', () => {
  assert.deepEqual(allocate(ROOT, []), allocate(ROOT, []))
  assert.equal(allocate(ROOT, []).slot, preferredSlot(ROOT))
})

test('allocate keeps two live sessions a handshake apart (>= 30 degrees)', () => {
  const a = allocate('20261105_090000_1f3a5c', [])
  const b = allocate('20261105_090137_1f3a5c', [a.slot])
  assert.ok(hueDistance(a.hue_deg, b.hue_deg) >= 30, `only ${hueDistance(a.hue_deg, b.hue_deg)}° apart`)
})

test('a full house reports crowded instead of guessing', () => {
  const all = Array.from({ length: SLOTS }, (_, k) => k)
  const a = allocate(ROOT, all)
  assert.equal(a.crowded, true)
  // crowded still returns a usable hue (the preferred slot)
  assert.ok(a.hue_deg >= ARC_START && a.hue_deg < ARC_END)
})

test('an empty or whitespace root is refused, never guessed; so is a bogus peer slot', () => {
  assert.throws(() => allocate('', []))
  assert.throws(() => allocate('   ', []))
  assert.throws(() => allocate(ROOT, [-1]))
  assert.throws(() => allocate(ROOT, [SLOTS]))
})
