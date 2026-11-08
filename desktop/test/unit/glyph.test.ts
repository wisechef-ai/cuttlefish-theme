// Unit: the v2.1 state marks (row swatch 24×16, status strip 21×14) — what the eye reads at a glance.
// Spec: docs/design/IMPLEMENTATION.md §1 (ink), §2 (geometry), §6 (the tests these are).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { GLYPH_H, GLYPH_W, glyphExtras, glyphOf, type GlyphExtra, STRIP_K } from '../../src/domain/glyph.ts'
import { contrast, palette } from '../../src/domain/ink.ts'
import { allocate, DEFAULT_SETTINGS, patternOf, renderStrip, renderSwatch } from '../../src/domain/index.ts'
import { composite, hexToRgb, rgbToHex, rgbToOklab } from '../../src/domain/oklch.ts'
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

// §4d ruling 1 and 4: the resting and error inks are set to 3.35 (the measured dark-selected floor is 3.10), so their bar is the 3.05 of §4d
test('WCAG 1.4.11: every mark pigment is ≥ 3.2:1 on every design row (chroma), ≥ 3.05:1 for the quiet resting and pale error inks (§4d); paper and pupil hold their own contrast', () => {
  const rowsOf: Record<string, string[]> = { '#fefefe': ROWS.slice(0, 2), '#141416': ROWS.slice(2, 4), '#2e3440': ROWS.slice(4) }
  for (const ground of GROUNDS) for (const hue of HUES) {
    const pal = palette(hue, ground)
    for (const row of rowsOf[ground]) {
      assert.ok(contrast(pal.chroma, row) >= 3.2, `chroma on ${row} (ground ${ground}, hue ${hue}): ${contrast(pal.chroma, row).toFixed(2)}`)
      for (const p of ['soft', 'blanch'] as const) assert.ok(contrast(pal[p], row) >= 3.05, `${p} on ${row} (ground ${ground}, hue ${hue}): ${contrast(pal[p], row).toFixed(2)}`)
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

// §4c (changed by r4 from v2.1): the eye is an almond with a pupil of r 2.8 over two corner flecks of r 0.7 (ratio 4.0 ≥ 2), the
// iris ring and the lens. The corner-gap check moved with the frame (the r4 frame ends its right edge at y 9).
test('finished-unseen: exactly one eye-spot dot (pupil r 2.8, ≥ 2× the median organ fleck), a pale lens and an iris ring BELOW; error: a plate and an open frame with the top-right corner empty', () => {
  const eye = glyphOf('eyespot')
  const spots = eye.filter(d => d.pigment === 'spot')
  assert.equal(spots.length, 1, 'one eye-spot')
  assert.equal(spots[0].r, 2.8)
  const organR = eye.filter(d => d.pigment !== 'spot').map(d => d.r)
  assert.ok(spots[0].r >= 2 * organR.sort((a, b) => a - b)[organR.length >> 1], 'the pupil dwarfs the flecks (spotRatios first ≥ 2)')
  const ex = glyphExtras('eyespot')
  assert.ok(ex.some(e => e.k === 'path' && e.alpha === 0.3 && !e.above), 'a pale lens below')
  assert.ok(ex.some(e => e.k === 'ellipse' && e.rx === 4.4 && e.stroke === 1.5 && !e.above), 'an iris ring below')
  const err = glyphExtras('blanch')
  assert.ok(!err.some(e => e.k === 'ellipse'), 'error has no ellipse')
  const plate = err.find(e => e.k === 'rect')
  assert.ok(plate && plate.alpha === 0.24, 'error has a pale plate (r5: chroma at .24)')
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
  assert.ok(!verts.some(([vx, vy]) => vx > 13 && vy < 9), 'the top-right corner is missing')
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

// §4c (changed by r4 from v2.1): resting is an UPRIGHT oval (taller than wide), working a WIDE cloud on a flat base, needs you a
// filled chip with TWO bars, error still hollow. The lobe radii grew (3.3/4.4/3.1), so the lobe count test is ≥ 3 at r ≥ 3.
test('coarse features at 1×: resting is one upright oval; working a wide cloud on a flat base; needs you a filled chip with two paper bars; error hollow', () => {
  const rest = glyphOf('mottle')
  for (let i = 0; i + 1 < rest.length; i++) {
    assert.ok(Math.hypot(rest[i].x - rest[i + 1].x, rest[i].y - rest[i + 1].y) < rest[i].r + rest[i + 1].r, 'neighbouring resting dots overlap into one oval')
  }
  const box = (ds: readonly { x: number; y: number; r: number }[]) => {
    const xs = ds.flatMap(d => [d.x - d.r, d.x + d.r]), ys = ds.flatMap(d => [d.y - d.r, d.y + d.r])
    return { w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }
  }
  const r = box(rest), c = box(glyphOf('clouds'))
  assert.ok(r.h > r.w, `resting is upright (${r.w.toFixed(1)} × ${r.h.toFixed(1)})`)
  assert.ok(c.w > c.h, `working is wide (${c.w.toFixed(1)} × ${c.h.toFixed(1)})`)
  assert.ok(glyphExtras('clouds').some(e => e.k === 'rect' && !e.above), 'working: a flat base below')
  assert.ok(glyphOf('clouds').filter(d => d.r >= 3).length >= 3, 'and three lobes of r ≥ 3')
  const chip = glyphExtras('zebra')
  assert.ok(chip.some(e => e.k === 'rect' && e.alpha === 1 && e.fill && !e.stroke && !e.above), 'needs you: a filled plate below')
  assert.equal(chip.filter(e => e.k === 'path' && e.pigment === 'paper' && e.above).length, 2, 'two paper bars above')
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

// v2.1 round r4 (§4c, rulings 1–6): the marks as the r4 patch draws them. Written first; each fails on 08e7d74.
const projDot = (d: { x: number; y: number; r: number; pigment: string }) => [d.x, d.y, d.r, d.pigment]
const projExtra = (e: GlyphExtra) => [e.k, e.pigment, e.above === true, e.fill === true, e.alpha ?? null, e.stroke ?? null,
  e.x ?? e.cx ?? null, e.y ?? e.cy ?? null, e.w ?? e.rx ?? null, e.h ?? e.ry ?? null, e.rx ?? null, e.d ?? null]

// The exact lists of the r4 marks; the resting mark and the error mark are the r5 values (§4d rulings 1 and 4).
test('r4/r5 marks: the exact dot and extra lists', () => {
  assert.deepEqual(glyphOf('mottle').map(projDot), [[12, 5.4, 5.1, 'soft'], [12, 8, 5.9, 'soft'], [12, 10.6, 5.1, 'soft']], 'resting: one upright oval (r5)')
  assert.deepEqual(glyphExtras('mottle').map(projExtra), [
    ['ellipse', 'paper', true, true, 0.9, null, 10.4, 5.2, 1, 1, 1, null],
    ['ellipse', 'paper', true, true, 0.9, null, 13.6, 8.4, 1.1, 1.1, 1.1, null],
    ['ellipse', 'paper', true, true, 0.9, null, 10.8, 11.2, 0.9, 0.9, 0.9, null]], 'and three paper holes above (r5)')
  assert.deepEqual(glyphOf('clouds').map(projDot), [[6.8, 9.6, 3.3, 'chroma'], [12.4, 7.8, 4.4, 'chroma'], [17.6, 9.8, 3.1, 'chroma']], 'working: three lobes')
  assert.deepEqual(glyphExtras('clouds').map(projExtra), [['rect', 'chroma', false, true, 1, null, 3.8, 9.8, 16.2, 3.9, 1.9, null]], 'and a flat base')
  assert.deepEqual(glyphOf('zebra').map(projDot), [[6, 5.5, 2.8, 'chroma'], [12, 5.5, 2.8, 'chroma'], [18, 5.5, 2.8, 'chroma'],
    [6, 10.5, 2.8, 'chroma'], [12, 10.5, 2.8, 'chroma'], [18, 10.5, 2.8, 'chroma']], 'needs you: six dots')
  const z = glyphExtras('zebra')
  assert.deepEqual(z.map(projExtra), [
    ['rect', 'chroma', false, true, 1, null, 2.5, 2, 19, 12, 3, null],
    ['path', 'paper', true, false, null, 3.4, null, null, null, null, null, 'M4 12 L12 4'],
    ['path', 'paper', true, false, null, 3.4, null, null, null, null, null, 'M11.5 12 L19.5 4']], 'a filled chip with exactly TWO bars')
  // the r5 error mark (§4d ruling 1) is asserted in its own test below
  const eye = glyphOf('eyespot')
  assert.deepEqual(eye.map(projDot), [[3, 8, 0.7, 'chroma'], [21, 8, 0.7, 'chroma'], [12, 8, 2.8, 'spot']], 'eye: two corner dots, the pupil LAST')
  assert.deepEqual(glyphExtras('eyespot').map(projExtra), [
    ['path', 'chroma', false, true, 0.3, null, null, null, null, null, null, 'M2 8 Q12 -2 22 8 Q12 18 2 8 Z'],
    ['path', 'chroma', false, false, null, 1.6, null, null, null, null, null, 'M2 8 Q12 -2 22 8 Q12 18 2 8 Z'],
    ['ellipse', 'chroma', false, false, null, 1.5, 12, 8, 4.4, 4.4, 4.4, null],
    ['ellipse', 'paper', true, true, 1, null, 13.3, 6.6, 0.9, 0.9, 0.9, null]], 'an almond with an iris ring and a catch-light')
})

/** Top-level path and segment helpers (M, H, V, L, Q sampled along the curve, Z ignored: the lens closes on its start). */
function segDist(x: number, y: number, a: [number, number], b: [number, number]): number {
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]]
  const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy || 1)))
  return Math.hypot(x - (a[0] + t * dx), y - (a[1] + t * dy))
}
function pathPts(d: string): Array<[number, number]> {
  const pts: Array<[number, number]> = []
  let cur: [number, number] = [0, 0]
  for (const cmd of d.matchAll(/([MHVLQZ])\s*([-\d.\s]*)/g)) {
    const nums = cmd[2].trim().split(/\s+/).filter(Boolean).map(Number)
    if (cmd[1] === 'M' || cmd[1] === 'L') for (let i = 0; i + 1 < nums.length; i += 2) { cur = [nums[i], nums[i + 1]]; pts.push(cur) }
    if (cmd[1] === 'Q') for (let i = 0; i + 3 < nums.length; i += 4) {
      const [p0, c, p1] = [cur, [nums[i], nums[i + 1]], [nums[i + 2], nums[i + 3]]] as const
      for (let k = 1; k <= 12; k++) {
        const t = k / 12, u = 1 - t
        pts.push([u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]])
      }
      cur = [p1[0], p1[1]]
    }
    if (cmd[1] === 'H') for (const x of nums) { cur = [x, cur[1]]; pts.push(cur) }
    if (cmd[1] === 'V') for (const y of nums) { cur = [cur[0], y]; pts.push(cur) }
  }
  return pts
}

/** Every sample composited layer by layer in its real colour (pale fills at their alpha included), 96×64 at 4× per design px. */
function inkColours(base: PatternKind, ground: string, hue: number): Array<{ r: number; g: number; b: number }> {
  const pal = palette(hue, ground)
  const bg = hexToRgb(ground)
  const S = 4, W = 96, H = 64
  const col: Array<{ r: number; g: number; b: number }> = new Array(W * H).fill(bg)
  const hit = (e: GlyphExtra, x: number, y: number): boolean => {
    if (e.k === 'rect') {
      const rx = e.rx ?? 0, cx = Math.min(Math.max(x, (e.x ?? 0) + rx), (e.x ?? 0) + (e.w ?? 0) - rx)
      const cy = Math.min(Math.max(y, (e.y ?? 0) + rx), (e.y ?? 0) + (e.h ?? 0) - rx)
      return x >= (e.x ?? 0) && x <= (e.x ?? 0) + (e.w ?? 0) && y >= (e.y ?? 0) && y <= (e.y ?? 0) + (e.h ?? 0) && (x - cx) ** 2 + (y - cy) ** 2 <= rx * rx
    }
    if (e.k === 'ellipse') {
      const q = Math.hypot((x - (e.cx ?? 0)) / (e.rx ?? 1), (y - (e.cy ?? 0)) / (e.ry ?? 1))
      return e.stroke !== undefined ? Math.abs(q - 1) * Math.min(e.rx ?? 1, e.ry ?? 1) <= e.stroke / 2 : q <= 1
    }
    const pts = pathPts(e.d ?? ''), half = (e.stroke ?? 0) / 2
    return pts.slice(1).some((p, i) => segDist(x, y, pts[i], p) <= half)
  }
  const paintExtra = (e: GlyphExtra) => {
    const c = hexToRgb(pal[e.pigment]), a = e.stroke !== undefined ? 1 : (e.alpha ?? 1)
    for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) {
      if (!hit(e, (px + 0.5) / S, (py + 0.5) / S)) continue
      col[py * W + px] = e.pigment === 'paper' ? bg : composite(c, a, col[py * W + px])
    }
  }
  glyphExtras(base).filter(e => !e.above).forEach(paintExtra)
  for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) {
    const x = (px + 0.5) / S, y = (py + 0.5) / S
    for (const d of glyphOf(base)) if ((x - d.x) ** 2 + (y - d.y) ** 2 <= d.r * d.r) col[py * W + px] = composite(hexToRgb(pal[d.pigment]), 1, col[py * W + px])
  }
  glyphExtras(base).filter(e => e.above).forEach(paintExtra)
  return col
}

/** The §4c ink mask: a sample is ink when it reaches 2:1 against the light ground. */
function inkMask(base: PatternKind, ground: string, hue: number): boolean[] {
  return inkColours(base, ground, hue).map(c => contrast(rgbToHex(c), ground) >= 2)
}


test('r4 error (ruling 2): the open corner is clear at 1× — no ink along the 6 px of top edge or the 4 px of right edge beside it, and no dot bridges it', () => {
  const mask = raster('blanch')
  const at = (x: number, y: number): boolean => mask[Math.floor(y * 4) * 96 + Math.floor(x * 4)]
  for (let x = 14.5; x <= 20.5; x += 0.25) assert.equal(at(x, 1.5), false, `top gap at x ${x}`)
  for (let y = 2; y <= 6.5; y += 0.25) assert.equal(at(22, y), false, `right gap at y ${y}`)
})

// v2.1 round r5 (§4d): the error mark is the PALEST; the footprint is measured as an ENVELOPE (the bounding box of the pixels
// that reach 1.3:1 against the ground), because a pale mark cannot pass the r4 ink-area bar of 2:1. This test REPLACES the
// r4 ink-area footprint test, which is removed; the ink area is still printed for information only.
const lightDL = (c: { r: number; g: number; b: number }, ground: string): number =>
  Math.abs(rgbToOklab(c).L - rgbToOklab(hexToRgb(ground)).L)

test('r5 error is the PALEST mark (§4d ruling 1): its visible pixels sit closest to the ground in OKLab L', () => {
  const ground = '#fefefe'
  const meanDL = (base: PatternKind): number => {
    const vis = inkColours(base, ground, 205).filter(c => rgbToHex(c) !== ground)
    return vis.reduce((sum, c) => sum + lightDL(c, ground), 0) / vis.length
  }
  const err = meanDL('blanch')
  for (const other of ['mottle', 'clouds', 'zebra', 'eyespot'] as const) {
    assert.ok(err < meanDL(other), `error ${err.toFixed(3)} must be paler than ${other} ${meanDL(other).toFixed(3)}`)
  }
})

test('r5 error mark (§4d ruling 1): one pale plate (chroma α .24), one thin outline (1.6) with the open corner; no solid extra', () => {
  const err = glyphExtras('blanch')
  assert.deepEqual(err.map(projExtra), [
    ['rect', 'chroma', false, true, 0.24, null, 3, 2.5, 18, 11, 1, null],
    ['path', 'blanch', false, false, null, 1.6, null, null, null, null, null, 'M13 2.5 H3 V13.5 H21 V9']], 'the washed plate and the broken frame')
  assert.ok(err.every(e => (e.alpha ?? 1) < 1 || e.stroke !== undefined), 'no extra is solid or a heavy stroke')
  assert.deepEqual(glyphOf('blanch').map(projDot), [[13, 2.5, 1.1, 'blanch'], [21, 9, 1.1, 'blanch']], 'the two ends of the break')
})

test('r5 resting mark (§4d ruling 4): three quiet dots, an upright oval slightly wider', () => {
  assert.deepEqual(glyphOf('mottle').map(projDot), [[12, 5.4, 5.1, 'soft'], [12, 8, 5.9, 'soft'], [12, 10.6, 5.1, 'soft']])
  assert.deepEqual(glyphExtras('mottle').map(projExtra).map(e => [e[6], e[7]]), [[10.4, 5.2], [13.6, 8.4], [10.8, 11.2]], 'three paper holes')
})

test('r5 optical footprint (§4d ruling 1): each mark\'s ENVELOPE (bounding box of pixels ≥ 1.3:1 on the light ground) is within ±25 % of the five-mark mean', () => {
  const ground = '#fefefe'
  const envelope = (base: PatternKind): number => {
    const cols = inkColours(base, ground, 205)
    let minX = 1e9, minY = 1e9, maxX = -1, maxY = -1
    cols.forEach((c, i) => {
      if (contrast(rgbToHex(c), ground) < 1.3) return
      const x = i % 96, y = Math.floor(i / 96)
      minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    })
    return ((maxX - minX + 1) / 4) * ((maxY - minY + 1) / 4)
  }
  const a = STATES.map(envelope)
  const mean = a.reduce((s, v) => s + v, 0) / a.length
  STATES.forEach((s, i) => assert.ok(Math.abs(a[i] / mean - 1) <= 0.25, `${s}: envelope ${a[i].toFixed(0)} px² vs mean ${mean.toFixed(0)}`))
})
