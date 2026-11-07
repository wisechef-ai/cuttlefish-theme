// Unit contract of the SVG element builder (adapters lane): the swatch draws EXACTLY the
// domain's dots — every visible dot, raw numbers, lowercase hex, alpha as opacity — the
// property oA_part4 compares against its oracle.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { allocate, patternOf, renderSwatch, resolveSettings } from '../../../src/domain/index.ts'
import { dotElements, svgElement, type Jsx } from '../../../src/adapters/svg.ts'

const raw = {
  states: { compacting_seen: { when: 'compacting', pattern: 'ripple', priority: 70, label: 'tidying up' } },
  patterns: { ripple: { base: 'clouds', density: 2, contrast: 1.5, scale: 1 } },
}

test('svg: every visible dot becomes a circle with the oracle\'s exact numbers', () => {
  const settings = resolveSettings(raw).settings
  const out = renderSwatch({ seed: 'SA', hueDeg: allocate('SA', []).hue_deg, ground: '#141416',
    pattern: patternOf(settings, 'compacting_seen'), intensity: settings.intensity })
  const made: { type: string; props: Record<string, unknown> }[] = []
  const jsx: Jsx = (type, props) => { made.push({ type: String(type), props }); return made.at(-1) }
  const els = dotElements(jsx, out.dots)
  const visible = out.dots.filter(d => d.alpha > 0 && d.r > 0)
  assert.equal(els.length, visible.length)
  assert.equal(made.filter(m => m.type === 'circle').length, visible.length, 'no dropped, no duplicated circles')
  made.forEach((m, i) => {
    assert.equal(m.props.cx, visible[i].x, 'cx is the raw number, never rounded')
    assert.equal(m.props.cy, visible[i].y)
    assert.equal(m.props.r, visible[i].r)
    assert.equal(m.props.fill, visible[i].color)
    assert.equal(m.props.opacity, visible[i].alpha)
  })
})

test('svg: zero-ink dots are skipped, not drawn hollow; a hairline dot still draws', () => {
  const made: unknown[] = []
  const jsx: Jsx = (type, props) => { made.push([type, props]); return made.at(-1) }
  const dots = [
    { x: 1, y: 2, r: 3, color: '#aabbcc', alpha: 0.5 },
    { x: 1, y: 2, r: 3, color: '#aabbcc', alpha: 0 },
    { x: 1, y: 2, r: 0, color: '#aabbcc', alpha: 0.5 },
    { x: 5, y: 6, r: 0.5, color: '#aabbcc', alpha: 0.5 },
  ]
  const els = dotElements(jsx, dots)
  assert.equal(els.length, 2)
  const hairline = made.at(-1) as [string, Record<string, unknown>]
  assert.equal(hairline[1].r, 0.5, 'the ink threshold is r > 0 and alpha > 0, nothing higher')
})

test('svg: the root carries the surface attributes and the viewBox', () => {
  const made: { type: string; props: Record<string, unknown> }[] = []
  const jsx: Jsx = (type, props) => { made.push({ type: String(type), props }); return made.at(-1) }
  const root = svgElement(jsx, { width: 24, height: 12 }, { 'data-cf-session': 'SA', 'data-cf-state': 'resting' },
    [{ x: 1, y: 2, r: 3, color: '#aabbcc', alpha: 0.5 }]) as { type: string; props: Record<string, unknown> }
  assert.equal(root.type, 'svg')
  assert.equal(root.props['data-cf-session'], 'SA')
  assert.equal(root.props['data-cf-state'], 'resting')
  assert.equal(root.props.viewBox, '0 0 24 12')
  assert.equal(root.props.width, 24)
  assert.ok(Array.isArray(root.props.children) && root.props.children.length === 1)
})
