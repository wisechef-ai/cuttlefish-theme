// ACCEPTANCE CONTRACT — O2: the colour-pattern language (locked).
// SPEC C4/C7/C8 + lead ruling: the background field is a SPARSE chromatophore scatter on the user's own ground.
// Every ceiling here is paired with a floor over the SAME sample: "near-invisible at rest" AND "the five states are
// told apart by a fixed classifier on every identity and ground"; "hue never changes with state" AND "two sessions
// never share a hue".
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { GROUNDS, H, PRESETS, ROOTS, SETTLED_MS, W } from './corpus.ts'
import {
  coverage, type Dot, dotDeltaL, hueDistance, lchOf, lightnessStats, mean, meanChroma, organKey, spotRatios,
} from './instruments.ts'
import { EXPECT, read, reading } from './language.ts'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Domain = any
const loaded: { mod?: Domain; err?: unknown } = {}
try { loaded.mod = await import('../../src/domain/index.ts') } catch (e) { loaded.err = e }
const D = (): Domain => {
  if (!loaded.mod) throw new Error(`desktop/src/domain/index.ts did not load: ${String(loaded.err)}`)
  return loaded.mod
}

const hueFor = (root: string): number => D().allocate(root, []).hue_deg

function field(root: string, ground: string, preset: string, over: Record<string, unknown> = {}): Dot[] {
  const s = D().DEFAULT_SETTINGS
  return D().renderField({
    seed: root, width: W, height: H, hueDeg: hueFor(root), ground,
    pattern: D().patternOf(s, preset), intensity: 1, motion: 'still', reducedMotion: false,
    tMs: 0, sinceChangeMs: SETTLED_MS, ...over,
  })
}

test('O2.1 every preset reads as exactly its own pattern, on every identity and ground (5 × 20 × 3)', () => {
  const misses: string[] = []
  for (const ground of GROUNDS) {
    for (const root of ROOTS) {
      for (const p of PRESETS) {
        const got = reading(read(field(root, ground, p), ground))
        if (got !== EXPECT[p]) misses.push(`${p}@${ground}/${root}: read as ${got}`)
      }
    }
  }
  assert.deepEqual(misses.slice(0, 12), [], `${misses.length}/300 renders misread`)
})

test('O2.2 resting is near-invisible (p95 ΔL ≤ 0.05) yet present (mean ΔL ≥ 0.012, ≥ 40 organs, sparse)', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS) {
      const dots = field(root, ground, 'resting')
      const organs = dots.filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0)
      const st = lightnessStats(organs, ground)
      const where = `${ground}/${root}`
      assert.ok(st.p95 <= 0.05, `${where}: resting p95 ΔL ${st.p95.toFixed(4)} > 0.05`)
      assert.ok(st.mean >= 0.012, `${where}: resting mean ΔL ${st.mean.toFixed(4)} < 0.012 (invisible is not near-invisible)`)
      assert.ok(organs.length >= 40, `${where}: only ${organs.length} visible organs`)
      const cov = coverage(dots, W, H)
      assert.ok(cov >= 0.001 && cov <= 0.06, `${where}: coverage ${cov.toFixed(4)} outside the sparse band [0.001, 0.06]`)
      // a mottle, not a flat tint: organs differ from each other
      const v = organs.map(d => dotDeltaL(d, ground))
      const cv = Math.sqrt(mean(v.map(x => (x - st.mean) ** 2))) / st.mean
      assert.ok(cv >= 0.15, `${where}: resting ΔL coefficient of variation ${cv.toFixed(3)} < 0.15 (no mottle)`)
    }
  }
})

test('O2.3 settled loudness: needs_you readable and ≥ 2× resting; every state stays text-safe (p95 ΔL ≤ 0.20)', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS) {
      const rest = lightnessStats(field(root, ground, 'resting'), ground).mean
      const need = lightnessStats(field(root, ground, 'needs_you'), ground)
      const where = `${ground}/${root}`
      assert.ok(need.mean >= 0.06, `${where}: needs_you mean ΔL ${need.mean.toFixed(4)} < 0.06`)
      assert.ok(need.mean >= 2 * rest, `${where}: needs_you ${need.mean.toFixed(4)} < 2 × resting ${rest.toFixed(4)}`)
      for (const p of PRESETS) {
        const st = lightnessStats(field(root, ground, p), ground)
        assert.ok(st.p95 <= 0.2, `${where}: ${p} p95 ΔL ${st.p95.toFixed(4)} > 0.20`)
        assert.ok(st.mean >= 0.012, `${where}: ${p} mean ΔL ${st.mean.toFixed(4)} — invisible`)
      }
    }
  }
})

test('O2.4 hue = identity: no state moves an organ\'s hue off the session hue (±10°); blanch is achromatic', () => {
  for (const root of ROOTS) {
    const h = hueFor(root)
    for (const ground of GROUNDS) {
      for (const p of PRESETS) {
        const organs = field(root, ground, p).filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0)
        if (p === 'error') {
          assert.ok(meanChroma(organs) <= 0.03, `${root}: error must blanch (chroma ${meanChroma(organs)})`)
          continue
        }
        assert.ok(meanChroma(organs) >= 0.04, `${root}/${p}: chroma ${meanChroma(organs).toFixed(3)} too low to carry identity`)
        const worst = Math.max(...organs.map(d => hueDistance(lchOf(d.color).h, h)))
        assert.ok(worst <= 10, `${root}/${p}@${ground}: organ hue ${worst.toFixed(1)}° off the identity hue ${h}`)
      }
    }
  }
})

test('O2.5 identities: hues stay in [110°, 340°) (never amber/red) and 20 live sessions get 20 distinct hues', () => {
  const held: number[] = []
  const hues: number[] = []
  for (const root of ROOTS) {
    const a = D().allocate(root, held)
    assert.ok(a.hue_deg >= 110 && a.hue_deg < 340, `${root}: hue ${a.hue_deg} outside [110, 340)`)
    assert.equal(a.crowded, false)
    held.push(a.slot)
    hues.push(a.hue_deg)
  }
  assert.equal(new Set(held).size, 20, 'slots collide')
  const two = [D().allocate(ROOTS[0], []), D().allocate(ROOTS[1], [D().allocate(ROOTS[0], []).slot])]
  assert.ok(hueDistance(two[0].hue_deg, two[1].hue_deg) >= 30, 'two live sessions must be told apart by hue (≥ 30°)')
  assert.equal(D().allocate(ROOTS[3], []).slot, D().allocate(ROOTS[3], []).slot, 'deterministic')
  assert.throws(() => D().allocate('', []), 'an empty lineage root is refused, never guessed')
})

test('O2.6 organs are fixed: state, time and bloom never move one; different sessions get different layouts', () => {
  for (const root of ROOTS.slice(0, 6)) {
    const g = GROUNDS[0]
    const key = organKey(field(root, g, 'resting'))
    for (const p of PRESETS) {
      for (const tMs of [0, 1700, 9000]) {
        for (const sinceChangeMs of [0, 400, SETTLED_MS]) {
          assert.equal(organKey(field(root, g, p, { tMs, sinceChangeMs })), key, `${root}/${p} t=${tMs} moved an organ`)
        }
      }
    }
  }
  assert.notEqual(organKey(field(ROOTS[0], GROUNDS[0], 'resting')), organKey(field(ROOTS[1], GROUNDS[0], 'resting')))
  assert.deepEqual(field(ROOTS[2], GROUNDS[1], 'working', { tMs: 1234 }), field(ROOTS[2], GROUNDS[1], 'working', { tMs: 1234 }),
    'a render is a pure function of its input')
})

test('O2.7 a change blooms, then settles (still); motion off and reduced motion never bloom', () => {
  for (const root of ROOTS.slice(0, 8)) {
    for (const ground of GROUNDS) {
      for (const p of ['needs_you', 'error', 'finished_unseen'] as const) {
        const at = (sinceChangeMs: number, over: Record<string, unknown> = {}) =>
          lightnessStats(field(root, ground, p, { sinceChangeMs, ...over }), ground).mean
        const peak = Math.max(at(150), at(400), at(800))
        const settled = at(SETTLED_MS)
        assert.ok(peak >= 1.5 * settled, `${root}/${p}@${ground}: bloom peak ${peak.toFixed(4)} < 1.5 × settled ${settled.toFixed(4)}`)
        assert.ok(Math.abs(at(9000) - settled) <= 0.02 * settled + 1e-9, `${root}/${p}: not settled after ${SETTLED_MS} ms`)
        for (const quiet of [{ motion: 'off' }, { reducedMotion: true }]) {
          assert.ok(Math.abs(at(150, quiet) - at(SETTLED_MS, quiet)) <= 1e-9, `${root}/${p} ${JSON.stringify(quiet)} bloomed`)
        }
      }
    }
  }
  assert.ok(D().BLOOM_MS >= 800 && D().BLOOM_MS <= 4000, `BLOOM_MS ${D().BLOOM_MS} is not "a few seconds"`)
})

test('O2.8 intensity scales loudness monotonically; 0 switches the field off', () => {
  for (const root of ROOTS.slice(0, 5)) {
    const g = GROUNDS[0]
    const m = (intensity: number) => lightnessStats(field(root, g, 'needs_you', { intensity }), g).mean
    assert.ok(m(0) === 0, `intensity 0 still draws (${m(0)})`)
    assert.ok(m(0.5) < m(1) && m(1) < m(2), `not monotonic: ${m(0.5)} ${m(1)} ${m(2)}`)
    const rest2 = lightnessStats(field(root, g, 'resting', { intensity: 2 }), g)
    assert.ok(rest2.p95 <= 0.1, `intensity 2 resting p95 ${rest2.p95} > 0.10 (the dial must stay bounded)`)
  }
})

test('O2.9 the swatch and the strip speak the same language at their own scale', () => {
  const s = D().DEFAULT_SETTINGS
  for (const which of ['renderSwatch', 'renderStrip'] as const) {
    for (const root of ROOTS.slice(0, 10)) {
      for (const ground of GROUNDS) {
        const ink = new Map<string, number[]>()
        for (const p of PRESETS) {
          const out = D()[which]({ seed: root, hueDeg: hueFor(root), ground, pattern: D().patternOf(s, p), intensity: 1 })
          const maxW = which === 'renderSwatch' ? 28 : 64
          assert.ok(out.width <= maxW && out.height <= 16, `${which} ${out.width}×${out.height} too big`)
          for (const d of out.dots) {
            assert.ok(d.x - d.r >= -0.5 && d.x + d.r <= out.width + 0.5 && d.y - d.r >= -0.5 && d.y + d.r <= out.height + 0.5,
              `${which} dot leaves its box`)
          }
          const lit = lightnessStats(out.dots, ground)
          assert.ok(lit.mean >= 0.08, `${which}/${p}@${ground}: mean ΔL ${lit.mean.toFixed(3)} — a row swatch must be visible`)
          if (p === 'error') assert.ok(meanChroma(out.dots) <= 0.03, `${which} error must blanch`)
          else {
            const organs = out.dots.filter((d: Dot) => d.role === 'organ' && d.alpha > 0)
            const worst = Math.max(...organs.map((d: Dot) => hueDistance(lchOf(d.color).h, hueFor(root))))
            assert.ok(worst <= 10, `${which}/${p}: hue drift ${worst}`)
          }
          if (p === 'finished_unseen') assert.ok(spotRatios(out.dots).first >= 2, `${which} eye-spot missing`)
          // ink per organ slot in a canonical order: comparable across presets because organs never move
          ink.set(p, [...out.dots].sort((a: Dot, b: Dot) => a.x - b.x || a.y - b.y).map((d: Dot) => dotDeltaL(d, ground) * d.r * d.r))
        }
        for (let i = 0; i < PRESETS.length; i++) {
          for (let j = i + 1; j < PRESETS.length; j++) {
            const a = ink.get(PRESETS[i])!, b = ink.get(PRESETS[j])!
            const n = Math.max(a.length, b.length)
            let diff = 0, tot = 0
            for (let k = 0; k < n; k++) { diff += Math.abs((a[k] ?? 0) - (b[k] ?? 0)); tot += Math.max(a[k] ?? 0, b[k] ?? 0) }
            assert.ok(diff >= 0.2 * tot, `${which} ${PRESETS[i]} vs ${PRESETS[j]} @${ground}/${root}: only ${(100 * diff / tot).toFixed(1)}% different`)
          }
        }
      }
    }
  }
})

test('O2.10 toSvg is a faithful, inert rendering of the dots', () => {
  const dots = field(ROOTS[4], GROUNDS[0], 'needs_you')
  const svg: string = D().toSvg(dots, W, H)
  assert.match(svg, /^<svg[^>]*\bwidth="1200"[^>]*\bheight="800"/)
  assert.doesNotMatch(svg, /<script|href=|on\w+=|url\(/i, 'an SVG background must be inert')
  const circles = [...svg.matchAll(/<circle\b[^>]*>/g)].map(m => m[0])
  const visible = dots.filter(d => d.alpha > 0 && d.r > 0)
  assert.equal(circles.length, visible.length)
  const attr = (c: string, k: string) => Number(new RegExp(`\\b${k}="([-0-9.]+)"`).exec(c)?.[1])
  for (const c of circles.slice(0, 50)) {
    const cx = attr(c, 'cx'), cy = attr(c, 'cy')
    const d = visible.find(v => Math.abs(v.x - cx) < 0.01 && Math.abs(v.y - cy) < 0.01)
    assert.ok(d, `circle ${c} matches no dot`)
    assert.ok(Math.abs(attr(c, 'r') - d!.r) < 0.01)
    assert.ok(c.toLowerCase().includes(d!.color.toLowerCase()), `fill of ${c} is not ${d!.color}`)
    const op = /\b(?:fill-)?opacity="([0-9.]+)"/.exec(c)?.[1]
    assert.ok(Math.abs(Number(op ?? 1) - d!.alpha) < 1e-3, `opacity of ${c} is not ${d!.alpha}`)
  }
})
