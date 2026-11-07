// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT PART 4 — oA: the swatch of a USER-ADDED state is the domain's drawing of its configured pattern (closes luna-parts L3).
// Part 2 (oA_part2_added_state) proved the NAME, LABEL and root attribute reach the surfaces but never that the configured pattern is DRAWN: a
// swatch that ignores `patterns.ripple` and draws the default passed. Here the dots of the swatch in the shipped plugin must equal the domain
// oracle — `renderSwatch` from desktop/src/domain/index.ts called with the same resolved settings + seed — compared as canonical circles.
// Oracle inputs (binding): seed = the stored session id; hueDeg = allocate(seed, []).hue_deg (a single known session, so no peers); ground =
// the fake host's computed ground (#141416); intensity = settings.intensity; pattern = patternOf(settings, <state>). The swatch may draw its dots as
// <circle> elements, or as an inline/data-URI SVG string: both are read.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { boot, expand, fakeDocument, focus, LoopDriver, mountTitlebar, stripText, swatchRoot, walk } from './fake/part1_probe.mjs'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Domain = any
const loaded: { mod?: Domain; err?: unknown } = {}
try { loaded.mod = await import('../../src/domain/index.ts') } catch (e) { loaded.err = e }
const D = (): Domain => {
  if (!loaded.mod) throw new Error(`desktop/src/domain/index.ts did not load: ${String(loaded.err)}`)
  return loaded.mod
}

const GROUND = '#141416'
const RAW = {
  states: { compacting_seen: { when: 'compacting', pattern: 'ripple', priority: 70, label: 'tidying up' } },
  patterns: { ripple: { base: 'clouds', density: 2, contrast: 1.5, scale: 1 } },
}
const compacting = rt => ({ type: 'status.update', session_id: rt, payload: { kind: 'compacting' } })

// ---- reading circles out of whatever the swatch renders -------------------------------------------------------------------

const ATTR = (tag, k) => { const m = new RegExp(`\\b${k}=["']?([^"'\\s>/]+)`).exec(tag); return m ? m[1] : undefined }

/** Circles found in a string of SVG (raw, or URL-encoded inside a data URI). */
function circlesInText(text) {
  let t = text
  try { t = decodeURIComponent(text) } catch { /* keep raw */ }
  return [...t.matchAll(/<circle\b[^>]*>/gi)].map(m => ({
    cx: Number(ATTR(m[0], 'cx')), cy: Number(ATTR(m[0], 'cy')), r: Number(ATTR(m[0], 'r')),
    fill: String(ATTR(m[0], 'fill') ?? '').toLowerCase(), op: Number(ATTR(m[0], 'fill-opacity') ?? ATTR(m[0], 'opacity') ?? 1),
  }))
}

function swatchCircles(h, id) {
  const root = swatchRoot(h, id)
  const found = []
  for (const el of walk(expand(root).tree)) {
    if (el.type === 'circle') {
      const p = el.props
      found.push({ cx: Number(p.cx), cy: Number(p.cy), r: Number(p.r), fill: String(p.fill).toLowerCase(), op: Number(p['fill-opacity'] ?? p.fillOpacity ?? p.opacity ?? 1) })
    }
    for (const v of Object.values(el.props ?? {})) {
      if (typeof v === 'string') found.push(...circlesInText(v))
      else if (v && typeof v === 'object' && typeof v.__html === 'string') found.push(...circlesInText(v.__html))
    }
  }
  return found
}

const canon = cs => cs.map(c => `${c.cx.toFixed(2)},${c.cy.toFixed(2)},${c.r.toFixed(2)},${c.fill},${c.op.toFixed(3)}`).sort()

function oracle(raw, state, seed = 'SA') {
  const settings = D().resolveSettings(raw).settings
  const out = D().renderSwatch({ seed, hueDeg: D().allocate(seed, []).hue_deg, ground: GROUND, pattern: D().patternOf(settings, state), intensity: settings.intensity })
  return { settings, circles: out.dots.filter(d => d.alpha > 0 && d.r > 0).map(d => ({ cx: d.x, cy: d.y, r: d.r, fill: d.color.toLowerCase(), op: d.alpha })) }
}

async function ready(raw) {
  const b = await boot({ settings: raw })
  focus(b.sdk, 'a', 'SA')
  mountTitlebar(b.h)
  b.driver = new LoopDriver(b.sdk)
  await b.driver.run(b.h, 12_000)
  return b
}

test('P6.1 the circle reader and the canonical comparison tell patterns apart (needs the domain only)', () => {
  const a = oracle(RAW, 'compacting_seen').circles
  const b = oracle({ ...RAW, states: { compacting_seen: { ...RAW.states.compacting_seen, pattern: 'mottle' } } }, 'compacting_seen').circles
  assert.ok(a.length >= 1, 'the oracle draws at least one dot for the added state')
  assert.notDeepEqual(canon(a), canon(b), 'the oracle must distinguish the added pattern from mottle, or this part proves nothing')
  assert.deepEqual(canon(circlesInText(`<svg><circle cx='1' cy='2.5' r='3' fill='#AABBCC' fill-opacity='.2'/></svg>`)), ['1.00,2.50,3.00,#aabbcc,0.200'])
  assert.deepEqual(canon(circlesInText(encodeURIComponent(`<svg><circle cx="1" cy="2" r="3" fill="#aabbcc" opacity="0.5"/></svg>`))), ['1.00,2.00,3.00,#aabbcc,0.500'])
})

test('P6.2 the swatch of an added state carries its name and draws exactly the oracle\'s dots for the configured pattern', async () => {
  const { h, sdk, driver } = await ready(RAW)
  sdk.fake.emit(compacting('a'))
  await driver.run(h, 1500)
  assert.equal(swatchRoot(h, 'SA').props['data-cf-state'], 'compacting_seen')
  const want = oracle(RAW, 'compacting_seen').circles
  assert.deepEqual(canon(swatchCircles(h, 'SA')), canon(want), 'the swatch does not draw the domain\'s dots for the configured pattern')
  h.dispose()
})

test('P6.3 the strip says the oracle\'s label for the added state, and the resting swatch equals the oracle too (the reader works)', async () => {
  const { h, sdk, driver } = await ready(RAW)
  assert.deepEqual(canon(swatchCircles(h, 'SA')), canon(oracle(RAW, 'resting').circles), 'the resting swatch differs from the oracle')
  sdk.fake.emit(compacting('a'))
  await driver.run(h, 1500)
  const label = oracle(RAW, 'compacting_seen').settings.states.compacting_seen.label
  assert.equal(label, 'tidying up')
  assert.match(stripText(h), new RegExp(label))
  assert.ok(fakeDocument.documentElement.getAttribute('data-cf-state') === 'compacting_seen')
  h.dispose()
})

test('P6.4 a live pattern edit redraws the swatch as the oracle draws the new pattern', async () => {
  const { h, sdk, box, driver } = await ready(RAW)
  sdk.fake.emit(compacting('a'))
  await driver.run(h, 1500)
  const edited = { ...RAW, states: { compacting_seen: { ...RAW.states.compacting_seen, pattern: 'zebra' } } }
  box.settings = edited
  box.mtime = 2
  await driver.run(h, 12_000)
  assert.deepEqual(canon(swatchCircles(h, 'SA')), canon(oracle(edited, 'compacting_seen').circles))
  assert.notDeepEqual(canon(oracle(edited, 'compacting_seen').circles), canon(oracle(RAW, 'compacting_seen').circles))
  h.dispose()
})
