// ACCEPTANCE CONTRACT — proof that the measuring instruments are straight (locked).
// Reference values are PUBLISHED numbers or constructed distributions, never an implementation's output.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  banding, bandSpectrum, composite, coverage, type Dot, dotDeltaL, hexToRgb, hueDistance, lchOf, lightnessStats,
  median, organKey, percentile, rgbToOklab, spotRatios,
} from './instruments.ts'

const close = (a: number, b: number, eps: number, what: string) =>
  assert.ok(Math.abs(a - b) <= eps, `${what}: ${a} vs ${b} (±${eps})`)

test('OKLab matches Ottosson 2020 reference values', () => {
  // https://bottosson.github.io/posts/oklab/ (table "sRGB → OKLab")
  const ref: [string, number, number, number][] = [
    ['#ffffff', 1.0, 0.0, 0.0],
    ['#000000', 0.0, 0.0, 0.0],
    ['#ff0000', 0.62796, 0.22486, 0.12585],
    ['#00ff00', 0.86644, -0.23389, 0.1795],
    ['#0000ff', 0.45201, -0.03246, -0.31153],
  ]
  for (const [hex, L, a, b] of ref) {
    const lab = rgbToOklab(hexToRgb(hex))
    close(lab.L, L, 2e-4, `${hex} L`)
    close(lab.a, a, 2e-4, `${hex} a`)
    close(lab.b, b, 2e-4, `${hex} b`)
  }
})

test('mid grey is perceptually ~0.6 L, not 0.5 (the sRGB transfer curve is applied)', () => {
  close(lchOf('#808080').L, 0.5999, 5e-4, '#808080 L')
})

test('hexToRgb rejects malformed colours', () => {
  for (const bad of ['fff', '#fff', '#gggggg', 'rgb(1,2,3)', '']) assert.throws(() => hexToRgb(bad))
})

test('nearest-rank percentile (Wikipedia worked example)', () => {
  const xs = [15, 20, 35, 40, 50]
  assert.equal(percentile(xs, 30), 20)
  assert.equal(percentile(xs, 40), 20)
  assert.equal(percentile(xs, 50), 35)
  assert.equal(percentile(xs, 100), 50)
  assert.equal(median([3, 1, 2, 10]), 2.5)
  assert.throws(() => percentile([], 50))
})

test('compositing and |ΔL|', () => {
  const c = composite({ r: 255, g: 255, b: 255 }, 0.5, { r: 0, g: 0, b: 0 })
  assert.deepEqual(c, { r: 127.5, g: 127.5, b: 127.5 })
  const opaque: Dot = { x: 0, y: 0, r: 1, color: '#ffffff', alpha: 1, role: 'organ' }
  close(dotDeltaL(opaque, '#000000'), 1, 1e-4, 'white on black')
  close(dotDeltaL({ ...opaque, alpha: 0 }, '#000000'), 0, 1e-12, 'transparent')
})

test('hue distance wraps', () => {
  assert.equal(hueDistance(350, 10), 20)
  assert.equal(hueDistance(10, 350), 20)
  assert.equal(hueDistance(90, 270), 180)
})

// A synthetic field on a 1200x800 grid, 24 px pitch, ink modulated by a chosen profile.
function grid(ink: (x: number, y: number) => number, ground = '#000000'): Dot[] {
  const dots: Dot[] = []
  for (let y = 12; y < 800; y += 24) {
    for (let x = 12; x < 1200; x += 24) dots.push({ x, y, r: 3, color: '#ffffff', alpha: ink(x, y), role: 'organ' })
  }
  void ground
  return dots
}

test('band spectrum: a uniform field has no banding', () => {
  const s = bandSpectrum(grid(() => 0.2), '#000000', 1200, 800, 0)
  for (const a of s) assert.ok(a < 1e-9, `flat field leaked ${a}`)
})

test('band spectrum: three vertical stripes land in A_3 (highK), at angle 0', () => {
  const dots = grid(x => (Math.floor((x / 1200) * 6) % 2 === 0 ? 0.6 : 0.05))
  const b = banding(dots, '#000000', 1200, 800)
  assert.equal(b.angle, 0)
  // square wave of ink ΔL(0.6 white on black) / ΔL(0.05): amplitude/mean ≈ 0.70, × bin sinc ≈ 0.66–0.76
  assert.ok(b.highK >= 0.6 && b.highK <= 1.0, `highK ${b.highK}`)
  assert.ok(b.highK > 2 * b.lowK, `stripes must dominate high k: low ${b.lowK} high ${b.highK}`)
})

test('band spectrum: one smooth horizontal band lands in lowK, at angle 90', () => {
  const dots = grid((_, y) => 0.1 + 0.5 * Math.exp(-(((y - 400) / 100) ** 2)))
  const b = banding(dots, '#000000', 1200, 800)
  assert.equal(b.angle, 90)
  assert.ok(b.lowK > 0.5, `lowK ${b.lowK}`)
  assert.ok(b.highK < 0.6 * b.lowK, `a smooth band must not read as stripes: low ${b.lowK} high ${b.highK}`)
})

test('spot ratios find exactly one outlier', () => {
  const dots = grid(() => 0.3)
  dots.push({ x: 600, y: 400, r: 18, color: '#ffffff', alpha: 0.5, role: 'eyespot' })
  const s = spotRatios(dots)
  assert.equal(s.first, 6)
  assert.equal(s.second, 1)
})

test('coverage, lightness stats, organ key', () => {
  const dots = grid(() => 1)
  close(coverage(dots, 1200, 800), (dots.length * Math.PI * 9) / (1200 * 800), 1e-12, 'coverage')
  const st = lightnessStats(dots, '#000000')
  close(st.mean, 1, 1e-4, 'mean ΔL')
  assert.equal(st.n, dots.length)
  const moved = dots.map(d => ({ ...d, alpha: 0.1 }))
  assert.equal(organKey(moved), organKey(dots), 'alpha changes do not move organs')
  assert.notEqual(organKey([{ ...dots[0], x: 13 }, ...dots.slice(1)]), organKey(dots))
})
