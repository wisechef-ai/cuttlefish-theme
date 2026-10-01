// cf2909 P1 host (lane H): the REAL TUI widget that renders a direction module inside `hermes --tui`.
//
// Drop this file into a THROWAWAY `$HERMES_HOME/tui-widgets/` (never the live ~/.hermes). It follows the
// P0 lifecycle receipts: it docks itself at load with `openWidget` (spike 03) and disposes its previous
// evaluation through a `globalThis` Symbol before doing anything else (spike 04 hot-reload fix).
//
// Inputs (environment, all absolute paths):
//   CF_P1_DIRECTION  the default direction module (design/directions/<id>/direction.mjs), dynamic-imported.
//                    A scene may carry `direction` (absolute path) to switch modules without a relaunch.
//   CF_P1_FIXTURE    tools/p1/stub-sessions.json
//   CF_P1_SCENE      scene json: { view: mantle|pill|grid16|grid20|degraded, state, session_idx, frame_t,
//                                  rung: half|bg, depth: truecolor|256, seq? }
//                    The file is re-read when it changes, so one TUI process can serve many scenes.
//   CF_P1_ACK        optional: after a scene is on screen the widget writes `{seq, view, ...}` here, so a
//                    driver knows the frame it screenshots is the scene it asked for.
//   CF_P1_LIVE=1     smoke mode: `working` animates at 4 fps (t advances 0.25 s per frame). Captures never
//                    set it: frame t comes from the scene, so captures are deterministic.
//
// Rungs (P1-brief §1): `half` paints `▀` with fg = top pixel, bg = bottom pixel (2 px per cell); `bg` paints
// background-coloured spaces only (1 px per cell). Depth `256` quantises every colour to the xterm-256 palette
// HERE, in the adapter (the direction never sees depth beyond opts), and emits `ansi256(n)` so the terminal
// gets exactly 38;5;n / 48;5;n. Text overlays from paint().text are drawn as real characters.
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const DISPOSE = Symbol.for('cuttlefish.p1.stub.dispose')
try { globalThis[DISPOSE]?.() } catch {}

const env = process.env
const need = k => {
  if (!env[k]) throw new Error(`cf-p1 stub widget: ${k} is not set`)
  return env[k]
}
const modules = new Map()
const loadDirection = async file => {
  if (!modules.has(file)) modules.set(file, await import(`${pathToFileURL(file).href}?t=${Date.now()}`))
  return modules.get(file)
}
const DEFAULT_DIRECTION = need('CF_P1_DIRECTION')
await loadDirection(DEFAULT_DIRECTION)
const fixture = JSON.parse(fs.readFileSync(need('CF_P1_FIXTURE'), 'utf8'))
const SCENE = need('CF_P1_SCENE')
const ACK = env.CF_P1_ACK || ''
const LIVE = env.CF_P1_LIVE === '1'

// ---------------------------------------------------------------- pure adapter (exported for tests)

const CUBE = [0, 95, 135, 175, 215, 255]
/** The xterm-256 palette entries 16..255 (the 16 system colours are terminal-themed, so never targeted). */
export const XTERM256 = (() => {
  const out = []
  for (let i = 16; i < 232; i++) {
    const n = i - 16
    out.push([i, CUBE[Math.floor(n / 36)], CUBE[Math.floor(n / 6) % 6], CUBE[n % 6]])
  }
  for (let i = 232; i < 256; i++) {
    const v = 8 + 10 * (i - 232)
    out.push([i, v, v, v])
  }
  return out
})()

/** Nearest xterm-256 index (16..255) to an sRGB triple, by squared RGB distance. */
export function nearest256(r, g, b) {
  let best = 16, bd = Infinity
  for (const [i, pr, pg, pb] of XTERM256) {
    const d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
    if (d < bd) { bd = d; best = i }
  }
  return best
}

const hex2 = v => v.toString(16).padStart(2, '0')
const rgbHex = (r, g, b) => `#${hex2(r)}${hex2(g)}${hex2(b)}`
const parseHex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))

/** One terminal colour string for an sRGB triple at a depth. */
export function termColor([r, g, b], depth) {
  return depth === '256' ? `ansi256(${nearest256(r, g, b)})` : rgbHex(r, g, b)
}

/**
 * paint() pixels (+ text) -> a grid of cells {ch, fg, bg} (terminal colour strings).
 *   half: cell (x, y) = '▀' with fg = px(x, 2y), bg = px(x, 2y+1); pixel h must be 2*rows
 *   bg:   cell (x, y) = ' ' with bg = px(x, y); pixel h must be rows
 * Text overlays (cell coordinates) replace cells with real characters; overflow is clipped.
 */
export function toCells({ pixels, text }, cols, rows, rung, depth) {
  const px = (x, y) => {
    const i = (y * cols + x) * 4
    return [pixels[i], pixels[i + 1], pixels[i + 2]]
  }
  const grid = []
  for (let y = 0; y < rows; y++) {
    const line = []
    for (let x = 0; x < cols; x++) {
      if (rung === 'half') line.push({ ch: '▀', fg: termColor(px(x, 2 * y), depth), bg: termColor(px(x, 2 * y + 1), depth) })
      else line.push({ ch: ' ', fg: null, bg: termColor(px(x, y), depth) })
    }
    grid.push(line)
  }
  for (const t of text || []) {
    const y = Math.round(t.y)
    if (y < 0 || y >= rows) continue
    const chars = [...String(t.str)]
    chars.forEach((ch, k) => {
      const x = Math.round(t.x) + k
      if (x < 0 || x >= cols) return
      const under = grid[y][x]
      const bg = t.bg ? termColor(parseHex(t.bg), depth) : under.bg ?? under.fg
      grid[y][x] = { ch, fg: termColor(parseHex(t.fg), depth), bg }
    })
  }
  return grid
}

/** Merge horizontal runs of identical (fg, bg) into one string each (spike 13: node count). */
export function runs(line) {
  const out = []
  for (const c of line) {
    const last = out[out.length - 1]
    if (last && last.fg === c.fg && last.bg === c.bg) last.str += c.ch
    else out.push({ str: c.ch, fg: c.fg, bg: c.bg })
  }
  return out
}

/** Mantle height in cell rows: 2, or 1 under 30 terminal rows (D3, spike 02). */
export const mantleRows = termRows => (termRows < 30 ? 1 : 2)

export const PILL_COLS = 14
export const GRID_PER_ROW = 4

/** Layout of the identity grid in cell units: tile w/h and positions, relative to the dock box. */
export function gridLayout(cols, n) {
  const avail = cols - 2
  const tw = Math.floor((avail - (GRID_PER_ROW - 1)) / GRID_PER_ROW)
  const th = 2
  const tiles = []
  for (let i = 0; i < n; i++) {
    tiles.push({ session_idx: i, col: (i % GRID_PER_ROW) * (tw + 1), row: Math.floor(i / GRID_PER_ROW) * (th + 1), w: tw, h: th })
  }
  return { tw, th, tiles, width: GRID_PER_ROW * tw + (GRID_PER_ROW - 1), height: Math.ceil(n / GRID_PER_ROW) * (th + 1) - 1 }
}

// ---------------------------------------------------------------- host glue

function readScene() {
  try {
    return JSON.parse(fs.readFileSync(SCENE, 'utf8'))
  } catch (error) {
    return { error: String(error?.message ?? error) }
  }
}

const sessionFor = scene =>
  scene.view === 'degraded' ? fixture.degraded : fixture.sessions[scene.session_idx ?? 0] ?? fixture.sessions[0]

const stateFor = scene => (scene.view === 'degraded' ? 'unknown' : scene.state ?? 'idle')

function paintCells({ scale, cols, rows, state, session, t, scene }) {
  const pxH = scene.rung === 'half' ? rows * 2 : rows
  const direction = modules.get(scene.direction || DEFAULT_DIRECTION)
  if (!direction) throw new Error(`direction not loaded: ${scene.direction}`)
  const out = direction.paint({ scale, w: cols, h: pxH, state, session, t, opts: { reducedMotion: false, depth: scene.depth ?? 'truecolor' } })
  if (!out || !(out.pixels instanceof Uint8ClampedArray) || out.pixels.length !== cols * pxH * 4) {
    throw new Error(`direction.paint returned ${out?.pixels?.length} bytes, want ${cols * pxH * 4}`)
  }
  return toCells(out, cols, rows, scene.rung === 'half' ? 'half' : 'bg', scene.depth ?? 'truecolor')
}

export default function register(sdk) {
  const { Box, Text, React, defineWidgetApp, openWidget, updateWidget, h } = sdk
  const cleanups = []

  const Row = ({ line }) =>
    h(Box, { height: 1, flexShrink: 0 }, ...runs(line).map((r, i) => h(Text, { key: i, color: r.fg ?? undefined, backgroundColor: r.bg ?? undefined }, r.str)))

  const Block = ({ grid }) => h(Box, { flexDirection: 'column', flexShrink: 0 }, ...grid.map((line, y) => h(Row, { key: y, line })))

  const Ack = ({ scene, info, cols, termRows }) => {
    React.useEffect(() => {
      if (!ACK) return
      const tmp = `${ACK}.tmp`
      const direction = modules.get(scene.direction || DEFAULT_DIRECTION)
      fs.writeFileSync(tmp, JSON.stringify({
        seq: scene.seq ?? null, direction: direction?.meta?.id ?? null, view: scene.view, state: stateFor(scene),
        rung: scene.rung, depth: scene.depth, cols, term_rows: termRows, ...info, pid: process.pid,
      }))
      fs.renameSync(tmp, ACK)
    })
    return null
  }

  const app = defineWidgetApp({
    id: 'cfp1stub',
    help: 'cf2909 P1 host harness: renders a direction module (not the product)',
    mode: 'ambient',
    zone: 'dock-top',
    init: () => ({ scene: readScene(), frame: 0 }),  // a first scene naming another direction is loaded by poll()
    reduce: s => s,
    render: ctx => {
      try {
        return renderScene(ctx)
      } catch (error) {
        return h(Text, { color: 'red' }, `cf-p1 render error: ${String(error?.message ?? error)}`)
      }
    },
  })

  function renderScene({ cols, rows: termRows, state: st }) {
      const scene = st.scene
      if (scene.error) return h(Text, { color: 'red' }, `cf-p1 scene error: ${scene.error}`)
      const t = LIVE ? st.frame * 0.25 : Number(scene.frame_t ?? 0)
      const view = scene.view ?? 'mantle'
      let body
      let info
      if (view === 'mantle' || view === 'degraded') {
        const w = Math.max(1, cols - 2)
        const rows = mantleRows(termRows)
        body = h(Block, { grid: paintCells({ scale: 'M', cols: w, rows, state: stateFor(scene), session: sessionFor(scene), t, scene }) })
        info = { t, cells: [w, rows], box_cols: w }
      } else if (view === 'pill') {
        body = h(Block, { grid: paintCells({ scale: 'S', cols: PILL_COLS, rows: 1, state: stateFor(scene), session: sessionFor(scene), t, scene }) })
        info = { t, cells: [PILL_COLS, 1], box_cols: PILL_COLS }
      } else if (view === 'grid16' || view === 'grid20') {
        const n = view === 'grid16' ? 16 : 20
        const L = gridLayout(cols, n)
        const tileGrids = L.tiles.map(tile =>
          paintCells({ scale: 'S', cols: L.tw, rows: L.th, state: scene.state ?? 'idle', session: fixture.sessions[tile.session_idx], t, scene }))
        const lines = []
        for (let r = 0; r * GRID_PER_ROW < n; r++) {
          for (let y = 0; y < L.th; y++) {
            const line = []
            for (let c = 0; c < GRID_PER_ROW; c++) {
              const idx = r * GRID_PER_ROW + c
              if (idx >= n) break
              if (c) line.push({ ch: ' ', fg: null, bg: null })
              line.push(...tileGrids[idx][y])
            }
            lines.push(line)
          }
          if ((r + 1) * GRID_PER_ROW < n) lines.push([{ ch: ' ', fg: null, bg: null }])
        }
        body = h(Block, { grid: lines })
        info = { t, cells: [L.width, L.height], box_cols: L.width, tiles: L.tiles }
      } else {
        return h(Text, { color: 'red' }, `cf-p1 unknown view ${view}`)
      }
      return h(Box, { flexDirection: 'column', flexShrink: 0 }, body, h(Ack, { scene, info, cols, termRows }))
  }

  openWidget(app, app.init(''))

  // Scene switching: re-read when the scene file is replaced (drivers write tmp + rename).
  let last = ''
  const poll = () => {
    let raw = ''
    try { raw = fs.readFileSync(SCENE, 'utf8') } catch { return }
    if (raw === last) return
    last = raw
    const scene = readScene()
    const apply = () => updateWidget(app, s => ({ ...s, scene }))
    if (scene.direction && !modules.has(scene.direction)) {
      loadDirection(scene.direction).then(apply, error => updateWidget(app, s => ({ ...s, scene: { error: String(error?.message ?? error) } })))
    } else {
      apply()
    }
  }
  { const first = readScene(); if (first.direction && !modules.has(first.direction)) last = '' ; else try { last = fs.readFileSync(SCENE, 'utf8') } catch {} }
  poll()
  const watcher = fs.watch(path.dirname(SCENE), () => poll())
  cleanups.push(() => watcher.close())

  if (LIVE) {
    const timer = setInterval(() => updateWidget(app, s => ({ ...s, frame: s.frame + 1 })), 250)
    timer.unref?.()
    cleanups.push(() => clearInterval(timer))
  }

  globalThis[DISPOSE] = () => {
    for (const f of cleanups.splice(0)) try { f() } catch {}
    globalThis[DISPOSE] = undefined
  }
}
