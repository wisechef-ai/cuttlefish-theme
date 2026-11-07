// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT PART 5 — oA: the owned <style> may declare ONLY what ruling R-S1 allows (closes luna-parts L4).
// oA_part3_field_route checks the shape of the background route but would let a stylesheet hide the transcript (`visibility`, `opacity`, `filter`…)
// or recolour core text. Here EVERY declaration of the owned style is checked against a property allowlist (binding):
//   rules on [data-chat-surface] (optionally with [data-composer-target]): only custom properties (--*), background, background-image,
//                                                                          background-position, background-size, background-repeat
//   rules on :root / html / html[data-cf-…]:                               only custom properties (--*)
// Any other selector, or any other property, fails. At-rules are entered (a @media block is no loophole). Comments prove nothing.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import { boot, busy, currentCss, flush, focus, LoopDriver, mountTitlebar, parseRules, stripCssComments } from './fake/part1_probe.mjs'

const SURFACE = /^\[data-chat-surface\](\[data-composer-target\])?$/
const ROOTISH = /^(:root|html)(\[data-cf-[a-z-]+(="[^"]*")?\])*$/
const SURFACE_PROPS = new Set(['background', 'background-image', 'background-position', 'background-size', 'background-repeat'])

/** Every declaration the owned style makes that the allowlist does not permit; [] when it makes none. */
export function allowlistProblems(rawCss) {
  const bad = []
  for (const r of parseRules(stripCssComments(rawCss))) {
    for (const sel of r.selectors) {
      const onSurface = SURFACE.test(sel)
      const onRoot = ROOTISH.test(sel)
      if (!onSurface && !onRoot) { bad.push(`selector ${sel} is not allowed`); continue }
      for (const d of r.decls) {
        const custom = d.prop.startsWith('--')
        if (!custom && !(onSurface && SURFACE_PROPS.has(d.prop))) bad.push(`${sel} { ${d.prop} } is not allowed`)
      }
    }
  }
  return bad
}

const DOTS = `url("data:image/svg+xml;utf8,%3Csvg%3E%3C/svg%3E")`
const GOOD = `:root{--cf-ground:var(--ui-chat-surface-background)}[data-chat-surface]{--ui-chat-surface-background:transparent;background:${DOTS} 0 0/1200px 800px no-repeat, var(--cf-ground);--dt-composer-ring:#336699}`

test('P7.0 the allowlist accepts the ruling and rejects every property that could hide or recolour the chat (scratch CSS)', () => {
  assert.deepEqual(allowlistProblems(GOOD), [])
  assert.deepEqual(allowlistProblems(`${GOOD}html[data-cf-state="working"]{--cf-x:1}[data-chat-surface]{background-image:${DOTS};background-position:0 0;background-size:cover;background-repeat:no-repeat}`), [])
  assert.deepEqual(allowlistProblems(`@media (prefers-reduced-motion:reduce){[data-chat-surface][data-composer-target]{--a:1}}`), [])
  for (const prop of ['visibility:hidden', 'color:red', 'opacity:.99', 'display:none', 'filter:blur(1px)', 'transform:scale(1)', 'content:""',
    'mix-blend-mode:multiply', 'background-color:red', 'background-attachment:fixed', 'z-index:9', 'pointer-events:none', 'position:fixed']) {
    const [name] = prop.split(':')
    assert.ok(allowlistProblems(`${GOOD}[data-chat-surface]{${prop}}`).some(p => p.includes(name)), `${prop} on the surface`)
    assert.ok(allowlistProblems(`${GOOD}:root{${prop}}`).some(p => p.includes(name)), `${prop} on :root`)
    assert.ok(allowlistProblems(`${GOOD}html[data-cf-state]{${prop}}`).length >= 1, `${prop} on html[data-cf-…]`)
    assert.ok(allowlistProblems(`@media all{[data-chat-surface]{${prop}}}`).length >= 1, `${prop} inside @media`)
  }
  assert.ok(allowlistProblems(`${GOOD}:root{background:red}`).length >= 1, 'the background properties are for the surface only')
  assert.ok(allowlistProblems(`${GOOD}.message{--a:1}`).length >= 1, 'a selector into core markup')
  assert.ok(allowlistProblems(`${GOOD}[data-chat-surface] *{--a:1}`).length >= 1, 'a descendant selector')
  assert.ok(allowlistProblems(`${GOOD}[data-chat-surface],.other{--a:1}`).length >= 1, 'one bad selector in a list')
  assert.ok(allowlistProblems(`${GOOD}[data-chat-surface]{--a:1;VISIBILITY:hidden}`).length >= 1, 'property names are case-insensitive')
  assert.deepEqual(allowlistProblems(`/* [data-chat-surface]{visibility:hidden} */ ${GOOD}`), [], 'a comment declares nothing')
})

test('P7.1 the shipped plugin declares only allowlisted properties at rest, while working and after a state change', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await h.advance(100); await flush(); await driver.run(h, 7000)
  assert.ok(currentCss().length > 0, 'the plugin owns a style')
  assert.deepEqual(allowlistProblems(currentCss()), [], 'at rest')
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(100); await driver.run(h, 7000)
  assert.deepEqual(allowlistProblems(currentCss()), [], 'working')
  busy(sdk, {})
  sdk.fake.emit({ type: 'message.complete', session_id: 'a', payload: { status: 'complete' } })
  sdk.fake.emit({ type: 'plugin.cuttlefish-theme.error', session_id: '', payload: { session_id: 'SA', session_key: 'SA', retryable: false } })
  await h.advance(100); await driver.run(h, 7000)
  assert.deepEqual(allowlistProblems(currentCss()), [], 'error')
  h.dispose()
})
