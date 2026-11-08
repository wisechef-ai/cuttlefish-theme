// Unit: the state glyphs (row swatch / strip) and the field's size language — what the eye reads at a glance.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { GLYPH_H, GLYPH_W, glyphOf } from '../../src/domain/glyph.ts'
import { constellation } from '../../src/domain/organs.ts'
import { radiusFactors, zebraBright } from '../../src/domain/pattern.ts'
import { allocate, DEFAULT_SETTINGS, patternOf, renderStrip, renderSwatch } from '../../src/domain/index.ts'
import { PATTERN_KINDS, type PatternKind } from '../../src/domain/types.ts'

test('every glyph fits its 24×12 box and has ink', () => {
  for (const base of PATTERN_KINDS) {
    const g = glyphOf(base)
    assert.ok(g.length >= 3, `${base} draws something`)
    for (const d of g) {
      assert.ok(d.x - d.r >= 0 && d.x + d.r <= GLYPH_W && d.y - d.r >= 0 && d.y + d.r <= GLYPH_H, `${base} dot leaves the box`)
      assert.ok(d.ink > 0 && d.ink <= 0.3, `${base} ink ${d.ink}`)
    }
  }
})

test('the five glyphs are five different pictures: dot counts and sizes tell the states apart', () => {
  const sig = (b: PatternKind): string => glyphOf(b).map(d => `${d.r.toFixed(1)}`).join(',')
  assert.equal(new Set(PATTERN_KINDS.map(sig)).size, 5)
  assert.equal(glyphOf('mottle').length, 3, 'resting: three soft dots')
  assert.equal(glyphOf('zebra').length, 12, 'needs you: three bars of four dots')
  assert.ok(glyphOf('blanch').every(d => d.pigment === 'blanch'), 'error is the pale pigment only')
  const eye = glyphOf('eyespot')
  assert.equal(eye.filter(d => d.pigment === 'spot').length, 1, 'finished unseen: exactly one eye-spot')
  assert.ok(Math.max(...eye.map(d => d.r)) >= 2.5 * Math.min(...eye.map(d => d.r)), 'and it dwarfs its halo')
})

test('an unknown pattern base degrades to the calm mottle, never a throw', () => {
  assert.equal(glyphOf('nonsense' as PatternKind), glyphOf('mottle'))
})

test('the swatch is the glyph in the session hue — the same shape for every session; the strip carries it twice', () => {
  const sw = (seed: string) => renderSwatch({ seed, hueDeg: allocate(seed, []).hue_deg, ground: '#fefefe', pattern: patternOf(DEFAULT_SETTINGS, 'needs_you'), intensity: 1 })
  const a = sw('s-one'), b = sw('s-two')
  assert.deepEqual(a.dots.map(d => [d.x, d.y, d.r]), b.dots.map(d => [d.x, d.y, d.r]), 'state is shape')
  assert.notDeepEqual(a.dots.map(d => d.color), b.dots.map(d => d.color), 'identity is hue')
  const strip = renderStrip({ seed: 's', hueDeg: 200, ground: '#fefefe', pattern: patternOf(DEFAULT_SETTINGS, 'needs_you'), intensity: 1 })
  assert.equal(strip.dots.length, 24)
  assert.ok(strip.dots.every(d => d.x - d.r >= 0 && d.x + d.r <= strip.width))
  const off = renderSwatch({ seed: 's', hueDeg: 200, ground: '#fefefe', pattern: patternOf(DEFAULT_SETTINGS, 'needs_you'), intensity: 0 })
  assert.ok(off.dots.every(d => d.alpha === 0), 'intensity 0 switches the glyph off')
})

test('field sizes: stripe organs swell in a band and shrink in the gap along 45° diagonals; error organs swell pale; the rest keep their size', () => {
  const cons = constellation('seed-x', 1340, 880, 190, 0.062, 0.098)
  const z = radiusFactors(patternOf(DEFAULT_SETTINGS, 'needs_you'), cons, 1340, 880)
  assert.deepEqual([...new Set(z)].sort(), [0.55, 3])
  cons.organs.forEach((o, i) => assert.equal(z[i] === 3, zebraBright(o, 1340, 880, 1)))
  // bands are diagonal: two organs on the same x+y diagonal always share a band
  const a = { ...cons.organs[0], x: 300, y: 100 }, b = { ...cons.organs[0], x: 100, y: 300 }
  assert.equal(zebraBright(a, 1340, 880, 1), zebraBright(b, 1340, 880, 1))
  assert.notEqual(zebraBright({ ...a, x: 0, y: 0 }, 1340, 880, 1), zebraBright({ ...a, x: 400, y: 0 }, 1340, 880, 1), 'and neighbouring diagonals alternate')
  const share = z.filter(f => f === 3).length / z.length
  assert.ok(share > 0.42 && share < 0.56, `half the organs are in a band (${share.toFixed(2)})`)
  assert.deepEqual([...new Set(radiusFactors(patternOf(DEFAULT_SETTINGS, 'error'), cons, 1340, 880))], [2.4])
  for (const s of ['resting', 'working', 'finished_unseen']) assert.deepEqual([...new Set(radiusFactors(patternOf(DEFAULT_SETTINGS, s), cons, 1340, 880))], [1])
})
