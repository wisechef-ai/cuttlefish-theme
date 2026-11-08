// Unit: the v2.1 state marks (row swatch 24×16, status strip 21×14) — what the eye reads at a glance.
// Spec: docs/design/IMPLEMENTATION.md §1 (ink), §2 (geometry), §6 (the tests these are).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { GLYPH_H, GLYPH_W, glyphExtras, glyphOf, STRIP_K } from '../../src/domain/glyph.ts'
import { contrast, palette } from '../../src/domain/ink.ts'
import { allocate, DEFAULT_SETTINGS, patternOf, renderStrip, renderSwatch } from '../../src/domain/index.ts'
import { hexToRgb, rgbToOklab } from '../../src/domain/oklch.ts'
import { PATTERN_KINDS, type PatternKind } from '../../src/domain/types.ts'

const STATES: PatternKind[] = ['mottle', 'clouds', 'zebra', 'blanch', 'eyespot']
const GROUNDS = ['#fefefe', '#141416', '#2e3440']
const HUES = [100, 150, 205, 260, 310, 350]
/** The design rows (light / dark / nord, unselected and selected) — the WCAG 1.4.11 backgrounds the marks must hold on. */
const ROWS = ['#f6f8fa', '#d8e1f0', '#17181c', '#2a3142', '#2e3440', '#434c5e']

const swatch = (seed: string, state: string, intensity = 1) =>
  renderSwatch({ seed, hueDeg: allocate(seed, []).hue_deg, ground: '#fefefe', pattern: patternOf(DEFAULT_SETTINGS, state), intensity })

function chromaOf(hex: string): number {
  const lab = rgbToOklab(hexToRgb(hex))
  return Math.hypot(lab.a, lab.b)
}
function hueOf(hex: string): number {
  const lab = rgbToOklab(hexToRgb(hex))
  return (Math.atan2(lab.b, lab.a) * 180) / Math.PI
}
const hueGap = (a: number, b: number): number => { const d = Math.abs(a - b) % 360; return Math.min(d, 360 - d) }

test('every dot and extra of every state lies inside the 24×16 box (±0.5); the strip inside 21×14', () => {
  assert.equal(GLYPH_W, 24)
  assert.equal(GLYPH_H, 16)
  assert.equal(STRIP_K, 0.875)
  for (const base of STATES) {
    for (const d of glyphOf(base)) {
      assert.ok(d.x - d.r >= -0.5 && d.x + d.r <= GLYPH_W + 0.5 && d.y - d.r >= -0.5 && d.y + d.r <= GLYPH_H + 0.5, `${base} dot leaves the box`)
    }
    for (const e of glyphExtras(base)) {
      if (e.k === 'rect') {
        const [x, y, w, h] = [e.x ?? 0, e.y ?? 0, e.w ?? 0, e.h ?? 0]
        assert.ok(x >= 0 && x + w <= GLYPH_W && y >= 0 && y + h <= GLYPH_H, `${base} rect leaves the box`)
      }
      if (e.k === 'ellipse') {
        const [cx, cy, rx, ry] = [e.cx ?? 0, e.cy ?? 0, e.rx ?? 0, e.ry ?? 0]
        assert.ok(cx - rx >= 0 && cx + rx <= GLYPH_W && cy - ry >= 0 && cy + ry <= GLYPH_H, `${base} ellipse leaves the box`)
      }
    }
    assert.equal(swatch('s', 'needs_you').width, GLYPH_W)
    assert.equal(swatch('s', 'needs_you').height, GLYPH_H)
    const strip = renderStrip({ seed: 's', hueDeg: 200, ground: '#fefefe', pattern: patternOf(DEFAULT_SETTINGS, 'needs_you'), intensity: 1 })
    assert.equal(strip.width, 21)
    assert.equal(strip.height, 14)
    assert.ok(strip.dots.every(d => d.x - d.r >= -0.5 && d.x + d.r <= 21.5 && d.y - d.r >= -0.5 && d.y + d.r <= 14.5), 'strip dots inside 21×14')
  }
})

/** Scanline raster of a state's ink on a 96×64 grid (the 24×16 box at ×4). Circles and extras are drawn in SVG order:
 *  below-extras, dots, above-extras; a paper-coloured extra clears what is under it; pale plates (fill < 1) are skipped. */
function raster(base: PatternKind): boolean[] {
  const S = 4, W = 96, H = 64
  const out = new Array<boolean>(W * H).fill(false)
  const paint = (cover: (x: number, y: number) => boolean, paper: boolean, px: number, py: number) => {
    if (cover(px, py)) out[py * W + px] = !paper
  }
  const inRoundRect = (e: { x: number; y: number; w: number; h: number; rx?: number }, x: number, y: number) => {
    if (x < e.x || x > e.x + e.w || y < e.y || y > e.y + e.h) return false
    const r = Math.min(e.rx ?? 0, e.w / 2, e.h / 2)
    const cx = Math.min(Math.max(x, e.x + r), e.x + e.w - r), cy = Math.min(Math.max(y, e.y + r), e.y + e.h - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
  }
  const segDist = (x: number, y: number, a: [number, number], b: [number, number]) => {
    const [dx, dy] = [b[0] - a[0], b[1] - a[1]]
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy || 1)))
    return Math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))
  }
  const pathPts = (d: string): Array<[number, number]> => {
    const pts: Array<[number, number]> = []
    let cur: [number, number] = [0, 0]
    for (const cmd of d.matchAll(/([MHVL])\s*([-\d.\s]*)/g)) {
      const nums = cmd[2].trim().split(/\s+/).filter(Boolean).map(Number)
      if (cmd[1] === 'M' || cmd[1] === 'L') for (let i = 0; i < nums.length; i += 2) { cur = [nums[i], nums[i + 1]]; pts.push(cur) }
      if (cmd[1] === 'H') for (const x of nums) { cur = [x, cur[1]]; pts.push(cur) }
      if (cmd[1] === 'V') for (const y of nums) { cur = [cur[0], y]; pts.push(cur) }
    }
    return pts
  }
  const layers = glyphExtras(base)
  const dots = glyphOf(base)
  const drawExtra = (e: ReturnType<typeof glyphExtras>[number]) => {
    const paper = e.pigment === 'paper'
    const pale = !paper && !e.stroke && (e.alpha ?? 1) < 1
    if (pale) return
    for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) {
      const x = (px + 0.5) / S, y = (py + 0.5) / S
      let hit: boolean
      if (e.k === 'rect') hit = e.stroke ? false : inRoundRect({ x: e.x ?? 0, y: e.y ?? 0, w: e.w ?? 0, h: e.h ?? 0, rx: e.rx }, x, y)
      else if (e.k === 'ellipse') {
        const [cx, cy, rx, ry] = [e.cx ?? 0, e.cy ?? 0, e.rx ?? 1, e.ry ?? 1]
        const q = Math.hypot((x - cx) / rx, (y - cy) / ry)
        hit = e.stroke ? Math.abs(q - 1) * Math.min(rx, ry) <= e.stroke / 2 : q <= 1
      } else {
        const pts = pathPts(e.d ?? '')
        const half = (e.stroke ?? 0) / 2
        hit = pts.slice(1).some((p, i) => segDist(x, y, pts[i], p) <= half)
      }
      paint(() => hit, paper, px, py)
    }
  }
  layers.filter(e => !e.above).forEach(drawExtra)
  for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) {
    const x = (px + 0.5) / S, y = (py + 0.5) / S
    if (dots.some(d => (x - d.x) ** 2 + (y - d.y) ** 2 <= d.r * d.r)) out[py * W + px] = true
  }
  layers.filter(e => e.above).forEach(drawExtra)
  return out
}

test('five silhouettes at 1×: pairwise IoU ≤ 0.55, and error vs finished-unseen ≤ 0.30', () => {
  const masks = Object.fromEntries(STATES.map(s => [s, raster(s)])) as Record<string, boolean[]>
  const iou = (a: boolean[], b: boolean[]) => {
    let inter = 0, uni = 0
    for (let i = 0; i < a.length; i++) { if (a[i] && b[i]) inter++; if (a[i] || b[i]) uni++ }
    return uni === 0 ? 0 : inter / uni
  }
  for (let i = 0; i < STATES.length; i++) for (let j = i + 1; j < STATES.length; j++) {
    const v = iou(masks[STATES[i]], masks[STATES[j]])
    assert.ok(v <= 0.55, `${STATES[i]} vs ${STATES[j]}: IoU ${v.toFixed(2)}`)
  }
  assert.ok(iou(masks.blanch, masks.eyespot) <= 0.30, `error vs finished: ${iou(masks.blanch, masks.eyespot).toFixed(2)}`)
})

test('WCAG 1.4.11: every mark pigment is ≥ 3.2:1 on every design row, selected or not; paper and pupil hold their own contrast', () => {
  const rowsOf: Record<string, string[]> = { '#fefefe': ROWS.slice(0, 2), '#141416': ROWS.slice(2, 4), '#2e3440': ROWS.slice(4) }
  for (const ground of GROUNDS) for (const hue of HUES) {
    const pal = palette(hue, ground)
    for (const row of rowsOf[ground]) for (const p of ['chroma', 'soft', 'blanch'] as const) {
      assert.ok(contrast(pal[p], row) >= 3.2, `${p} on ${row} (ground ${ground}, hue ${hue}): ${contrast(pal[p], row).toFixed(2)}`)
    }
    assert.ok(contrast(pal.paper, pal.chroma) >= 3.5, `paper vs chroma on ${ground}`)
    assert.ok(contrast(pal.spot, pal.chroma) >= 3.0, `pupil vs iris on ${ground}`)
  }
})

test('error is the only grey mark: its organs are near-achromatic, every other state keeps the identity hue (within 10°)', () => {
  for (const hue of [0, 45, 90, 135, 180, 225, 270, 315, 357]) {
    const seed = `hue-${hue}`
    const sw = (base: string) => renderSwatch({ seed, hueDeg: hue, ground: '#141416', pattern: patternOf(DEFAULT_SETTINGS, base === 'blanch' ? 'error' : base === 'mottle' ? 'resting' : base === 'clouds' ? 'working' : base === 'zebra' ? 'needs_you' : 'finished_unseen'), intensity: 1 })
    const err = sw('blanch').dots.filter(d => d.role === 'organ')
    const mean = err.reduce((s, d) => s + chromaOf(d.color), 0) / err.length
    assert.ok(mean <= 0.03, `error mean chroma ${mean.toFixed(3)} at hue ${hue}`)
    for (const base of ['mottle', 'clouds', 'zebra', 'eyespot']) {
      for (const d of sw(base).dots.filter(x => x.role === 'organ')) {
        assert.ok(hueGap(hueOf(d.color), hue) <= 10, `${base} organ hue ${hueOf(d.color).toFixed(1)} vs ${hue}`)
      }
    }
  }
})

test('finished-unseen: exactly one eye-spot dot (core r 4.5, ≥ 7× the median organ radius), a pale disc and a ring BELOW the dots; error: a plate and an open frame with the top-right corner empty', () => {
  const eye = glyphOf('eyespot')
  const spots = eye.filter(d => d.pigment === 'spot')
  assert.equal(spots.length, 1, 'one eye-spot')
  assert.equal(spots[0].r, 4.5)
  const organR = eye.filter(d => d.pigment !== 'spot').map(d => d.r)
  assert.ok(spots[0].r >= 7 * organR.sort((a, b) => a - b)[organR.length >> 1], 'the core dwarfs the flecks')
  const ex = glyphExtras('eyespot')
  assert.ok(ex.some(e => e.k === 'ellipse' && e.rx === 7 && !e.stroke && e.alpha === 0.3 && !e.above), 'a pale disc below')
  assert.ok(ex.some(e => e.k === 'ellipse' && e.rx === 7 && e.stroke === 1.6 && !e.above), 'a crisp ring below')
  const err = glyphExtras('blanch')
  assert.ok(!err.some(e => e.k === 'ellipse'), 'error has no ellipse')
  const plate = err.find(e => e.k === 'rect')
  assert.ok(plate && plate.alpha === 0.14, 'error has a pale plate')
  const frame = err.find(e => e.k === 'path')!
  assert.match(frame.d ?? '', /^M[\d. ]+(?:[HV][\d. ]+)+$/, 'the frame is M H V only')
  const pts = [...(frame.d ?? '').matchAll(/([HV])\s*([\d.]+)|M\s*([\d.]+)\s+([\d.]+)/g)]
  let x = 0, y = 0
  const verts: Array<[number, number]> = []
  for (const m of pts) {
    if (m[3] !== undefined) { x = Number(m[3]); y = Number(m[4]) }
    else if (m[1] === 'H') x = Number(m[2]); else y = Number(m[2])
    verts.push([x, y])
  }
  assert.notDeepEqual(verts[0], verts[verts.length - 1], 'open: the frame does not close')
  assert.ok(!verts.some(([vx, vy]) => vx > 13.2 && vy < 9.9), 'the top-right corner is missing')
})

test('the swatch is opaque (intensity 0 switches it off); the strip is the swatch × 0.875', () => {
  const on = swatch('s', 'needs_you', 1)
  const visible = on.dots.filter(d => d.r > 0)
  assert.ok(visible.every(d => d.alpha === 1), 'opaque dots')
  assert.ok(swatch('s', 'needs_you', 0).dots.every(d => d.alpha === 0), 'intensity 0 switches the glyph off')
  const strip = renderStrip({ seed: 's', hueDeg: allocate('s', []).hue_deg, ground: '#fefefe', pattern: patternOf(DEFAULT_SETTINGS, 'needs_you'), intensity: 1 })
  assert.equal(strip.dots.length, on.dots.length)
  strip.dots.forEach((d, i) => {
    const s = on.dots[i]
    assert.ok(Math.abs(d.x - s.x * STRIP_K) < 1e-9 && Math.abs(d.y - s.y * STRIP_K) < 1e-9 && Math.abs(d.r - s.r * STRIP_K) < 1e-9, `dot ${i} is scaled`)
    assert.equal(d.color, s.color)
  })
})

test('extras are never circles: every extra is a rect, an ellipse or a path', () => {
  for (const base of PATTERN_KINDS) for (const e of glyphExtras(base)) {
    assert.ok(['rect', 'ellipse', 'path'].includes(e.k), `${base} extra ${e.k}`)
  }
  const sw = swatch('s', 'finished_unseen')
  assert.ok(sw.extras.length >= 2 && sw.extras.every(e => e.tag === 'rect' || e.tag === 'ellipse' || e.tag === 'path'))
})

test('coarse features at 1×: resting is one blob; working a flat-bottomed cloud; needs you a filled chip with paper bars; error hollow', () => {
  const rest = glyphOf('mottle')
  for (let i = 0; i + 1 < rest.length; i++) {
    assert.ok(Math.hypot(rest[i].x - rest[i + 1].x, rest[i].y - rest[i + 1].y) < rest[i].r + rest[i + 1].r, 'neighbouring resting dots overlap into one oval')
  }
  const xs = rest.flatMap(d => [d.x - d.r, d.x + d.r]), ys = rest.flatMap(d => [d.y - d.r, d.y + d.r])
  assert.ok(Math.max(...xs) - Math.min(...xs) <= 13 && Math.max(...ys) - Math.min(...ys) <= 7, 'a small oval, smaller than the cloud')
  const cloud = glyphExtras('clouds')
  assert.ok(cloud.some(e => e.k === 'rect' && !e.above), 'working: a flat bottom below')
  assert.ok(glyphOf('clouds').filter(d => d.r >= 4).length >= 3, 'and three big lobes')
  const chip = glyphExtras('zebra')
  assert.ok(chip.some(e => e.k === 'rect' && e.alpha === 1 && e.fill && !e.stroke && !e.above), 'needs you: a filled plate below')
  const bars = chip.filter(e => e.k === 'path' && e.pigment === 'paper' && e.above)
  assert.equal(bars.length, 3, 'three paper bars above')
  const err = glyphExtras('blanch')
  assert.ok(!err.some(e => e.alpha === 1 && e.fill && (e.pigment === 'chroma' || e.pigment === 'blanch')), 'error is hollow: no solid plate')
  assert.ok(glyphOf('blanch').every(d => d.pigment === 'blanch'), 'error dots are the pale pigment')
})

test('the swatch shape is the state and the hue is the identity: same geometry for every session, different ink', () => {
  const a = swatch('s-one', 'needs_you').dots.map(d => [d.x, d.y, d.r])
  const b = swatch('s-two', 'needs_you').dots.map(d => [d.x, d.y, d.r])
  assert.deepEqual(a, b, 'state is shape')
  assert.notDeepEqual(swatch('s-one', 'needs_you').dots.map(d => d.color), swatch('s-two', 'needs_you').dots.map(d => d.color), 'identity is hue')
})
