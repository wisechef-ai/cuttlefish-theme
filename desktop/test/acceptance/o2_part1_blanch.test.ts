// ACCEPTANCE CONTRACT PART 1 — O2: "error" must be PALE, and toSvg must be faithful for EVERY circle (closes luna F2-pale, F5).
// Locked O2.4 only bounds the error preset's chroma (≤ 0.03): a DARK achromatic error passes it, which is not
// "blanching to pale" (SPEC C8). Locked O2.10 compares `circles.slice(0, 50)` only. Both holes are closed here.
//
// PALE (binding, per root × ground over the corpus), measured on the dots as they APPEAR on the ground:
//   mean OKLab L of the error organs  ≥  mean OKLab L of the SAME session's resting organs + 0.01
//   mean organ chroma (pigment)       ≤  0.03          (as O2.4)
//   mean ΔL on the ground             ≥  0.012         (as O2.3: still visible)
// On a dark ground this means the error organs are lighter than the resting ones; on the light ground (#fbfbfa) it means
// they sit between the resting organs and the ground (darker than the ground, lighter than resting): the satisfiable band
// was measured on a scratch prototype before the lock (see contract/PARTS.md).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { GROUNDS, H, ROOTS, SETTLED_MS, W } from './corpus.ts'
import {
  composite, type Dot, hexToRgb, lightnessStats, mean, meanChroma, rgbToOklab,
} from './instruments.ts'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Domain = any
const loaded: { mod?: Domain; err?: unknown } = {}
try { loaded.mod = await import('../../src/domain/index.ts') } catch (e) { loaded.err = e }
const D = (): Domain => {
  if (!loaded.mod) throw new Error(`desktop/src/domain/index.ts did not load: ${String(loaded.err)}`)
  return loaded.mod
}

function field(root: string, ground: string, preset: string, over: Record<string, unknown> = {}): Dot[] {
  const s = D().DEFAULT_SETTINGS
  return D().renderField({
    seed: root, width: W, height: H, hueDeg: D().allocate(root, []).hue_deg, ground,
    pattern: D().patternOf(s, preset), intensity: 1, motion: 'still', reducedMotion: false,
    tMs: 0, sinceChangeMs: SETTLED_MS, ...over,
  })
}

const organs = (dots: readonly Dot[]): Dot[] => dots.filter(d => d.role === 'organ' && d.alpha > 0 && d.r > 0)

/** OKLab L of each organ as it appears on the ground (source-over in sRGB, as the browser draws it). */
const appearL = (dots: readonly Dot[], ground: string): number =>
  mean(organs(dots).map(d => rgbToOklab(composite(hexToRgb(d.color), d.alpha, hexToRgb(ground))).L))

const PALE_MARGIN = 0.01

test('P2.1 error is PALE: lighter than the same session\'s resting organs by ≥ 0.01 L, achromatic, still visible (20 × 3)', () => {
  const bad: string[] = []
  for (const ground of GROUNDS) {
    for (const root of ROOTS) {
      const rest = field(root, ground, 'resting'), err = field(root, ground, 'error')
      assert.ok(organs(err).length >= 40, `${ground}/${root}: error draws only ${organs(err).length} organs`)
      const margin = appearL(err, ground) - appearL(rest, ground)
      const chroma = meanChroma(organs(err))
      const ink = lightnessStats(organs(err), ground).mean
      if (margin < PALE_MARGIN) bad.push(`${ground}/${root}: error L is only ${margin.toFixed(4)} above resting (need ≥ ${PALE_MARGIN})`)
      if (chroma > 0.03) bad.push(`${ground}/${root}: error chroma ${chroma.toFixed(3)} > 0.03`)
      if (ink < 0.012) bad.push(`${ground}/${root}: error mean ΔL ${ink.toFixed(4)} < 0.012 (blanched out of sight)`)
    }
  }
  assert.deepEqual(bad.slice(0, 10), [], `${bad.length} of 60 error renders are not pale`)
})

test('P2.2 pale is a property of the SETTLED pattern, not only of the bloom (long after the change)', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS.slice(0, 6)) {
      for (const sinceChangeMs of [SETTLED_MS, 3 * SETTLED_MS]) {
        const m = appearL(field(root, ground, 'error', { sinceChangeMs }), ground) - appearL(field(root, ground, 'resting', { sinceChangeMs }), ground)
        assert.ok(m >= PALE_MARGIN, `${ground}/${root} +${sinceChangeMs}ms: margin ${m.toFixed(4)}`)
      }
    }
  }
})

// ---- O2.10 in full: EVERY circle of a render matches exactly one dot (locked O2.10 only looks at the first 50) -------------

const attr = (c: string, k: string): number => Number(new RegExp(`\\b${k}="([-0-9.]+)"`).exec(c)?.[1])

/** Match every <circle> to a distinct visible dot (cx, cy, r, fill, opacity) and nothing is left over on either side. */
function compareAllCircles(svg: string, dots: readonly Dot[]): string[] {
  const circles = [...svg.matchAll(/<circle\b[^>]*>/g)].map(m => m[0])
  const free = dots.filter(d => d.alpha > 0 && d.r > 0)
  const problems: string[] = []
  if (circles.length !== free.length) problems.push(`${circles.length} circles for ${free.length} visible dots`)
  for (const c of circles) {
    const cx = attr(c, 'cx'), cy = attr(c, 'cy'), r = attr(c, 'r')
    const op = Number(/\b(?:fill-)?opacity="([0-9.]+)"/.exec(c)?.[1] ?? 1)
    const at = free.findIndex(d => Math.abs(d.x - cx) < 0.01 && Math.abs(d.y - cy) < 0.01 && Math.abs(d.r - r) < 0.01
      && Math.abs(d.alpha - op) < 1e-3 && c.toLowerCase().includes(d.color.toLowerCase()))
    if (at < 0) problems.push(`circle ${c} matches no remaining dot`)
    else free.splice(at, 1)
  }
  if (free.length) problems.push(`${free.length} visible dots are missing from the svg (first: ${JSON.stringify(free[0])})`)
  return problems
}

test('P2.3 toSvg draws every visible dot exactly once and nothing else (hand-built dots, incl. invisible ones)', () => {
  const dots: Dot[] = [
    { x: 10.5, y: 20.25, r: 4, color: '#3aa17e', alpha: 0.37, role: 'organ' },
    { x: 300, y: 99, r: 2.5, color: '#3AA17E', alpha: 1, role: 'organ' },
    { x: 301, y: 99, r: 2.5, color: '#112233', alpha: 0.5, role: 'eyespot' },
    { x: 50, y: 50, r: 3, color: '#ffffff', alpha: 0, role: 'organ' },       // invisible: no circle
    { x: 60, y: 60, r: 0, color: '#ffffff', alpha: 0.9, role: 'organ' },     // zero radius: no circle
    { x: 1199, y: 799.5, r: 7, color: '#fafafa', alpha: 0.05, role: 'organ' },
  ]
  const svg: string = D().toSvg(dots, W, H)
  assert.deepEqual(compareAllCircles(svg, dots), [])
})

test('P2.4 toSvg of REAL renders is faithful for every circle (all presets, all grounds, 3 identities)', () => {
  for (const ground of GROUNDS) {
    for (const root of ROOTS.slice(0, 3)) {
      for (const p of ['resting', 'working', 'needs_you', 'error', 'finished_unseen']) {
        const dots = field(root, ground, p)
        const problems = compareAllCircles(D().toSvg(dots, W, H), dots)
        assert.deepEqual(problems.slice(0, 3), [], `${p}@${ground}/${root}: ${problems.length} svg problems`)
      }
    }
  }
})

test('P2.5 the comparison itself rejects an altered svg (a dropped circle, a recoloured one, a moved one)', () => {
  const dots: Dot[] = Array.from({ length: 80 }, (_, i) => ({
    x: 10 + i * 13, y: 20 + (i % 7) * 31, r: 3 + (i % 4), color: '#40a0c0', alpha: 0.2 + (i % 5) / 10, role: 'organ' as const,
  }))
  // a LOCAL reference svg (this test proves the comparison, independent of the implementation)
  const svg = `<svg width="1200" height="800">${dots.map(d =>
    `<circle cx="${d.x}" cy="${d.y}" r="${d.r}" fill="${d.color}" fill-opacity="${d.alpha}"/>`).join('')}</svg>`
  assert.deepEqual(compareAllCircles(svg, dots), [])
  const circles = [...svg.matchAll(/<circle\b[^>]*>/g)].map(m => m[0])
  const last = circles[circles.length - 1]
  assert.notDeepEqual(compareAllCircles(svg.replace(last, ''), dots), [], 'a dropped circle past index 50 went unnoticed')
  assert.notDeepEqual(compareAllCircles(svg.replace(last, last.replace(/#40a0c0/i, '#c04040')), dots), [], 'a recoloured circle')
  assert.notDeepEqual(compareAllCircles(svg.replace(last, last.replace(/cx="[-0-9.]+"/, 'cx="5"')), dots), [], 'a moved circle')
})
