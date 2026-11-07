// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT PART 1 — oA: what the shipped plugin APPLIES, not what its text mentions (closes luna F3, F5-loop).
// Locked A4/A10 regex-match tokens in raw CSS / the serialised strip: a token inside a /* comment */ or an inert rule passes.
// ADDENDUM R-S1: the composer ring VARIABLE route is dead on v0.22.7 (core pins the composer border with !important); the composer speaks
// through a plugin-owned RIM in COMPOSER_AREAS.top. Here the CSS is comment-stripped and PARSED, the field data-URI is DECODED and its circles counted, the composer-ring
// rim (composer.top) must carry the state, the strip's words must differ across presets, and the budgeted loop must actually
// run frames that change the field while the focused session works (A5 only inspected `idleWhen`).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  backgroundLayers, boot, busy, countCircles, currentCss, declarations, fieldLayers, flush, focus, LoopDriver, mountTitlebar, ownStyles, rimRoot,
  parseRules, setReducedMotion, stripCssComments, stripText, svgDataUris,
} from './fake/part1_probe.mjs'

const SETTLE_MS = 7000   // > BLOOM_MS (≤ 4000) + slack

const needsYou = (id, active, rid = 'r1') => ({ type: 'plugin.cuttlefish-theme.needs_you', session_id: '',
  payload: { session_id: id, session_key: id, request_id: rid, kind: 'approval', active } })
const failed = id => ({ type: 'plugin.cuttlefish-theme.error', session_id: '', payload: { session_id: id, session_key: id, retryable: false } })

// ---- the instrument itself (needs no implementation) ---------------------------------------------------------------

const circles = n => Array.from({ length: n }, (_, i) => `<circle cx='${i}' cy='${i}' r='3' fill='%23336699' fill-opacity='.2'/>`).join('')
const uri = n => `url("data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='800'>${circles(n)}</svg>`)}")`

test('P3.0 the CSS instrument ignores comments, reads the decoded field, and sees inert or shorthand rules for what they are', () => {
  const good = `[data-chat-surface]{background-image:${uri(60)};}:root{--dt-composer-ring:#336699;--composer-ring-strength:.4}`
  assert.equal(fieldLayers(good).length, 1)
  assert.equal(countCircles(fieldLayers(good)[0]), 60)
  assert.deepEqual(declarations(good, '--composer-ring-strength'), ['.4'])
  // tokens only inside a comment: nothing is applied
  const commented = `/* [data-chat-surface]{background-image:${uri(60)}} --dt-composer-ring: red; */ body{margin:0}`
  assert.deepEqual(fieldLayers(commented), [])
  assert.deepEqual(declarations(commented, '--dt-composer-ring'), [])
  // a rule on another selector, or an image with no organs, is inert
  assert.deepEqual(fieldLayers(`.other{background-image:${uri(60)}}`), [])
  assert.equal(countCircles(fieldLayers(`[data-chat-surface]{background-image:${uri(0)}}`)[0]), 0)
  // at-rules are entered; base64 and quoted forms decode; ';' and ')' inside a url() do not split the declaration
  assert.equal(fieldLayers(`@media (min-width:1px){[data-chat-surface]::before{background-image:${uri(41)}}}`).map(countCircles)[0], 41)
  const b64 = Buffer.from(`<svg>${circles(3)}</svg>`).toString('base64')
  assert.equal(countCircles(svgDataUris(`url(data:image/svg+xml;base64,${b64})`)[0]), 3)
  assert.deepEqual(parseRules(stripCssComments('a{x:url("data:a;b)");y:1} b{z:2}')).map(r => r.selectors), [['a'], ['b']])
  assert.deepEqual(parseRules('{color:red}'), [{ selectors: [], decls: [{ prop: 'color', value: 'red' }], at: null }], 'a rule at offset 0')
  assert.deepEqual(parseRules('x{:v;A-B : W }')[0].decls, [{ prop: '', value: 'v' }, { prop: 'a-b', value: 'W' }], 'colon at 0; props lower-cased; values trimmed')
  assert.deepEqual(parseRules('x{novalue}')[0].decls, [], 'a declaration without a colon is dropped')
  assert.deepEqual(svgDataUris('url("data:image/svg+xml,%E0%A4%A")'), ['%E0%A4%A'], 'an undecodable payload is kept raw, not thrown')
  assert.deepEqual(svgDataUris('url(data:text/plain,hi) url("data:image/svg+xml,%3Csvg%3E%3C/svg%3E")'), ['<svg></svg>'], 'only svg images')
  assert.equal(fieldLayers(`[data-chat-surface]{background:${uri(5)}}`).length, 1, 'a background shorthand is read as a layer too')
  assert.deepEqual(fieldLayers(`[data-chat-surface]{mask-image:${uri(5)}}`), [], 'other properties are not field layers')
  assert.equal(countCircles('<svg><CIRCLE r=1/><circle/></svg>'), 2)
  assert.equal(countCircles('<svg/>'), 0)
  assert.equal(backgroundLayers(`[data-chat-surface]{background-image:${uri(5)}}`).length, 0, 'R-S1: the field is the `background` declaration')
  assert.equal(backgroundLayers(`[data-chat-surface]{background:${uri(5)}, var(--cf-ground)}`).length, 1)
  assert.equal(backgroundLayers(`.x{background:${uri(5)}}`).length, 0)
  assert.throws(() => parseRules('a{b:1'), /unbalanced/)
})

// ---- the applied field + composer ring ------------------------------------------------------------------------------

async function settle(driver, h) { await h.advance(100); await flush(); await driver.run(h, SETTLE_MS) }

test('P3.1 the field is APPLIED: a [data-chat-surface] rule paints a decoded SVG with ≥ 40 organs, and never a fill', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  await settle(new LoopDriver(sdk), h)
  assert.equal(ownStyles().length, 1, 'exactly one owned <style>')
  const css = currentCss()
  const layers = backgroundLayers(css)
  assert.ok(layers.length >= 1, 'no [data-chat-surface] rule sets an svg data-URI in its `background` declaration (R-S1; tokens in comments do not count)')
  const n = Math.max(...layers.map(countCircles))
  assert.ok(n >= 40, `the applied field holds ${n} organs (< 40): a sparse scatter of at least 40 is the field`)
  for (const r of parseRules(stripCssComments(css))) {
    if (!r.selectors.some(s => s.includes('[data-chat-surface]'))) continue
    for (const d of r.decls) {
      assert.notEqual(d.prop, 'background-color', 'the user\'s own ground stays')
    }
  }
  assert.doesNotMatch(layers.join(''), /<script|href=|on\w+=/i, 'an svg background must be inert')
  h.dispose()
})

test('P3.2 the composer speaks through a plugin-owned rim in COMPOSER_AREAS.top: data-cf-state = the focused state, an SVG, ≥ 4 presets differ', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await settle(driver, h)
  const seen = {}
  const take = name => { const r = rimRoot(h); assert.ok(r.drawsSvg, `${name}: the rim draws no SVG`); seen[name] = r }
  take('resting')
  assert.equal(seen.resting.state, 'resting', 'the rim names the focused state at rest')
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await settle(driver, h)
  take('working')
  busy(sdk, {})
  sdk.fake.emit({ type: 'message.complete', session_id: 'a', payload: { status: 'complete' } })
  sdk.fake.emit(needsYou('SA', true))
  await settle(driver, h)
  take('needs_you')
  sdk.fake.emit(needsYou('SA', false))
  sdk.fake.emit(failed('SA'))
  await settle(driver, h)
  take('error')
  for (const [name, r] of Object.entries(seen)) assert.equal(r.state, name, `the rim's data-cf-state is ${r.state} while ${name}`)
  assert.equal(new Set(Object.values(seen).map(r => r.markup)).size, 4, 'the rim\'s markup does not tell 4 presets apart')
  h.dispose()
})

test('P3.2b the rim is static (rendering it never wakes the loop) and the ring variable is identity, not state', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await settle(driver, h)
  const wakes = () => sdk.calls.loops.reduce((n, l) => n + l.wakes, 0)
  const before = wakes()
  for (let i = 0; i < 5; i++) rimRoot(h)
  assert.equal(wakes(), before, 'rendering the rim woke the budgeted loop: the rim must never animate')
  const ring = () => declarations(currentCss(), '--dt-composer-ring', s => s.includes('[data-chat-surface]'))
  const rest = ring()
  assert.ok(rest.length >= 1 && rest[rest.length - 1].length > 0, '--dt-composer-ring is set on [data-chat-surface] (R-S1 ruling 3)')
  sdk.fake.emit(needsYou('SA', true))
  await settle(driver, h)
  assert.deepEqual(ring(), rest, 'the ring variable is the session\'s identity hue, never a state signal')
  h.dispose()
})

test('P3.3 the status strip speaks: its words differ across at least 4 presets (resting, working, needs you, error)', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  const seen = {}
  await settle(driver, h)
  seen.resting = stripText(h)
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await settle(driver, h)
  seen.working = stripText(h)
  busy(sdk, {})
  sdk.fake.emit({ type: 'message.complete', session_id: 'a', payload: { status: 'complete' } })
  sdk.fake.emit(needsYou('SA', true))
  await settle(driver, h)
  seen.needs_you = stripText(h)
  sdk.fake.emit(needsYou('SA', false))
  sdk.fake.emit(failed('SA'))
  await settle(driver, h)
  seen.error = stripText(h)
  // resting's default label is "" (contract/config-vectors.json): the strip may say nothing at rest, never while it matters
  for (const [k, v] of Object.entries(seen)) if (k !== 'resting') assert.ok(v.length > 0, `the strip is empty while ${k}`)
  assert.equal(new Set(Object.values(seen)).size, 4, `strip words are not distinct per preset: ${JSON.stringify(seen)}`)
  assert.match(seen.needs_you, /needs you/i)
  h.dispose()
})

// ---- frames really run (F5) --------------------------------------------------------------------------------------------

test('P3.4 while the focused session works the loop runs frames and the applied field changes between them (slow clouds)', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await settle(driver, h)
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(100)
  await driver.run(h, SETTLE_MS)                 // let the bloom pass: any change below is the clouds, not the bloom
  const loop = sdk.calls.loops.find(l => !l.disposed)
  assert.ok(loop, 'a live budgeted loop')
  assert.equal(loop.opts.idleWhen(), false, 'working: the loop is awake')
  const drawsBefore = driver.draws
  const frames = new Set()
  for (let i = 0; i < 6; i++) {
    const made = await driver.run(h, 1000)
    assert.ok(made >= 1, `second ${i + 1}: the loop ran no frame while the focused session works`)
    frames.add(fieldLayers(currentCss()).join('|'))
  }
  assert.ok(driver.draws - drawsBefore >= 6)
  assert.ok(frames.size >= 2, 'six seconds of frames left the field untouched: the clouds do not pass')
  for (const svg of frames) assert.ok(countCircles(svg.split('|')[0]) >= 40, 'the field stays a ≥ 40-organ scatter while it moves')
  assert.equal(ownStyles().length, 1, 'frames update the one owned <style> in place')
  h.dispose()
})

test('P3.5 at rest, and under reduced motion, no frame changes the field (the loop is parked)', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await settle(driver, h)
  const rest = currentCss()
  assert.ok(fieldLayers(rest).length >= 1, 'a resting field is drawn (the floor under the near-invisible ceiling)')
  await driver.run(h, 6000)
  assert.equal(currentCss(), rest, 'resting + still: the field is static')
  setReducedMotion(true)
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await settle(driver, h)
  const calm = currentCss()
  await driver.run(h, 5000)
  assert.equal(currentCss(), calm, 'prefers-reduced-motion: working does not drift')
  setReducedMotion(false)
  h.dispose()
})
