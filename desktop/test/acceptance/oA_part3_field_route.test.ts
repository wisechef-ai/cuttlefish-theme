// @ts-nocheck — exercises the JS fakes under ./fake; behaviour, not types, is the contract here.
// ACCEPTANCE CONTRACT PART 3 — oA: the ONLY legal field route on v0.22.7 (addendum R-S1, ruling 1).
// Measured on a real Desktop (M0.4): a background-image on [data-chat-surface] is hidden by the opaque composer-bounds child;
// an ::after overlay paints OVER the text. The route that works: the owned <style> makes the surface transparent through the
// documented --ui-chat-surface-background variable and paints   background: url("data:image/svg+xml,…"), var(--cf-ground)
// with   --cf-ground: var(--ui-chat-surface-background)   declared at :root, so the last layer is the USER'S OWN ground by reference.
import { strict as assert } from 'node:assert'
import { test } from 'node:test'

import {
  boot, busy, countCircles, currentCss, flush, focus, LoopDriver, mountTitlebar, parseRules, splitLayers, stripCssComments, svgDataUris,
} from './fake/part1_probe.mjs'

const SURFACE = /^\[data-chat-surface\](\[data-composer-target\])?$/
const ROOTISH = /^(:root|html)(\[data-cf-[a-z-]+(="[^"]*")?\])*$/
const NAMED = ['transparent', 'black', 'white', 'red', 'green', 'blue', 'gray', 'grey', 'silver', 'yellow', 'orange', 'purple', 'pink', 'brown',
  'cyan', 'magenta', 'navy', 'teal', 'olive', 'maroon', 'lime', 'aqua', 'fuchsia', 'currentcolor', 'tomato', 'gold', 'indigo', 'violet']
const FUNCS = /(#[0-9a-f]{3,8}\b|\b(rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color|color-mix|light-dark)\()/i

/** Every way a stylesheet departs from ruling 1; [] when it follows it. */
export function routeProblems(rawCss) {
  const rules = parseRules(stripCssComments(rawCss))
  const bad = []
  const decl = (r, prop) => r.decls.filter(d => d.prop === prop).map(d => d.value)
  const surface = rules.filter(r => r.selectors.some(s => SURFACE.test(s)))
  const rootish = rules.filter(r => r.selectors.some(s => ROOTISH.test(s)))
  for (const r of rules) {
    for (const s of r.selectors) {
      if (/::?(before|after)\b/i.test(s)) bad.push(`pseudo-element rule ${s}: an overlay paints over the text`)
      else if (!SURFACE.test(s) && !ROOTISH.test(s)) bad.push(`selector ${s} is outside :root/html, [data-chat-surface] and html[data-cf-…]`)
    }
    for (const d of r.decls.filter(x => x.prop.startsWith('background'))) {
      const bare = d.value.replace(/url\(\s*(?:"[^"]*"|'[^']*'|[^)]*)\s*\)/gi, 'url()')
      if (FUNCS.test(bare) || NAMED.some(n => new RegExp(`(^|[^\\w-])${n}([^\\w-]|$)`, 'i').test(bare))) {
        bad.push(`a literal colour in ${d.prop}: ${bare}`)
      }
    }
  }
  if (!surface.some(r => decl(r, '--ui-chat-surface-background').some(v => v.trim() === 'transparent'))) {
    bad.push('[data-chat-surface] does not set --ui-chat-surface-background: transparent')
  }
  const backgrounds = surface.flatMap(r => decl(r, 'background'))
  if (backgrounds.length === 0) bad.push('[data-chat-surface] has no `background` declaration')
  for (const v of backgrounds) {
    const layers = splitLayers(v)
    if (layers[layers.length - 1] !== 'var(--cf-ground)') bad.push(`the last background layer is ${layers[layers.length - 1]}, not var(--cf-ground)`)
    if (!layers.slice(0, -1).some(l => svgDataUris(l).length > 0)) bad.push('no svg data-URI layer before the ground')
  }
  if (surface.some(r => r.decls.some(d => d.prop === 'background-color'))) bad.push('background-color on the surface')
  if (!rootish.some(r => decl(r, '--cf-ground').some(v => v.trim() === 'var(--ui-chat-surface-background)'))) {
    bad.push(':root/html does not declare --cf-ground: var(--ui-chat-surface-background)')
  }
  return bad
}

const dots = n => Array.from({ length: n }, (_, i) => `<circle cx='${i}' cy='${i}' r='3' fill='%23336699' fill-opacity='.2'/>`).join('')
const uri = n => `url("data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg'>${dots(n)}</svg>`)}")`
const GOOD = `:root{--cf-ground:var(--ui-chat-surface-background)}[data-chat-surface]{--ui-chat-surface-background:transparent;background:${uri(60)} 0 0/1200px 800px no-repeat, var(--cf-ground);--dt-composer-ring:#336699}`

test('P5.0 the route checker accepts the ruling and rejects each departure (scratch CSS, no implementation needed)', () => {
  assert.deepEqual(routeProblems(GOOD), [])
  assert.deepEqual(routeProblems(`html[data-cf-state="working"]{--x:1}${GOOD}`), [])
  assert.deepEqual(routeProblems(GOOD.replace('[data-chat-surface]{', '[data-chat-surface][data-composer-target]{')), [])
  const overlay = `${GOOD}[data-chat-surface]::after{content:"";background:${uri(60)}}`
  assert.ok(routeProblems(overlay).some(p => /pseudo-element/.test(p)), 'an ::after overlay')
  assert.ok(routeProblems(`${GOOD}[data-chat-surface]:before{content:""}`).some(p => /pseudo-element/.test(p)))
  assert.ok(routeProblems(GOOD.replace('var(--cf-ground)', '#141416').replace(':root{--cf-ground:#141416}', ':root{--cf-ground:var(--ui-chat-surface-background)}')).some(p => /literal colour/.test(p) || /last background layer/.test(p)))
  for (const lit of ['#141416', 'rgb(20,20,22)', 'oklch(0.2 0 0)', 'hsl(0 0% 8%)', 'black', 'transparent']) {
    const css = GOOD.replace('no-repeat, var(--cf-ground)', `no-repeat, var(--cf-ground), ${lit}`)
    assert.ok(routeProblems(css).some(p => /literal colour/.test(p)), `literal ${lit}`)
  }
  assert.ok(routeProblems(`/* ${GOOD} */ body{margin:0}`).length >= 3, 'tokens in a comment prove nothing')
  assert.ok(routeProblems(GOOD.replace('transparent', 'red')).some(p => /transparent/.test(p)))
  assert.ok(routeProblems(GOOD.replace(':root{', '.x{')).some(p => /--cf-ground|selector/.test(p)))
  assert.ok(routeProblems(GOOD.replace('--cf-ground:var(--ui-chat-surface-background)', '--cf-ground:#111')).some(p => /--cf-ground/.test(p)))
  assert.ok(routeProblems(`${GOOD}.chat .message{color:red}`).some(p => /selector/.test(p)), 'a selector into core markup')
  assert.ok(routeProblems(`${GOOD}[data-slot="composer-surface"]{x:1}`).some(p => /selector/.test(p)))
  assert.ok(routeProblems(GOOD.replace('background:', 'background-color:#fff;background:')).some(p => /background-color|literal/.test(p)))
  assert.ok(routeProblems(GOOD.replace(`${uri(60)} 0 0/1200px 800px no-repeat, var(--cf-ground)`, 'var(--cf-ground)')).some(p => /svg data-URI/.test(p)))
  assert.deepEqual(splitLayers('url("a,b") 0 0, var(--x, red), none'), ['url("a,b") 0 0', 'var(--x, red)', 'none'])
})

test('P5.1 the shipped plugin follows ruling 1 at rest and while working, with ≥ 40 circles in the field layer', async () => {
  const { h, sdk } = await boot()
  focus(sdk, 'a', 'SA')
  mountTitlebar(h)
  const driver = new LoopDriver(sdk)
  await h.advance(100); await flush(); await driver.run(h, 7000)
  assert.deepEqual(routeProblems(currentCss()), [])
  const layer = splitLayers(parseRules(stripCssComments(currentCss())).filter(r => r.selectors.some(s => s.includes('[data-chat-surface]'))).flatMap(r => r.decls).find(d => d.prop === 'background').value)[0]
  assert.ok(countCircles(svgDataUris(layer)[0]) >= 40)
  busy(sdk, { a: true })
  sdk.fake.emit({ type: 'message.start', session_id: 'a', payload: {} })
  await h.advance(100); await driver.run(h, 7000)
  assert.deepEqual(routeProblems(currentCss()), [], 'every frame keeps the route')
  h.dispose()
})
