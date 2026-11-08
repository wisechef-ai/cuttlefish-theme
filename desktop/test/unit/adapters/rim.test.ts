// Unit: the composer rim's nodes — one clean thin band per state, never grain.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { PATTERN_KINDS, type PatternKind } from '../../../src/domain/types.ts'
import { rimElement, rimNodes, rimSvg, type RimNode } from '../../../src/adapters/rim.ts'

const input = (base: PatternKind, over = {}) => ({ base, hueDeg: 200, ground: '#fefefe', intensity: 1, height: 6, ...over })
const flat = (ns: RimNode[]): RimNode[] => ns.flatMap(n => [n, ...flat(n.children ?? [])])

test('the five states are five different bands; each is a handful of nodes, never a texture', () => {
  const sigs = PATTERN_KINDS.map(b => JSON.stringify(rimNodes(input(b))))
  assert.equal(new Set(sigs).size, 5)
  for (const b of PATTERN_KINDS) assert.ok(flat(rimNodes(input(b))).length <= 100, `${b} is a few shapes (the cloud is 14 banks x 6 puffs)`)
})

test('what each band is: hairline, banks of cloud puffs, diagonal stripes, broad pale dashes, hairline + one dark spot', () => {
  const tags = (b: PatternKind) => flat(rimNodes(input(b))).map(n => n.tag).join(',')
  assert.equal(tags('mottle'), 'rect')
  const banks = rimNodes(input('clouds'))
  assert.equal(banks.length, 14, 'fourteen banks')
  assert.ok(banks.every(n => n.tag === 'svg' && n.children?.length === 6 && n.children.every(c => c.tag === 'circle')), 'of six overlapping puffs — the sidebar cloud, in a row')
  assert.ok(banks.every(n => n.children!.every(c => Number(c.attrs.r) >= 2.2)), 'full-height puffs, bold not slivers')
  assert.equal(tags('zebra'), 'defs,pattern,rect,rect')
  assert.equal(tags('blanch'), 'defs,pattern,rect,rect')
  assert.equal(tags('eyespot'), 'rect,circle')
  const stripes = flat(rimNodes(input('zebra'))).find(n => n.tag === 'pattern')!
  assert.match(String(stripes.attrs.patternTransform), /skewX/, 'stripes are slanted')
  const dashes = flat(rimNodes(input('blanch'))).find(n => n.tag === 'pattern')!
  assert.equal(dashes.attrs.width, 30, 'broad dashes with gaps')
  const dash = dashes.children![0]
  assert.ok(Number(dash.attrs.width) >= 18 && Number(dash.attrs.rx) > 0, 'wide, rounded')
  assert.equal(dash.attrs.opacity !== 0, true)
})

test('hue is identity: the chromatic bands carry the session pigment, error the near-achromatic one', () => {
  const fill = (b: PatternKind, hue: number) => String(flat(rimNodes(input(b, { hueDeg: hue }))).find(n => n.attrs.fill && !String(n.attrs.fill).startsWith('url'))!.attrs.fill)
  assert.notEqual(fill('mottle', 140), fill('mottle', 280))
  const [r, g, b] = [1, 3, 5].map(i => parseInt(fill('blanch', 200).slice(i, i + 2), 16))
  assert.ok(Math.max(r, g, b) - Math.min(r, g, b) < 24, 'pale, near-grey')
})

test('intensity 0 switches the band off; an unknown base is the hairline; garbage never throws', () => {
  for (const n of flat(rimNodes(input('clouds', { intensity: 0 }))).filter(n => n.tag === 'circle')) assert.equal(n.attrs.opacity, 0)
  assert.deepEqual(rimNodes(input('nonsense' as PatternKind)), rimNodes(input('mottle')))
})

test('rimElement builds the svg through the host jsx; rimSvg writes the same band as text', () => {
  const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
  const el = rimElement(jsx, input('zebra')) as { type: string; props: { width: string; height: number; children: unknown[] } }
  assert.equal(el.type, 'svg')
  assert.equal(el.props.width, '100%')
  assert.equal(el.props.height, 6)
  assert.equal(el.props.children.length, 2)
  const text = rimSvg({ ...input('clouds'), width: 1000 })
  assert.match(text, /^<svg width="1000" height="6">/)
  assert.equal((text.match(/<circle /g) ?? []).length, 84)
  assert.match(text, /<svg x="20"/, 'percentages resolve against the width')
})
