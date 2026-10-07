// Behaviour of the REAL desktop stub plugin (tools/p1/hosts/desktop-stub/plugin.js): how it paints a surface.
// The plugin is imported as shipped; only the three modules the desktop loader injects (@hermes/plugin-sdk,
// react, react/jsx-runtime) are replaced by inert stand-ins, and canvas / ImageData are recorded fakes.
//   node --test tools/tests/p1_desktop_stub.test.mjs
import assert from 'node:assert/strict'
import * as module from 'node:module'
import * as path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')

const stubs = {
  '@hermes/plugin-sdk': 'export const host={},PANES_AREA="p",SESSION_ROW_AREAS={leading:"l"},STATUSBAR_AREAS={left:"s"};' +
    'export const atom=v=>({get:()=>v,set(){}});export const useValue=a=>a.get()',
  react: 'const f=()=>{};export const useEffect=f,useLayoutEffect=f,useRef=f,useState=f',
  'react/jsx-runtime': 'export const jsx=()=>null,jsxs=()=>null',
}
module.register('data:text/javascript,' + encodeURIComponent(`
  const stubs = ${JSON.stringify(stubs)}
  export async function resolve(spec, ctx, next) {
    if (spec in stubs) return { url: 'stub:' + spec, shortCircuit: true }
    return next(spec, ctx)
  }
  export async function load(url, ctx, next) {
    if (url.startsWith('stub:')) return { format: 'module', source: JSON.parse(${JSON.stringify(JSON.stringify(stubs))})[url.slice(5)], shortCircuit: true }
    return next(url, ctx)
  }`), import.meta.url)

globalThis.ImageData = class { constructor(data, w, h) { this.data = data; this.width = w; this.height = h } }
const stub = await import(path.join(ROOT, 'tools/p1/hosts/desktop-stub/plugin.js'))

const fakeCanvas = () => ({ width: 0, height: 0, style: {}, getContext: () => ({ putImageData() {} }) })
/** A direction that paints whatever size it is asked for and ALWAYS returns a text overlay. */
const talkative = { paint: ({ w, h }) => ({ pixels: new Uint8ClampedArray(w * h * 4), text: [{ x: 0, y: 0, str: 'ERROR 2m', fg: '#fff' }] }) }
const session = { name: 'x', lineage_id: 'l' }

test('XL is painted at ~1/4 of the pane in CSS px', () => {
  const c = fakeCanvas()
  stub.paintInto(c, talkative, { scale: 'XL', w: 720, h: 400, state: 'idle', session, t: 0 })
  assert.deepEqual([c.width, c.height], [180, 100])
})

test('XL never exceeds 57600 painted px, whatever the pane size, and keeps the pane aspect', () => {
  for (const [w, h] of [[1900, 2400], [3840, 2160], [720, 4000], [10000, 10000], [5, 3], [1, 1]]) {
    const c = fakeCanvas()
    stub.paintInto(c, talkative, { scale: 'XL', w, h, state: 'idle', session, t: 0 })
    assert.ok(c.width >= 1 && c.height >= 1)
    assert.ok(c.width * c.height <= 57600, `${w}x${h} painted ${c.width}x${c.height}`)
    if (w * h > 57600 * 16) assert.ok(Math.abs(c.width / c.height - w / h) < 0.05 * (w / h), `aspect drift ${w}x${h}`)
  }
})

test('XL canvas is upscaled with smoothing; M and S stay pixelated', () => {
  const xl = fakeCanvas(), m = fakeCanvas(), s = fakeCanvas()
  stub.paintInto(xl, talkative, { scale: 'XL', w: 720, h: 400, state: 'idle', session, t: 0 })
  stub.paintInto(m, talkative, { scale: 'M', w: 20, h: 2, state: 'idle', session, t: 0 })
  stub.paintInto(s, talkative, { scale: 'S', w: 4, h: 2, state: 'idle', session, t: 0 })
  assert.equal(xl.style.imageRendering, 'auto')
  assert.equal(m.style.imageRendering, 'pixelated')
  assert.equal(s.style.imageRendering, 'pixelated')
})

test('XL text overlays are still returned (CSS px), the direction is told the pane size', () => {
  let seen
  const dir = { paint: a => { seen = a; return talkative.paint(a) } }
  const text = stub.paintInto(fakeCanvas(), dir, { scale: 'XL', w: 720, h: 400, state: 'fault', session, t: 0 })
  assert.equal(text.length, 1)
  assert.deepEqual([seen.w, seen.h, seen.opts.cssW, seen.opts.cssH], [180, 100, 720, 400])
})

test('desktop S swatch (w <= 8) draws no text even when the direction returns some', () => {
  for (const w of [1, 4, 8]) {
    const text = stub.paintInto(fakeCanvas(), talkative, { scale: 'S', w, h: 2, state: 'fault', session, t: 0 })
    assert.deepEqual(text, [], `w=${w}`)
  }
})

test('the chip (M) and a wide S keep their text', () => {
  assert.equal(stub.paintInto(fakeCanvas(), talkative, { scale: 'M', w: 20, h: 2, state: 'fault', session, t: 0 }).length, 1)
  assert.equal(stub.paintInto(fakeCanvas(), talkative, { scale: 'S', w: 14, h: 2, state: 'fault', session, t: 0 }).length, 1)
})
