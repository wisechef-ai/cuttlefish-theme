// Unit: C5 — settings hot-reload. The file's mtime is an opaque version token; refetch exactly
// when it CHANGES, never on a stutter, never on an unreadable stat.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { configPlan, initialConfigWatch } from '../../src/domain/configwatch.ts'

test('the first sight always fetches', () => {
  const { refetch, next } = configPlan(initialConfigWatch(), 1000)
  assert.equal(refetch, true)
  assert.deepEqual(next, { seen: true, mtime: 1000 })
})

test('the same token again does not; a changed token does', () => {
  const seen = configPlan(initialConfigWatch(), 'ms:1').next
  assert.equal(configPlan(seen, 'ms:1').refetch, false)
  assert.equal(configPlan(seen, 'ms:1').next, seen, 'no refetch keeps the watch untouched')
  const bump = configPlan(seen, 'ms:2')
  assert.equal(bump.refetch, true)
  assert.deepEqual(bump.next, { seen: true, mtime: 'ms:2' })
})

test('an unreadable mtime (null or junk) keeps the last settings — it never resets', () => {
  const seen = configPlan(initialConfigWatch(), 1234).next
  const junk: (number | string | null)[] = [null, Number.NaN, '']
  for (const m of junk) {
    const r = configPlan(seen, m)
    assert.equal(r.refetch, false)
    assert.equal(r.next, seen)
  }
  // 0 is a legal epoch mtime, not junk: it is a token like any other
  assert.equal(configPlan(seen, 0).refetch, true)
})

test('a number token and its string form are the SAME version (stat jitter must not refetch)', () => {
  const seen = configPlan(initialConfigWatch(), 7).next
  assert.equal(configPlan(seen, '7').refetch, false, 'mtime 7 seen twice, once as a string, is no change')
  assert.equal(configPlan(seen, '8').refetch, true)
})

test('recovery to the same token after a failure does not refetch again', () => {
  const a = configPlan(initialConfigWatch(), 500).next
  const b = configPlan(a, 600).next          // refetched
  assert.equal(configPlan(b, 500).refetch, true, 'a genuinely older-then-newer token changed twice')
  assert.equal(configPlan(b, 600).refetch, false)
})
