// Unit: the bloom and the motion plans. Bloom shape from origin/feat/sparse-dots-preview
// tools/dots_preview.py (open tau 100 ms, close tau 550 ms) — a fast flare that decays slowly.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { BLOOM_MS, bloomFactor, motionPlan } from '../../src/domain/motion.ts'
import type { PatternKind } from '../../src/domain/types.ts'

test('BLOOM_MS is a few seconds', () => {
  assert.ok(BLOOM_MS >= 800 && BLOOM_MS <= 4000)
})

test('off, reduced and settled are EXACTLY 1: renders under them are bit-identical', () => {
  for (const s of [0, 1, 150, 400, 800, 2400, BLOOM_MS - 1, BLOOM_MS, 6000, 99999]) {
    assert.equal(bloomFactor(s, 'still', true), 1)
    assert.equal(bloomFactor(s, 'off', false), 1)
  }
  // settled (still, unreduced): the bloom is over — exactly 1, whatever the history
  for (const s of [BLOOM_MS, 6000, 99999]) assert.equal(bloomFactor(s, 'still', false), 1)
})

test('the bloom rises fast to a peak >= 1.5x and decays monotonically after it', () => {
  const at = (s: number): number => bloomFactor(s, 'still', false)
  assert.ok(at(0) < 1.02, 'a change starts from rest')
  const peak = Math.max(at(150), at(400), at(800))
  assert.ok(peak >= 1.5, `peak ${peak} < 1.5`)
  let prev = Infinity
  for (let s = 800; s <= BLOOM_MS; s += 100) {
    assert.ok(at(s) <= prev + 1e-12, 'no re-bloom on the way down')
    prev = at(s)
  }
  assert.equal(at(BLOOM_MS), 1)
})

test('motionPlan: off and reduced never animate; still animates only clouds and a bloom', () => {
  for (const pattern of ['mottle', 'clouds', 'zebra', 'blanch', 'eyespot'] as PatternKind[]) {
    for (const motion of ['off', 'still', 'alive'] as const) {
      const p = motionPlan({ pattern, motion, reducedMotion: true, sinceChangeMs: 10_000 })
      assert.equal(p.animate, false, `reduced ${pattern}/${motion} must not animate`)
    }
    assert.equal(motionPlan({ pattern, motion: 'off', reducedMotion: false, sinceChangeMs: 10_000 }).animate, false)
    // still, long settled: only the cloud keeps moving
    const st = motionPlan({ pattern, motion: 'still', reducedMotion: false, sinceChangeMs: 10_000 })
    assert.equal(st.animate, pattern === 'clouds')
    if (pattern === 'clouds') assert.ok(st.fps >= 4 && st.fps <= 10, `clouds fps ${st.fps}`)
  }
})

test('motionPlan: alive animates everything, slowly; a bloom in progress animates under still', () => {
  for (const pattern of ['mottle', 'clouds', 'zebra', 'blanch', 'eyespot'] as PatternKind[]) {
    const p = motionPlan({ pattern, motion: 'alive', reducedMotion: false, sinceChangeMs: 10_000 })
    assert.equal(p.animate, true, `alive ${pattern} must animate`)
    assert.ok(p.fps <= 10, `alive ${pattern} fps ${p.fps} > 10`)
    if (pattern !== 'clouds') assert.ok(p.fps <= 4, `alive non-cloud ${pattern} fps ${p.fps} > 4`)
  }
  const bloom = motionPlan({ pattern: 'mottle', motion: 'still', reducedMotion: false, sinceChangeMs: 100 })
  assert.equal(bloom.animate, true, 'a bloom in progress animates even under still')
  assert.ok(bloom.fps >= 4 && bloom.fps <= 10)
})
