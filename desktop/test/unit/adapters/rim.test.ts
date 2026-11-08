// Unit: the composer rim (v2.1 §3) — ONE system: every state is the same 10 px pill; the state changes only what fills
// it and how its outline is drawn, echoing its mark.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { palette } from '../../../src/domain/ink.ts'
import { PATTERN_KINDS, type PatternKind } from '../../../src/domain/types.ts'
import { rimElement, rimNodes, rimSvg, RIM_HEIGHT, type RimNode } from '../../../src/adapters/rim.ts'

const input = (base: PatternKind, over = {}) => ({ base, hueDeg: 200, ground: '#fefefe', intensity: 1, height: RIM_HEIGHT, ...over })
const flat = (ns: RimNode[]): RimNode[] => ns.flatMap(n => [n, ...flat(n.children ?? [])])
/** The body: everything after the <defs> (the clip and any tiles). */
const body = (b: PatternKind, over = {}): RimNode[] => rimNodes(input(b, over)).filter(n => n.tag !== 'defs')
const pill = (b: PatternKind, over = {}): RimNode => body(b, over).find(n => n.tag === 'rect' && n.attrs.rx === 4.25)!

test('the rim is 10 px tall and every state draws the same pill (one system, not five bands)', () => {
  assert.equal(RIM_HEIGHT, 10)
  for (const b of PATTERN_KINDS) {
    const p = pill(b)
    assert.ok(p, `${b} draws the pill`)
    assert.deepEqual([p.attrs.x, p.attrs.y, p.attrs.height, p.attrs.rx], [0.75, 0.75, 8.5, 4.25], `${b}: the pill's placement and round caps`)
    const clip = flat(rimNodes(input(b))).find(n => n.tag === 'clipPath')!
    assert.equal(clip.attrs.id, 'cf-rim-cap', `${b}: the fill is clipped to the same pill`)
  }
  const sigs = PATTERN_KINDS.map(b => JSON.stringify(body(b)))
  assert.equal(new Set(sigs).size, 5, 'and the five markups differ')
})

test('what each state fills the pill with: hairline outline, cloud trains, diagonal stripes, pale wash in a broken frame, one eye', () => {
  assert.equal(body('mottle').length, 1, 'resting: the outline alone')
  assert.equal(pill('mottle')!.attrs.fill, 'none')
  const trains = flat(rimNodes(input('clouds'))).filter(n => n.tag === 'circle')
  assert.ok(trains.length >= 12, `clouds: lobe trains (${trains.length} circles)`)
  assert.ok(flat(body('clouds')).some(n => n.tag === 'rect' && String(n.attrs.fill).startsWith('url(')), 'clouds: a track filled with the trains')
  const stripes = flat(rimNodes(input('zebra'))).find(n => n.tag === 'pattern')!
  assert.equal(stripes.attrs.width, 12)
  assert.match(String(stripes.attrs.patternTransform), /skewX\(-45\)/, 'stripes are slanted')
  assert.equal(flat(rimNodes(input('zebra'))).find(n => n.tag === 'rect' && n.attrs.width === 6)?.attrs.width, 6, 'a stripe is six wide')
  const blanch = body('blanch')
  assert.ok(flat(blanch).some(n => n.tag === 'rect' && n.attrs['fill-opacity'] === 0.38), 'error: a pale wash')
  assert.ok(pill('blanch')!.attrs['stroke-dasharray'] !== undefined, 'and a broken outline')
  assert.equal(pill('blanch')!.attrs['stroke-width'], 3, 'a firmer frame')
  const eye = body('eyespot').filter(n => n.tag === 'circle')
  assert.deepEqual(eye.map(n => n.attrs.r), [3.9, 2.4], 'finished: an iris ring and one dark pupil')
  assert.equal(eye[1].attrs.fill, palette(200, '#fefefe').spot, 'the pupil is the spot pigment')
})

test('hue is identity: the bands carry the session pigment, error the near-achromatic one, the pupil the spot', () => {
  const stroke = (b: PatternKind, hue: number) => String(pill(b, { hueDeg: hue }).attrs.stroke)
  assert.notEqual(stroke('clouds', 140), stroke('clouds', 280))
  assert.equal(stroke('zebra', 200), palette(200, '#fefefe').chroma)
  const [r, g, b] = [1, 3, 5].map(i => parseInt(stroke('blanch', 200).slice(i, i + 2), 16))
  assert.ok(Math.max(r, g, b) - Math.min(r, g, b) < 24, 'pale, near-grey')
})

test('intensity 0 switches the band off; an unknown base is the calm outline; garbage never throws', () => {
  for (const n of body('clouds', { intensity: 0 })) assert.equal(n.attrs.opacity, 0)
  assert.deepEqual(rimNodes(input('nonsense' as PatternKind)), rimNodes(input('mottle')))
})

test('rimElement builds the svg through the host jsx; rimSvg writes the same band as text', () => {
  const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
  const el = rimElement(jsx, input('zebra')) as { type: string; props: { width: string; height: number; children: unknown[] } }
  assert.equal(el.type, 'svg')
  assert.equal(el.props.width, '100%')
  assert.equal(el.props.height, RIM_HEIGHT)
  const text = rimSvg({ ...input('clouds'), width: 1000 })
  assert.match(text, /^<svg width="1000" height="10">/)
  assert.match(text, /x="0.75"/, 'the pill is inset one pixel')
})
