/**
 * cf2909 P1 host (lane H): the REAL desktop plugin "Cuttlefish" that renders a direction module inside the
 * Hermes desktop app. NOT the product: a stub host so P1 direction renders come from real pixels.
 *
 * Surfaces (plan scales, P1-brief §2):
 *   XL  field pane      PANES_AREA, docked right of the conversation; a <canvas> painted at low internal
 *                       resolution (~1/4 of the pane, w*h <= 57600) and upscaled smoothly; text overlays as real DOM
 *                       text in CSS px
 *   M   status chip     STATUSBAR_AREAS.left; CHIP_COLS × 1 cells, painted like the TUI half rung
 *                       (2 logical px per cell, each CHIP_CELL_W × CHIP_CELL_H/2 CSS px), text as DOM
 *   S   row swatch      SESSION_ROW_AREAS.leading on every sidebar row whose stored id is a fixture lineage id
 *
 * Install: capture_matrix.py copies this file into a throwaway package `plugins/cuttlefish/desktop/plugin.js`
 * and replaces the DIRECTIONS marker below with every requested direction module INLINED. The desktop loader
 * only resolves `@hermes/plugin-sdk` / `react*` (runtime-loader.ts `unsupportedImports`: "a relative path cannot
 * resolve against the blob: base the module is evaluated from"), so import-by-path is impossible; directions are
 * pure no-import ESM (CONTRACT §2), which makes inlining exact. The fixture is inlined the same way.
 *
 * Scene switching (one Electron boot captures everything): `window.__cfP1.setScene(scene)` and
 * `ctx.storage` key `scene`. A scene is
 *   { seq, direction, state, session_idx, degraded, frame_t, rowState }
 * After every surface has painted that scene, `window.__cfP1.ack` becomes the scene's seq.
 */
import { host, PANES_AREA, SESSION_ROW_AREAS, STATUSBAR_AREAS, atom, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/*__CF_P1_INLINE_BEGIN__*/
const DIRECTIONS = {}
const FIXTURE = { sessions: [], degraded: { name: 'unbound', state: 'unknown', hue_deg: null, alarm_text: null } }
/*__CF_P1_INLINE_END__*/

const CHIP_COLS = 22
const CHIP_CELL_W = 8
const CHIP_CELL_H = 18
const SWATCH_COLS = 4
const SWATCH_CELL_W = 6
const SWATCH_CELL_H = 16

const $scene = atom({ seq: 0, direction: Object.keys(DIRECTIONS)[0] ?? null, state: 'idle', session_idx: 0, degraded: false, frame_t: 0 })
const painted = new Map() // surface key -> seq last painted

function probe() {
  const w = window
  if (!w.__cfP1) w.__cfP1 = { ack: 0, errors: [], loads: 0 }
  return w.__cfP1
}

function markPainted(key, seq, expected) {
  painted.set(key, seq)
  const p = probe()
  if ([...expected].every(k => painted.get(k) === seq)) p.ack = seq
}

const byLineage = new Map(FIXTURE.sessions.map(s => [s.lineage_id, s]))

function sceneSession(scene) {
  return scene.degraded ? FIXTURE.degraded : FIXTURE.sessions[scene.session_idx ?? 0] ?? FIXTURE.sessions[0]
}

const sceneState = scene => (scene.degraded ? 'unknown' : scene.state ?? 'idle')

/** XL budget (CONTRACT §2, D-R2-3): ~1/4 of the pane in CSS px, never more than 57 600 logical px (320×180). */
export const XL_MAX_PIXELS = 57600
export const XL_DIVISOR = 4
/** Desktop S swatches are 4×2 logical px; at w <= 8 the host never draws text overlays (D-R2-2). */
export const SWATCH_TEXT_MAX_W = 8

export function xlPaintSize(cssW, cssH) {
  let w = Math.max(1, Math.ceil(cssW / XL_DIVISOR))
  let h = Math.max(1, Math.ceil(cssH / XL_DIVISOR))
  if (w * h > XL_MAX_PIXELS) {
    const k = Math.sqrt(XL_MAX_PIXELS / (w * h))
    w = Math.max(1, Math.floor(w * k))
    h = Math.max(1, Math.floor(h * k))
    while (w * h > XL_MAX_PIXELS) { if (w >= h) w--; else h-- }
  }
  return { w, h }
}

/**
 * Paint one surface into `canvas`. For XL, `w`/`h` are the pane's CSS px: the direction is painted at the low
 * internal size (xlPaintSize) and the canvas is upscaled by the compositor with smoothing (`image-rendering: auto`).
 * M and S paint 1 logical px : 1 canvas px and are shown pixelated. Returns the text overlays to draw.
 */
export function paintInto(canvas, dir, { scale, w, h, state, session, t }) {
  const css = { w, h }
  if (scale === 'XL') ({ w, h } = xlPaintSize(css.w, css.h))
  const out = dir.paint({ scale, w, h, state, session, t, opts: { reducedMotion: false, depth: 'truecolor', cssW: css.w, cssH: css.h } })
  if (!out || out.pixels?.length !== w * h * 4) throw new Error(`paint returned ${out?.pixels?.length} bytes, want ${w * h * 4}`)
  canvas.width = w
  canvas.height = h
  if (canvas.style) canvas.style.imageRendering = scale === 'XL' ? 'auto' : 'pixelated'
  const ctx2d = canvas.getContext('2d')
  ctx2d.putImageData(new ImageData(new Uint8ClampedArray(out.pixels), w, h), 0, 0)
  if (scale === 'S' && w <= SWATCH_TEXT_MAX_W) return []
  return out.text || []
}

/** Text overlays as real DOM characters. `unit` = [px per x, px per y] (cells for M/S, 1 for XL). */
function Overlays({ text, unit, font }) {
  return text.map((t, i) =>
    jsx('span', {
      key: i,
      'data-cf-text': t.str,
      style: {
        position: 'absolute', left: t.x * unit[0], top: t.y * unit[1], whiteSpace: 'pre', color: t.fg,
        background: t.bg ?? 'transparent', font, lineHeight: `${unit[1] === 1 ? 'normal' : unit[1] + 'px'}`,
        letterSpacing: 0, pointerEvents: 'none',
      },
      children: t.str,
    }))
}

/** One painted surface: canvas scaled by CSS (XL smooth, M/S pixelated; set in paintInto) + overlays. */
function Surface({ surfaceKey, expected, scale, cols, rows, pxPerCell, cellW, cellH, scene, session, state, testId, font }) {
  const ref = useRef(null)
  const [text, setText] = useState([])
  const dir = DIRECTIONS[scene.direction]
  useLayoutEffect(() => {
    if (!ref.current || !dir) return
    try {
      setText(paintInto(ref.current, dir, { scale, w: cols, h: rows * pxPerCell, state, session, t: Number(scene.frame_t ?? 0) }))
    } catch (error) {
      probe().errors.push(`${surfaceKey}: ${String(error?.message ?? error)}`)
    }
  }, [dir, scene.seq, session?.lineage_id, state, cols, rows])
  useEffect(() => {
    // Two frames: the canvas + overlay commit is on screen before the harness screenshots.
    const id = requestAnimationFrame(() => requestAnimationFrame(() => markPainted(surfaceKey, scene.seq, expected)))
    return () => cancelAnimationFrame(id)
  }, [scene.seq, text])
  return jsxs('span', {
    'data-testid': testId,
    'data-cf-session': session?.name ?? '',
    'data-cf-seq': scene.seq,
    style: { position: 'relative', display: 'inline-block', width: cols * cellW, height: rows * cellH, flexShrink: 0, overflow: 'hidden', verticalAlign: 'middle' },
    children: [
      jsx('canvas', { ref, style: { position: 'absolute', inset: 0, width: '100%', height: '100%' } }),
      jsx(Overlays, { text, unit: [cellW, cellH], font }),
    ],
  })
}

const CHIP_FONT = `12px "DejaVu Sans Mono", monospace`

function Chip() {
  const scene = useValue($scene)
  return jsx(Surface, {
    surfaceKey: 'chip', expected: EXPECTED, scale: 'M', cols: CHIP_COLS, rows: 1, pxPerCell: 2, cellW: CHIP_CELL_W, cellH: CHIP_CELL_H,
    scene, session: sceneSession(scene), state: sceneState(scene), testId: 'cf-p1-chip', font: CHIP_FONT,
  })
}

function Swatch({ sessionId }) {
  const scene = useValue($scene)
  const s = byLineage.get(sessionId)
  if (!s) return null
  // The scene's own row shows the scene look (degraded included); every other row shows rowState (identity view).
  const own = s.idx === (scene.session_idx ?? 0)
  const session = own && scene.degraded ? FIXTURE.degraded : s
  const state = own ? sceneState(scene) : scene.rowState ?? sceneState(scene)
  return jsx(Surface, {
    surfaceKey: `swatch:${s.idx}`, expected: EXPECTED, scale: 'S', cols: SWATCH_COLS, rows: 1, pxPerCell: 2,
    cellW: SWATCH_CELL_W, cellH: SWATCH_CELL_H, scene, session, state, testId: `cf-p1-swatch-${s.idx}`, font: CHIP_FONT,
  })
}

function Field() {
  const scene = useValue($scene)
  const box = useRef(null)
  const [size, setSize] = useState(null)
  useLayoutEffect(() => {
    if (!box.current) return
    const ro = new ResizeObserver(() => {
      const r = box.current.getBoundingClientRect()
      setSize({ w: Math.max(1, Math.floor(r.width)), h: Math.max(1, Math.floor(r.height)) })
    })
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])
  return jsx('div', {
    ref: box,
    'data-testid': 'cf-p1-field-box',
    style: { position: 'absolute', inset: 0, overflow: 'hidden', background: '#000' },
    children: size && jsx(Surface, {
      surfaceKey: 'field', expected: EXPECTED, scale: 'XL', cols: size.w, rows: size.h, pxPerCell: 1, cellW: 1, cellH: 1,
      scene, session: sceneSession(scene), state: sceneState(scene), testId: 'cf-p1-field', font: `600 20px "DejaVu Sans", sans-serif`,
    }),
  })
}

// The surfaces that must have painted a scene before it is acked: field, chip, and every visible swatch.
const EXPECTED = new Set(['field', 'chip'])

export default {
  id: 'cuttlefish',
  name: 'Cuttlefish',
  register(ctx) {
    const p = probe()
    p.loads++
    p.directions = Object.fromEntries(Object.entries(DIRECTIONS).map(([k, d]) => [k, d.meta ?? null]))
    p.fixtureSessions = FIXTURE.sessions.length
    p.setScene = scene => {
      const next = { ...scene, seq: scene.seq ?? $scene.get().seq + 1 }
      painted.clear()
      p.ack = 0
      // Swatches only exist for rows currently mounted; the harness passes which ones it will crop.
      EXPECTED.clear()
      EXPECTED.add('field').add('chip')
      for (const idx of next.expectSwatches ?? []) EXPECTED.add(`swatch:${idx}`)
      $scene.set(next)
      Promise.resolve(ctx.storage?.set?.('scene', next)).catch(() => undefined)
      return next.seq
    }
    p.revealField = () => host.revealPane?.('cuttlefish:field')
    ctx.register({
      id: 'field', area: PANES_AREA, title: 'Cuttlefish field',
      data: { placement: 'right', dock: { pane: 'workspace', pos: 'right' }, width: '720px', minWidth: '480px' },
      render: () => jsx(Field, {}),
    })
    ctx.register({ id: 'chip', area: STATUSBAR_AREAS.left, order: 1, render: () => jsx(Chip, {}) })
    ctx.register({ id: 'swatch', area: SESSION_ROW_AREAS.leading, data: { render: props => jsx(Swatch, props) } })
  },
}
