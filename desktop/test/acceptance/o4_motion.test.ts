// ACCEPTANCE CONTRACT — O4 (pure half): motion is configurable, quiet by default, honest about reduced motion (locked).
// SPEC C3: default still; slow passing clouds only while working; one short bloom per change; off when the OS asks.
// Ceiling ↔ floor: "static states request no frames" AND "working really moves at ≥ 4 changes/s".
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { GROUNDS, H, PRESETS, ROOTS, SETTLED_MS, W } from './corpus.ts'
import { type Dot, dotDeltaL, organKey } from './instruments.ts'
import { EXPECT, read, reading } from './language.ts'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Domain = any
const loaded: { mod?: Domain; err?: unknown } = {}
try { loaded.mod = await import('../../src/domain/index.ts') } catch (e) { loaded.err = e }
const D = (): Domain => {
  if (!loaded.mod) throw new Error(`desktop/src/domain/index.ts did not load: ${String(loaded.err)}`)
  return loaded.mod
}

const KINDS = ['mottle', 'clouds', 'zebra', 'blanch', 'eyespot'] as const

test('O4.1 motionPlan: off / reduced motion never animate; still animates only clouds and a bloom', () => {
  for (const pattern of KINDS) {
    for (const sinceChangeMs of [0, 100, SETTLED_MS, 60_000]) {
      for (const motion of ['still', 'alive', 'off'] as const) {
        const reduced = D().motionPlan({ motion, reducedMotion: true, pattern, sinceChangeMs })
        assert.equal(reduced.animate, false, `reduced motion animated ${motion}/${pattern}`)
      }
      assert.equal(D().motionPlan({ motion: 'off', reducedMotion: false, pattern, sinceChangeMs }).animate, false)
      const still = D().motionPlan({ motion: 'still', reducedMotion: false, pattern, sinceChangeMs })
      const blooming = sinceChangeMs < D().BLOOM_MS
      assert.equal(still.animate, pattern === 'clouds' || blooming, `still ${pattern} @${sinceChangeMs}`)
      if (still.animate) assert.ok(still.fps >= 4 && still.fps <= 10, `still fps ${still.fps} outside [4, 10]`)
    }
  }
})

test('O4.2 alive adds only slow motion (≤ 4 fps for resting / needs_you), never faster than 10 fps', () => {
  for (const pattern of KINDS) {
    const p = D().motionPlan({ motion: 'alive', reducedMotion: false, pattern, sinceChangeMs: SETTLED_MS })
    assert.ok(p.fps <= 10, `alive ${pattern} fps ${p.fps}`)
    if (p.animate && pattern !== 'clouds') assert.ok(p.fps <= 4, `alive ${pattern} idles at ${p.fps} fps (≤ 4)`)
  }
  assert.equal(D().motionPlan({ motion: 'alive', reducedMotion: false, pattern: 'mottle', sinceChangeMs: SETTLED_MS }).animate, true,
    'alive must add the resting twinkle')
})

function render(root: string, preset: string, tMs: number, over: Record<string, unknown> = {}): Dot[] {
  const s = D().DEFAULT_SETTINGS
  const hueDeg = D().allocate(root, []).hue_deg
  return D().renderField({ seed: root, width: W, height: H, hueDeg, ground: GROUNDS[0], pattern: D().patternOf(s, preset),
    intensity: 1, motion: 'still', reducedMotion: false, tMs, sinceChangeMs: SETTLED_MS + tMs, ...over })
}
const changed = (a: Dot[], b: Dot[]): number => {
  let n = 0
  for (let i = 0; i < a.length; i++) if (Math.abs(dotDeltaL(a[i], GROUNDS[0]) - dotDeltaL(b[i], GROUNDS[0])) > 0.002) n++
  return n / a.length
}

test('O4.3 working really moves: ≥ 15% of organs change within 250 ms, the band travels, organs stay put', () => {
  for (const root of ROOTS.slice(0, 8)) {
    const frames = [0, 250, 500, 1000, 3000].map(t => render(root, 'working', t))
    for (const f of frames) assert.equal(organKey(f), organKey(frames[0]))
    assert.ok(changed(frames[0], frames[1]) >= 0.15, `${root}: working frame 0→250 ms changed ${changed(frames[0], frames[1])}`)
    assert.ok(changed(frames[0], frames[4]) >= 0.15, `${root}: the cloud does not travel over 3 s`)
  }
})

test('O4.4 static means static: resting/needs_you/error/finished_unseen under still, and EVERYTHING under off/reduced', () => {
  for (const root of ROOTS.slice(0, 6)) {
    for (const preset of ['resting', 'needs_you', 'error', 'finished_unseen']) {
      assert.deepEqual(render(root, preset, 0), render(root, preset, 2750), `${root}/${preset} moved under still`)
    }
    for (const quiet of [{ motion: 'off' }, { reducedMotion: true }]) {
      for (const preset of ['resting', 'working', 'needs_you']) {
        assert.deepEqual(render(root, preset, 0, quiet), render(root, preset, 4321, quiet), `${root}/${preset} ${JSON.stringify(quiet)} moved`)
      }
    }
  }
})

test('O4.5 alive twinkle is sparse: ≤ 5% of organs change between frames, but something changes over 6 s', () => {
  for (const root of ROOTS.slice(0, 6)) {
    const at = (t: number) => render(root, 'resting', t, { motion: 'alive' })
    let any = false
    let prev = at(0)
    for (let t = 250; t <= 6000; t += 250) {
      const cur = at(t)
      const c = changed(prev, cur)
      assert.ok(c <= 0.05, `${root}: alive resting changed ${(c * 100).toFixed(1)}% of organs in one frame`)
      if (c > 0) any = true
      prev = cur
    }
    assert.ok(any, `${root}: alive resting never twinkled`)
  }
})

test('O4.6 with no motion at all (off / reduced) every state is still told apart, on every ground', () => {
  for (const quiet of [{ motion: 'off' }, { reducedMotion: true }]) {
    for (const root of ROOTS.slice(0, 10)) {
      for (const ground of GROUNDS) {
        for (const p of PRESETS) {
          const got = reading(read(render(root, p, 777, { ...quiet, ground }), ground))
          assert.equal(got, EXPECT[p], `${p}@${ground}/${root} ${JSON.stringify(quiet)} read as ${got}`)
        }
      }
    }
  }
})
