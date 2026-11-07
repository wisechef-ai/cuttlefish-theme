// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT PART 1 — oA: what the shipped plugin APPLIES, not what its text mentions (closes luna F3, F5-loop).
// Locked A4/A10 regex-match tokens in raw CSS / the serialised strip: a token inside a /* comment */ or an inert rule passes.
// Here the CSS is comment-stripped and PARSED, the field data-URI is DECODED and its circles counted, the composer-ring
// VALUES must differ between states, the strip's words must differ across presets, and the budgeted loop must actually
// run frames that change the field while the focused session works (A5 only inspected `idleWhen`).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  boot, busy, countCircles, currentCss, declarations, fieldLayers, flush, focus, LoopDriver, mountTitlebar, ownStyles,
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
  assert.equal(parseRules(stripCssComments('a{x:url("data:a;b)");y:1} b{z:2}')).length, 2)
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
  const layers = fieldLayers(css)
  assert.ok(layers.length >= 1, 'no [data-chat-surface] rule paints an svg data-URI background-image (tokens in comments do not count)')
  const n = Math.max(...layers.map(countCircles))
  assert.ok(n >= 40, `the applied field holds ${n} organs (< 40): a sparse scatter of at least 40 is the field`)
  for (const r of parseRules(stripCssComments(css))) {
    if (!r.selectors.some(s => s.includes('[data-chat-surface]'))) continue
    for (const d of r.decls) {
      assert.notEqual(d.prop, 'background-color', 'the user\'s own ground stays')
      assert.notEqual(d.prop, 'background', 'a background shorthand would reset the user\'s own ground')
    }
  }
  assert.doesNotMatch(layers.join(''), /<script|href=|on\w+=/i, 'an svg background must be inert')
  h.dispose()
})

test('P3.2 the composer ring is APPLIED and state-dependent: its custom-property VALUES differ resting → needs you', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await settle(driver, h)
  const read = () => ['--dt-composer-ring', '--composer-ring-strength'].map(p => {
    const v = declarations(currentCss(), p)
    return { p, v: v.length ? v[v.length - 1] : null }
  })
  const rest = read()
  for (const { p, v } of rest) assert.ok(v && v.length > 0, `${p} is not declared with a value in the applied CSS`)
  sdk.fake.emit(needsYou('SA', true))
  await settle(driver, h)
  const need = read()
  for (const { p, v } of need) assert.ok(v && v.length > 0, `${p} vanished while needing you`)
  assert.notDeepEqual(need, rest, `focused needs-you leaves the composer ring unchanged: ${JSON.stringify(need)}`)
  sdk.fake.emit(needsYou('SA', false))
  await settle(driver, h)
  assert.deepEqual(read(), rest, 'the ring returns to its resting values when the request is resolved')
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
