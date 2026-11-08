// Unit: the v2.1 r5 inks (§4d ruling 1 and 4): the quiet resting ink and the pale error outline, on every row the marks sit on.
// Written first; the constants below do not exist on 7049668 (SOFT_C) or hold the r4 values (SOFT_CONTRAST 3.5, BLANCH_CONTRAST 4.5).
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import * as ink from '../../src/domain/ink.ts'
import { rgbToOklab, hexToRgb } from '../../src/domain/oklch.ts'

const GROUNDS = ['#fefefe', '#141416', '#2e3440']
const HUES = [100, 150, 205, 260, 310, 350]
/** The design rows each ground is shown on: unselected and selected. */
const ROWS: Record<string, string[]> = { '#fefefe': ['#f6f8fa', '#d8e1f0'], '#141416': ['#17181c', '#2a3142'], '#2e3440': ['#2e3440', '#434c5e'] }
const chromaOf = (hex: string): number => { const l = rgbToOklab(hexToRgb(hex)); return Math.hypot(l.a, l.b) }

test('r5 ink constants (§4d): resting is lower-saturation at 3.35, error is the pale outline at 3.35', () => {
  assert.equal(ink.SOFT_C, 0.07, 'resting ink chroma')
  assert.equal(ink.SOFT_CONTRAST, 3.35, 'resting ink contrast floor')
  assert.equal(ink.BLANCH_CONTRAST, 3.35, 'error outline contrast floor')
})

test('r5 outlines (§4d): resting and error hold ≥ 3.05:1 on every ground and every row, selected or not', () => {
  for (const ground of GROUNDS) for (const hue of HUES) {
    const pal = ink.palette(hue, ground)
    for (const row of ROWS[ground]) for (const p of ['soft', 'blanch'] as const) {
      assert.ok(ink.contrast(pal[p], row) >= 3.05, `${p} on ${row} (ground ${ground}, hue ${hue}): ${ink.contrast(pal[p], row).toFixed(2)}`)
    }
  }
})

test('r5 resting ink (§4d): less saturated than the identity ink, the hue kept', () => {
  for (const ground of GROUNDS) for (const hue of HUES) {
    const pal = ink.palette(hue, ground)
    assert.ok(chromaOf(pal.soft) < chromaOf(pal.chroma), `soft ${chromaOf(pal.soft).toFixed(3)} vs chroma ${chromaOf(pal.chroma).toFixed(3)} at ${hue}`)
  }
})
