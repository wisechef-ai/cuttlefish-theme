// Unit: the pattern language's margins, measured with the same instruments the acceptance
// contract uses (imported read-only). The acceptance suite asserts the FLOORS; this pins the
// HEADROOM we actually have — a regression that eats the margin fails here before it fails the
// contract. Includes the error-blanching rule from the v2 spec (blanch to PALE: lighter than the
// same session's resting organs, still visible) ahead of its locked assertion.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { GROUNDS, H, PRESETS, ROOTS, SETTLED_MS, W } from '../acceptance/corpus.ts'
import {
  banding, type Dot, dotDeltaL, lchOf, lightnessStats, mean, meanChroma, organKey, spotRatios,
} from '../acceptance/instruments.ts'
import { EXPECT, read, reading } from '../acceptance/language.ts'
import { allocate, DEFAULT_SETTINGS, patternOf, renderField } from '../../src/domain/index.ts'

const hueFor = (root: string): number => allocate(root, []).hue_deg

function field(root: string, ground: string, preset: string, over: Record<string, unknown> = {}): Dot[] {
  return renderField({
    seed: root, width: W, height: H, hueDeg: hueFor(root), ground,
    pattern: patternOf(DEFAULT_SETTINGS, preset), intensity: 1, motion: 'still', reducedMotion: false,
    tMs: 0, sinceChangeMs: SETTLED_MS, ...over,
  })
}

// A third of the corpus keeps this fast; the full 300-render matrix is the acceptance suite's job.
const ROOTS_SAMPLE = ROOTS.filter((_, i) => i % 3 === 0)

test('every preset still reads as itself, with banding margin on both sides of the thresholds', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS_SAMPLE) {
      for (const p of PRESETS) {
        const dots = field(root, ground, p)
        assert.equal(reading(read(dots, ground)), EXPECT[p])
        const b = banding(dots, ground, W, H)
        if (p === 'working') {
          assert.ok(b.lowK >= 0.75, `clouds lowK ${b.lowK.toFixed(2)} too close to the 0.55 floor`)
          assert.ok(b.highK <= 0.45 * b.lowK, `clouds highK ${b.highK.toFixed(2)} crowds its lowK`)
        }
        if (p === 'needs_you') {
          assert.ok(b.highK >= 0.75, `stripes highK ${b.highK.toFixed(2)} too close to the 0.6 floor`)
          assert.ok(b.highK >= 2 * b.lowK, `stripes lowK ${b.lowK.toFixed(2)} crowds its highK`)
        }
        if (p === 'resting' || p === 'finished_unseen') {
          assert.ok(b.highK <= 0.5, `calm/preset highK ${b.highK.toFixed(2)} could read as stripes`)
          assert.ok(b.lowK <= 0.5, `calm/preset lowK ${b.lowK.toFixed(2)} could read as clouds`)
        }
      }
    }
  }
})

test('error = blanching to PALE: lighter than the same session\'s resting organs, still visible', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS_SAMPLE) {
      const err = field(root, ground, 'error').filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0)
      const rest = field(root, ground, 'resting').filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0)
      // signed lightness along the ground's contrast direction
      const gl = lchOf(ground).L
      const dir = lchOf(ground).L < 0.5 ? 1 : -1
      const signed = (ds: Dot[]): number => mean(ds.map(d => gl + dir * dotDeltaL(d, ground)))
      const lighterBy = signed(err) - signed(rest)
      assert.ok(lighterBy >= 0.01, `${ground}/${root}: error only ${lighterBy.toFixed(4)} lighter than resting (need >= 0.01)`)
      const errMean = mean(err.map(d => dotDeltaL(d, ground)))
      assert.ok(errMean >= 0.012, `${ground}/${root}: error mean dL ${errMean.toFixed(4)} — blanch is not invisible`)
      assert.ok(meanChroma(err) <= 0.03, `${ground}/${root}: error chroma ${meanChroma(err).toFixed(3)} — not pale`)
    }
  }
})

test('resting headroom: mean ink >= 0.02, p95 <= 0.048, and the mottle varies', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS_SAMPLE) {
      const organs = field(root, ground, 'resting').filter(d => d.role === 'organ' && d.alpha > 0)
      const st = lightnessStats(organs, ground)
      assert.ok(st.mean >= 0.02, `${ground}/${root}: resting mean ${st.mean.toFixed(4)}`)
      assert.ok(st.p95 <= 0.048, `${ground}/${root}: resting p95 ${st.p95.toFixed(4)}`)
      const v = organs.map(d => dotDeltaL(d, ground))
      assert.ok(Math.sqrt(mean(v.map(x => (x - st.mean) ** 2))) / st.mean >= 0.3, 'the mottle flattened')
    }
  }
})

test('needs_you >= 3x resting; every preset stays well under the text-safe ceiling', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS_SAMPLE) {
      const rest = lightnessStats(field(root, ground, 'resting'), ground).mean
      assert.ok(lightnessStats(field(root, ground, 'needs_you'), ground).mean >= 3 * rest, 'needs_you lost its punch')
      for (const p of PRESETS) {
        assert.ok(lightnessStats(field(root, ground, p), ground).p95 <= 0.18, `${p} too loud`)
      }
    }
  }
})

test('the eye-spot is exactly one outlier: first >= 4.5x, second <= 1.5x the median organ', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS_SAMPLE) {
      const sp = spotRatios(field(root, ground, 'finished_unseen'))
      assert.ok(sp.first >= 4.5, `eye-spot only ${sp.first.toFixed(2)}x the median`)
      assert.ok(sp.second <= 1.5, `a second outlier (${sp.second.toFixed(2)}x) would blur the read`)
    }
  }
})

test('organs are the same dots whatever the state, time or bloom (positions pinned)', () => {
  const root = ROOTS_SAMPLE[0]
  const key = organKey(field(root, GROUNDS[0], 'resting'))
  for (const p of PRESETS) {
    for (const tMs of [0, 1700, 9000]) {
      for (const s of [0, 400, SETTLED_MS]) {
        assert.equal(organKey(field(root, GROUNDS[0], p, { tMs, sinceChangeMs: s })), key)
      }
    }
  }
})

test('hue never drifts with state: every organ of every preset sits on the identity hue', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS_SAMPLE) {
      const h = hueFor(root)
      for (const p of PRESETS) {
        if (p === 'error') continue
        const organs = field(root, ground, p).filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0)
        for (const d of organs) {
          const dd = Math.abs(lchOf(d.color).h - h)
          const dist = Math.min(dd, 360 - dd)
          assert.ok(dist <= 5, `${p}@${ground}: organ hue ${dist.toFixed(2)}° off (budget 10°)`)
        }
      }
    }
  }
})
