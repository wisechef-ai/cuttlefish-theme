// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT PART 2 — oA: a state a USER ADDS in config is carried end to end (closes luna F8, SPEC C2).
// Locked o2_config.test.ts resolves added states, but nothing drove one through the SURFACES. Here the settings add
//   states.compacting_seen = { when: 'compacting', pattern: 'ripple', priority: 70, label: 'tidying up' }
//   patterns.ripple        = { base: 'clouds', density: 2, contrast: 1.5, scale: 1 }
// and a `status.update { kind: 'compacting' }` for the focused session must surface that state's NAME in the swatch
// data-cf-state, its LABEL in the status strip and the NAME in html[data-cf-state]; the custom pattern must be the one
// drawn; a live edit (config mtime) re-prices and relabels it without a restart; a rejected addition changes nothing.
// (The composer-ring change per state is pinned by oA_part1_applied P3.2.)
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  boot, busy, currentCss, fakeDocument, focus, LoopDriver, mountTitlebar, stripText, swatchRoot,
} from './fake/part1_probe.mjs'

const ADDED = {
  states: { compacting_seen: { when: 'compacting', pattern: 'ripple', priority: 70, label: 'tidying up' } },
  patterns: { ripple: { base: 'clouds', density: 2, contrast: 1.5, scale: 1 } },
}
const compacting = rt => ({ type: 'status.update', session_id: rt, payload: { kind: 'compacting' } })
const rootState = () => fakeDocument.documentElement.getAttribute('data-cf-state')
const state = (h, id) => swatchRoot(h, id).props['data-cf-state']

async function ready(settings) {
  const b = await boot({ settings })
  focus(b.sdk, 'a', 'SA')
  b.sdk.fake.emit({ type: 'session.info', session_id: 'b', payload: { stored_session_id: 'SB' } })
  mountTitlebar(b.h)
  b.driver = new LoopDriver(b.sdk)
  await b.driver.run(b.h, 12_000)   // first sight of the config mtime fetches /config (locked A7 allows 12 s)
  return b
}

test('P4.1 an added state reaches the swatch, the strip and the html root for the focused session — and no other row', async () => {
  const { h, sdk, driver } = await ready(ADDED)
  assert.equal(state(h, 'SA'), 'resting')
  assert.equal(rootState(), 'resting')
  const restingStrip = stripText(h)
  assert.ok(!restingStrip.includes('tidying up'))
  sdk.fake.emit(compacting('a'))
  await driver.run(h, 1500)
  assert.equal(state(h, 'SA'), 'compacting_seen', 'the swatch names the added state')
  assert.equal(rootState(), 'compacting_seen', 'html[data-cf-state] names the added state for the focused session')
  assert.match(stripText(h), /tidying up/, 'the strip says the added state\'s label in words')
  assert.equal(state(h, 'SB'), 'resting', 'another session\'s row is untouched')
  sdk.fake.emit({ type: 'message.complete', session_id: 'a', payload: { status: 'complete' } })
  await driver.run(h, 1500)
  assert.equal(state(h, 'SA'), 'resting', 'a turn end clears compacting')
  assert.equal(rootState(), 'resting')
  assert.ok(!stripText(h).includes('tidying up'))
  h.dispose()
})

test('P4.2 priority is honoured end to end: 70 beats working (60); a live edit to 10 hands the row back to working', async () => {
  const { h, sdk, box, driver } = await ready(ADDED)
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  sdk.fake.emit(compacting('a'))
  await driver.run(h, 1500)
  assert.equal(state(h, 'SA'), 'compacting_seen')
  box.settings = { ...ADDED, states: { compacting_seen: { ...ADDED.states.compacting_seen, priority: 10, label: 'tidying' } } }
  box.mtime = 2
  await driver.run(h, 12_000)
  assert.equal(state(h, 'SA'), 'working', 'priority 10 < 60: working wins now, with no restart')
  assert.equal(rootState(), 'working')
  box.settings = { ...ADDED, states: { compacting_seen: { ...ADDED.states.compacting_seen, label: 'compacting now' } } }
  box.mtime = 3
  await driver.run(h, 12_000)
  assert.equal(state(h, 'SA'), 'compacting_seen')
  assert.match(stripText(h), /compacting now/, 'a relabel applies live')
  h.dispose()
})

test('P4.3 the added state\'s own pattern is the one drawn (swatch and field differ from the same state on another pattern)', async () => {
  const drawn = async settings => {
    const { h, sdk, driver } = await ready(settings)
    sdk.fake.emit(compacting('a'))
    await driver.run(h, 7000)
    const out = { swatch: JSON.stringify(swatchRoot(h, 'SA')), css: currentCss() }
    h.dispose()
    return out
  }
  const ripple = await drawn(ADDED)
  const zebra = await drawn({ ...ADDED, patterns: {}, states: { compacting_seen: { ...ADDED.states.compacting_seen, pattern: 'zebra' } } })
  assert.notEqual(ripple.swatch, zebra.swatch, 'the swatch ignores the added state\'s pattern')
  assert.notEqual(ripple.css, zebra.css, 'the field ignores the added state\'s pattern')
})

test('P4.4 a rejected addition changes nothing: unknown pattern / unknown signal / no priority leave the row resting', async () => {
  const bad = [
    { states: { oops: { when: 'compacting', pattern: 'plaid', priority: 70, label: 'oops' } } },
    { states: { oops: { when: 'sulking', pattern: 'zebra', priority: 70, label: 'oops' } } },
    { states: { oops: { when: 'compacting', pattern: 'zebra', label: 'oops' } } },
  ]
  for (const settings of bad) {
    const { h, sdk, driver } = await ready(settings)
    sdk.fake.emit(compacting('a'))
    await driver.run(h, 1500)
    assert.equal(state(h, 'SA'), 'resting', `${JSON.stringify(settings)} was applied`)
    assert.equal(rootState(), 'resting')
    assert.ok(!stripText(h).includes('oops'))
    h.dispose()
  }
})

test('P4.5 removing the addition live returns the row to resting; the five presets are still there', async () => {
  const { h, sdk, box, driver } = await ready(ADDED)
  sdk.fake.emit(compacting('a'))
  await driver.run(h, 1500)
  assert.equal(state(h, 'SA'), 'compacting_seen')
  box.settings = {}
  box.mtime = 2
  await driver.run(h, 12_000)
  assert.equal(state(h, 'SA'), 'resting', 'the state is gone; compacting falls through to resting (O2c.4)')
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await driver.run(h, 1500)
  assert.equal(state(h, 'SA'), 'working')
  h.dispose()
})
