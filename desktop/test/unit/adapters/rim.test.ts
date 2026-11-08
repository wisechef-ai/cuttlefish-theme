// Unit: the composer rim's nodes — one clean thin band per state, never grain.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { PATTERN_KINDS, type PatternKind } from '../../../src/domain/types.ts'
import { rimElement, rimNodes, rimSvg, type RimNode } from '../../../src/adapters/rim.ts'

const input = (base: PatternKind, over = {}) => ({ base, hueDeg: 200, ground: '#fefefe', intensity: 1, height: 5, ...over })
const flat = (ns: RimNode[]): RimNode[] => ns.flatMap(n => [n, ...flat(n.children ?? [])])

test('the five states are five different bands; each is a handful of nodes, never a texture', () => {
  const sigs = PATTERN_KINDS.map(b => JSON.stringify(rimNodes(input(b))))
  assert.equal(new Set(sigs).size, 5)
  for (const b of PATTERN_KINDS) assert.ok(flat(rimNodes(input(b))).length <= 6, `${b} is a few shapes`)
})

test('what each band is: hairline, cloud dashes, diagonal stripes, a flat pale wash, hairline + one dark spot', () => {
  const tags = (b: PatternKind) => flat(rimNodes(input(b))).map(n => n.tag).join(',')
  assert.equal(tags('mottle'), 'rect')
  assert.equal(tags('clouds'), 'rect,rect,rect')
  assert.ok(rimNodes(input('clouds')).every(n => Number(n.attrs.rx) > 0), 'cloud dashes are rounded')
  assert.equal(tags('zebra'), 'defs,pattern,rect,rect')
  assert.equal(tags('blanch'), 'rect')
  assert.equal(tags('eyespot'), 'rect,circle')
  const stripes = flat(rimNodes(input('zebra'))).find(n => n.tag === 'pattern')!
  assert.match(String(stripes.attrs.patternTransform), /skewX/, 'stripes are slanted')
  const wash = rimNodes(input('blanch'))[0]
  assert.equal(wash.attrs.width, '100%')
})

test('hue is identity: the chromatic bands carry the session pigment, error the near-achromatic one', () => {
  const fill = (b: PatternKind, hue: number) => String(flat(rimNodes(input(b, { hueDeg: hue })))[0].attrs.fill)
  assert.notEqual(fill('mottle', 140), fill('mottle', 280))
  const [r, g, b] = [1, 3, 5].map(i => parseInt(fill('blanch', 200).slice(i, i + 2), 16))
  assert.ok(Math.max(r, g, b) - Math.min(r, g, b) < 24, 'pale, near-grey')
})

test('intensity 0 switches the band off; an unknown base is the hairline; garbage never throws', () => {
  for (const n of flat(rimNodes(input('clouds', { intensity: 0 })))) assert.equal(n.attrs.opacity, 0)
  assert.deepEqual(rimNodes(input('nonsense' as PatternKind)), rimNodes(input('mottle')))
})

test('rimElement builds the svg through the host jsx; rimSvg writes the same band as text', () => {
  const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
  const el = rimElement(jsx, input('zebra')) as { type: string; props: { width: string; height: number; children: unknown[] } }
  assert.equal(el.type, 'svg')
  assert.equal(el.props.width, '100%')
  assert.equal(el.props.height, 5)
  assert.equal(el.props.children.length, 2)
  const text = rimSvg({ ...input('clouds'), width: 1000 })
  assert.match(text, /^<svg width="1000" height="5">/)
  assert.equal((text.match(/<rect /g) ?? []).length, 3)
  assert.match(text, /x="50"/, 'percentages resolve against the width')
})
