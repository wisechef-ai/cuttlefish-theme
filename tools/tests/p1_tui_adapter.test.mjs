// Pure adapter of the TUI stub widget (tools/p1/hosts/tui-stub-widget.mjs): paint() pixels → terminal cells.
// Behaviour on outputs; the widget module is imported with the env it needs (it reads nothing at import but these).
//   node --test tools/tests/p1_tui_adapter.test.mjs
import assert from 'node:assert/strict'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'cf-p1-adapter-'))
fs.writeFileSync(path.join(tmp, 'scene.json'), '{}')
Object.assign(process.env, {
  CF_P1_DIRECTION: path.join(ROOT, 'design/directions/_ref/direction.mjs'),
  CF_P1_FIXTURE: path.join(ROOT, 'tools/p1/stub-sessions.json'),
  CF_P1_SCENE: path.join(tmp, 'scene.json'),
})
const w = await import(path.join(ROOT, 'tools/p1/hosts/tui-stub-widget.mjs'))

const px = (...rgb) => {
  const a = new Uint8ClampedArray(rgb.length / 3 * 4)
  for (let i = 0; i < rgb.length / 3; i++) a.set([rgb[i * 3], rgb[i * 3 + 1], rgb[i * 3 + 2], 255], i * 4)
  return a
}

test('half rung: one ▀ per cell, fg = top pixel, bg = bottom pixel', () => {
  // 2 cols × 2 pixel rows → 1 cell row
  const g = w.toCells({ pixels: px(255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255), text: [] }, 2, 1, 'half', 'truecolor')
  assert.deepEqual(g, [[{ ch: '▀', fg: '#ff0000', bg: '#0000ff' }, { ch: '▀', fg: '#00ff00', bg: '#ffffff' }]])
})

test('bg rung: background-coloured spaces only, 1 pixel per cell', () => {
  const g = w.toCells({ pixels: px(1, 2, 3, 4, 5, 6), text: [] }, 1, 2, 'bg', 'truecolor')
  assert.deepEqual(g, [[{ ch: ' ', fg: null, bg: '#010203' }], [{ ch: ' ', fg: null, bg: '#040506' }]])
})

test('256 depth: every colour becomes an exact xterm-256 entry (16..255), never a themed system colour', () => {
  for (const [rgb, want] of [[[0, 0, 0], 16], [[255, 255, 255], 231], [[135, 95, 175], 97], [[128, 128, 128], 244]]) {
    assert.equal(w.nearest256(...rgb), want, rgb)
  }
  const g = w.toCells({ pixels: px(130, 90, 170, 250, 170, 5), text: [] }, 1, 1, 'half', '256')
  assert.deepEqual(g[0][0], { ch: '▀', fg: 'ansi256(97)', bg: 'ansi256(214)' })
  for (let r = 0; r < 256; r += 51) for (let gg = 0; gg < 256; gg += 37) {
    const n = w.nearest256(r, gg, 200)
    assert.ok(n >= 16 && n <= 255)
  }
})

test('text overlays are real characters on their own colours, clipped to the box', () => {
  const pixels = px(...Array(8 * 2).fill([10, 10, 10]).flat())
  const g = w.toCells({ pixels, text: [{ x: 5, y: 0, str: 'INPUT 4m', fg: '#000000', bg: '#ffb000' }] }, 8, 1, 'half', 'truecolor')
  assert.equal(g[0].map(c => c.ch).join(''), '▀▀▀▀▀INP')
  assert.deepEqual(g[0][5], { ch: 'I', fg: '#000000', bg: '#ffb000' })
})

test('runs merge identical neighbours (one Text node per run)', () => {
  const line = [{ ch: '▀', fg: 'a', bg: 'b' }, { ch: '▀', fg: 'a', bg: 'b' }, { ch: 'x', fg: 'c', bg: 'b' }]
  assert.deepEqual(w.runs(line), [{ str: '▀▀', fg: 'a', bg: 'b' }, { str: 'x', fg: 'c', bg: 'b' }])
})

test('mantle height follows D3: 2 rows, 1 under 30 terminal rows', () => {
  assert.equal(w.mantleRows(40), 2)
  assert.equal(w.mantleRows(30), 2)
  assert.equal(w.mantleRows(29), 1)
})

test('identity grid: 16 and 20 tiles, 4 per row, inside cols − 2', () => {
  for (const n of [16, 20]) {
    const L = w.gridLayout(120, n)
    assert.equal(L.tiles.length, n)
    assert.ok(L.width <= 118)
    const keys = new Set(L.tiles.map(t => `${t.col},${t.row}`))
    assert.equal(keys.size, n)
  }
})

test('pixelPalette lists box colours, never glyph ink', () => {
  const g = [[{ ch: '▀', fg: '#111111', bg: '#222222' }, { ch: 'A', fg: '#ffffff', bg: '#333333' }, { ch: ' ', fg: null, bg: 'ansi256(16)' }]]
  assert.deepEqual(w.pixelPalette(g), ['#000000', '#111111', '#222222', '#333333'])
})
