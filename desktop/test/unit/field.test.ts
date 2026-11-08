// Unit: the renderers — performance (the contract's < 5 ms/call budget), the inert SVG, the
// small canvases' bounds, and the pure-function guarantee.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import process from 'node:process'
import { GROUNDS, H, PRESETS, ROOTS, SETTLED_MS, W } from '../acceptance/corpus.ts'
import { coverage, type Dot, dotDeltaL, lightnessStats, organKey } from '../acceptance/instruments.ts'
import { allocate, DEFAULT_SETTINGS, patternOf, renderField, renderStrip, renderSwatch, toSvg } from '../../src/domain/index.ts'

const hueFor = (root: string): number => allocate(root, []).hue_deg

const inputOf = (root: string, ground: string, preset: string) => ({
  seed: root, width: W, height: H, hueDeg: hueFor(root), ground,
  pattern: patternOf(DEFAULT_SETTINGS, preset), intensity: 1,
  motion: 'still' as const, reducedMotion: false, tMs: 0, sinceChangeMs: SETTLED_MS,
})

test('renderField: 1200x800 well under 5 ms/call (best of 5, process.cpuUsage)', () => {
  const bestOf5 = (input: ReturnType<typeof inputOf>): number => {
    for (let i = 0; i < 3; i++) renderField(input)          // warm-up: JIT and the plan caches
    let best = Infinity
    for (let i = 0; i < 5; i++) {
      const t0 = process.cpuUsage()
      renderField(input)
      const d = process.cpuUsage(t0)
      best = Math.min(best, (d.user + d.system) / 1000)     // µs -> ms
    }
    return best
  }
  // A shared box schedules other work between our calls; cpu-time still inflates under
  // frequency scaling, so an overloaded machine can flake one best-of-5. Re-measure and
  // keep the global best — the claim under test is what the CPU can do, not the load.
  const bestOf5Stable = (input: ReturnType<typeof inputOf>): number => {
    let best = Infinity
    for (let attempt = 0; attempt < 3 && best >= 5; attempt++) best = bestOf5(input)
    return best
  }
  const best = bestOf5Stable(inputOf(ROOTS[0], GROUNDS[0], 'working'))
  assert.ok(best < 5, `best renderField ${best.toFixed(3)} ms is not "well under" 5 ms`)
  // a second identity on another ground (cold caches inside the same process) stays in budget too
  const cold = bestOf5Stable(inputOf(ROOTS[7], GROUNDS[2], 'needs_you'))
  assert.ok(cold < 5, `cold-identity renderField ${cold.toFixed(3)} ms`)
})

test('toSvg is inert, faithful and counts circles exactly', () => {
  const dots: Dot[] = renderField(inputOf(ROOTS[4], GROUNDS[0], 'needs_you'))
  const svg = toSvg(dots, W, H)
  assert.match(svg, /^<svg[^>]*\bwidth="1200"[^>]*\bheight="800"/)
  assert.doesNotMatch(svg, /<script|href=|on\w+=|url\(|javascript:/i)
  const circles = [...svg.matchAll(/<circle\b[^>]*>/g)].map(m => m[0])
  const visible = dots.filter(d => d.alpha > 0 && d.r > 0)
  assert.equal(circles.length, visible.length, 'one circle per visible dot, no more, no fewer')
  for (const c of circles) {
    assert.match(c, /cx="-?\d+(\.\d+)?"/)
    assert.match(c, /fill="#[0-9a-f]{6}"/i)
    assert.match(c, /opacity="(0(\.\d+)?|1)"/)
  }
})

test('the swatch and the strip stay inside their boxes, all presets, all grounds', () => {
  for (const which of [renderSwatch, renderStrip]) {
    const out = which({ seed: ROOTS[1], hueDeg: hueFor(ROOTS[1]), ground: GROUNDS[1], pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1 })
    for (const p of PRESETS) {
      const o = which({ seed: ROOTS[1], hueDeg: hueFor(ROOTS[1]), ground: GROUNDS[1], pattern: patternOf(DEFAULT_SETTINGS, p), intensity: 1 })
      for (const d of o.dots) {
        assert.ok(d.x - d.r >= -0.5 && d.x + d.r <= o.width + 0.5 && d.y - d.r >= -0.5 && d.y + d.r <= o.height + 0.5, `${p} dot leaves its box`)
      }
    }
    assert.ok(out.width <= 64 && out.height <= 16)
  }
})

test('intensity 0 draws nothing visible; intensity is a pure multiplier of loudness', () => {
  const off = renderField({ ...inputOf(ROOTS[2], GROUNDS[0], 'needs_you'), intensity: 0 })
  assert.equal(lightnessStats(off, GROUNDS[0]).mean, 0)
  const loud = (i: number): number => lightnessStats(renderField({ ...inputOf(ROOTS[2], GROUNDS[0], 'needs_you'), intensity: i }), GROUNDS[0]).mean
  assert.ok(loud(0.5) < loud(1) && loud(1) < loud(2))
})

test('renders under off/reduced are BIT-identical whatever sinceChangeMs (no hidden bloom)', () => {
  const base = inputOf(ROOTS[3], GROUNDS[0], 'error')
  for (const quiet of [{ motion: 'off' as const, reducedMotion: false }, { motion: 'still' as const, reducedMotion: true }]) {
    const a = renderField({ ...base, ...quiet, sinceChangeMs: 0 })
    const b = renderField({ ...base, ...quiet, sinceChangeMs: 150 })
    const c = renderField({ ...base, ...quiet, sinceChangeMs: 99999 })
    assert.deepEqual(a, b)
    assert.deepEqual(b, c)
  }
})

test('a render is a pure function of its input (deep-equal on a second call)', () => {
  const input = inputOf(ROOTS[5], GROUNDS[2], 'finished_unseen')
  assert.deepEqual(renderField(input), renderField(input))
})

// v2.1 §4 — the reading lane and the anchored eye-spot, over the locked corpus (20 roots × 3 grounds × 5 presets).
const SIZES = [[1339, 879], [1020, 680], [1200, 800]] as const
const laneOf = (w: number): number => Math.max(0.60, Math.min(0.70, 704 / w)) * w

test('eye-spot is anchored in the right gutter, the same for every session, dark on light and ≥ 4× the organs', () => {
  for (const root of ROOTS) for (const ground of GROUNDS) {
    const dots = renderField({ ...inputOf(root, ground, 'finished_unseen'), width: W, height: H })
    const eye = dots.filter(d => d.role === 'eyespot')
    assert.equal(eye.length, 1, `${root}: one eye-spot`)
    assert.ok(Math.abs(eye[0].x - 0.90 * W) < 1e-9 && Math.abs(eye[0].y - 0.30 * H) < 1e-9, `${root}: anchored at (0.90W, 0.30H)`)
    const organR = dots.filter(d => d.role === 'organ').map(d => d.r).sort((a, b) => a - b)
    assert.ok(eye[0].r >= 4 * organR[organR.length >> 1], `${root}: the eye is ${(eye[0].r / organR[organR.length >> 1]).toFixed(2)}× the median organ`)
    if (ground === GROUNDS[2]) assert.ok(dotDeltaL(eye[0], ground) >= 0.45, `${root}: dark on a light ground`)
  }
})

test('reading lane: no organ in the text, the cards or under the header; the field stays on every state, every phase', () => {
  for (const root of ROOTS) for (const [w, h] of SIZES) for (const preset of PRESETS) for (const ground of GROUNDS) {
    for (const tMs of [0, 9000]) {
      const dots = renderField({ ...inputOf(root, ground, preset), width: w, height: h, tMs, motion: 'alive', sinceChangeMs: 0 })
      for (const d of dots.filter(x => x.role === 'organ')) {
        assert.ok(d.x >= laneOf(w) - 1e-6, `${root} ${w}×${h} ${preset}: organ at x ${d.x.toFixed(1)} is left of the lane ${laneOf(w).toFixed(1)}`)
        assert.ok(d.y >= 64 - 1e-6 && d.y <= 0.88 * h + 1e-6, `${root} ${w}×${h} ${preset}: organ at y ${d.y.toFixed(1)} is outside [64, 0.88H]`)
      }
    }
  }
})

test('the lane keeps enough organs (≥ 40 visible) at every size, for resting and working', () => {
  for (const [w, h] of SIZES) for (const ground of GROUNDS) {
    const count = (preset: string) => renderField({ ...inputOf(ROOTS[2], ground, preset), width: w, height: h })
      .filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0).length
    assert.ok(count('resting') >= 40, `${w}×${h}: ${count('resting')} organs`)
    assert.ok(count('working') >= 40, `${w}×${h}: ${count('working')} organs`)
  }
})

test('error is FEWER organs at resting size: same positions, same radii, 35–45 % at zero ink, and coverage(error) ≤ coverage(resting) (§4b F-B, §6 #10)', () => {
  for (const root of ROOTS) for (const ground of GROUNDS) for (const [w, h] of [[1339, 879], [1200, 800]] as const) {
    const rest = renderField({ ...inputOf(root, ground, 'resting'), width: w, height: h })
    const err = renderField({ ...inputOf(root, ground, 'error'), width: w, height: h })
    assert.equal(organKey(err), organKey(rest), `${root}: error moves no organ`)
    const ro = rest.filter(d => d.role === 'organ'), eo = err.filter(d => d.role === 'organ')
    assert.deepEqual(eo.map(d => d.r), ro.map(d => d.r), `${root}: error radii are the resting radii`)
    const hidden = eo.filter(d => d.alpha === 0).length / eo.length
    assert.ok(hidden >= 0.35 && hidden <= 0.45, `${root}: ${(100 * hidden).toFixed(0)} % of the error organs are at zero ink`)
    assert.ok(eo.filter(d => d.alpha > 0).length >= 40, `${root}: at least 40 visible error organs`)
    assert.ok(coverage(err, w, h) <= coverage(rest, w, h), `${root} ${ground} ${w}×${h}: error ${coverage(err, w, h)} vs resting ${coverage(rest, w, h)}`)
  }
})
