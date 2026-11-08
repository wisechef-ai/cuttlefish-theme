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
  // §4c ruling 2 (changed from v2.1's .38 wash and 3 px double dash): one line, one break, lighter
  assert.ok(flat(blanch).some(n => n.tag === 'rect' && n.attrs['fill-opacity'] === 0.16), 'error: a pale wash')
  assert.ok(pill('blanch')!.attrs['stroke-dasharray'] !== undefined, 'and a broken outline')
  assert.equal(pill('blanch')!.attrs['stroke-width'], 1.6, 'one fine line')
  // §4c ruling 4 (changed from v2.1's ring): a lens, an iris and a pupil
  const eye = body('eyespot').filter(n => n.tag === 'circle')
  assert.deepEqual(eye.map(n => n.attrs.r), [2.6, 1.6], 'finished: an iris and one dark pupil')
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

// v2.1 round r4 (§4c, rulings 1–3): the rim as the r4 patch draws it. Written first; each fails on 08e7d74.
test('r4 needs you (ruling 1): a static warning band of two end chips, never a full-width marching stripe', () => {
  const nodes = flat(rimNodes(input('zebra')))
  const chips = nodes.filter(n => n.tag === 'rect' && n.attrs.width === 96)
  assert.equal(chips.length, 2, 'two chips of 96 px')
  assert.equal(chips.filter(n => n.attrs.transform === 'translate(-96 0)').length, 1, 'the right one is mirrored from the end')
  assert.equal(nodes.filter(n => n.tag === 'rect' && n.attrs.fill === 'url(#cf-rim-stripes)' && n.attrs.width === '100%').length, 0, 'no full-width stripe band')
  const ends = nodes.filter(n => n.tag === 'rect' && n.attrs.width === 1.5)
  assert.equal(ends.length, 2, 'a 1.5 px end bar at each chip')
  const json = JSON.stringify(rimNodes(input('zebra')))
  assert.doesNotMatch(json, /animate|keyframes|animation/, 'the warning band is static: no animation anywhere in the rim')
})

test('r4 working (ruling 3): miniature clouds, four nodes each (three lobes and a base), no lozenge', () => {
  const nodes = flat(rimNodes(input('clouds')))
  const circles = nodes.filter(n => n.tag === 'circle')
  const bases = nodes.filter(n => n.tag === 'rect' && n.attrs.rx === 1.5 && n.attrs.width === 13.4)
  assert.ok(circles.length >= 12 && circles.length % 3 === 0, `${circles.length} lobes`)
  assert.equal(bases.length, circles.length / 3, 'one flat base per cloud')
})

test('r4 error (ruling 2): one pale wash and ONE broken line, lighter than before', () => {
  const body = rimNodes(input('blanch')).filter(n => n.tag !== 'defs')
  const lines = flat(body).filter(n => n.attrs['stroke-dasharray'] !== undefined)
  assert.equal(lines.length, 1, 'one outline')
  assert.deepEqual([lines[0].attrs['stroke-dasharray'], lines[0].attrs['stroke-width'], lines[0].attrs.pathLength], ['975 25', 1.6, 1000], 'a single 25/1000 break')
  assert.equal(lines[0].attrs['stroke-dashoffset'], -80)
  assert.ok(flat(body).some(n => n.attrs['fill-opacity'] === 0.16), 'the wash is .16')
})

test('r4 finished (ruling 4): a lens-shaped eye, an iris ring and a pupil', () => {
  const body = rimNodes(input('eyespot')).filter(n => n.tag !== 'defs')
  const lens = flat(body).find(n => n.tag === 'path')!
  assert.match(String(lens.attrs.d), /Q/, 'the lens is a quadratic almond')
  const circles = flat(body).filter(n => n.tag === 'circle')
  assert.deepEqual(circles.map(n => n.attrs.r), [2.6, 1.6], 'iris and pupil')
})

// v2.1 round r5 (§4d rulings 2–4): the rims as the r5 patch draws them. Written first; each fails on 7049668.
test('r5 resting (ruling 4): ONE hairline in the soft ink, no pill, no second line', () => {
  const body = rimNodes(input('mottle')).filter(n => n.tag !== 'defs')
  assert.equal(body.length, 1, 'one node')
  assert.equal(body[0].tag, 'rect')
  assert.deepEqual([body[0].attrs.y, body[0].attrs.height], [9, 1], 'the bottom pixel row of the 10 px rim')
  assert.equal(body[0].attrs.fill, palette(200, '#fefefe').soft, 'in the soft ink')
  assert.equal(body[0].attrs.rx, undefined, 'no rounded pill')
})

test('r5 error (ruling 2): a broken border of four plain rects, one clear 56 px gap, no pill, no dash, no wash', () => {
  const body = flat(rimNodes(input('blanch')).filter(n => n.tag !== 'defs'))
  assert.equal(body.filter(n => n.tag === 'rect').length, 4, 'four rects')
  assert.ok(body.every(n => n.attrs.rx === undefined), 'no rounded ends')
  assert.equal(body.filter(n => n.attrs.transform === 'translate(56 0)').length, 1, 'exactly one gap, of 56 px')
  assert.ok(body.every(n => n.attrs['stroke-dasharray'] === undefined && n.attrs['fill-opacity'] === undefined), 'no dash and no wash')
  assert.ok(body.some(n => n.attrs.height === 1.2 && n.attrs.width === '62%'), 'the top edge runs in two parts')
})

test('r5 working (ruling 3): a clean 1.2 px outline, a faint tint, and five spaced clouds in a 20 % tile', () => {
  const nodes = rimNodes(input('clouds'))
  const tile = flat(nodes).find(n => n.tag === 'pattern')!
  assert.equal(tile.attrs.width, 0.2)
  assert.equal(tile.attrs.patternUnits, 'objectBoundingBox')
  const group = flat(nodes).find(n => n.tag === 'g')!
  assert.equal(group.attrs.opacity, 0.55, 'the lobes share one group opacity')
  assert.equal(group.children!.filter(n => n.tag === 'circle').length, 3, 'three lobes')
  assert.equal(group.children!.filter(n => n.tag === 'rect').length, 1, 'and a base')
  assert.ok(flat(nodes).some(n => n.tag === 'rect' && n.attrs['fill-opacity'] === 0.08), 'a faint tint')
  const pillNode = flat(nodes).find(n => n.tag === 'rect' && n.attrs.rx === 4.25)!
  assert.equal(pillNode.attrs['stroke-width'], 1.2, 'a 1.2 px outline')
})
