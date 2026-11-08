// Real-pixel proxy for the locked O7_5 field read (dev-only): render the product's own field (domain renderField + the painter's circle budget)
// as an SVG background of a surface in a 1600x1000 page, with headless Chromium, at the same place the Desktop paints it (surface at 260,34).
// The PNGs are then measured with the LOCKED instruments (tests/acceptance/instruments_py.py) by field_pixels.py, over the real sidecar regions/exclusions.
//   node field_pixels.mjs <outdir> [field_variants.json]     variant = {name, w, h, cull}   (w,h = the field canvas; cull = circle budget, 0 = none)
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
import { renderField, toSvg, allocate, patternOf, DEFAULT_SETTINGS } from '../../desktop/src/domain/index.ts'

const out = path.resolve(process.argv[2]), variants = JSON.parse(fs.readFileSync(new URL('./' + (process.argv[3] ?? 'field_variants.json'), import.meta.url), 'utf8'))
fs.mkdirSync(out, { recursive: true })
const only = (process.env.CF_STATES ?? '').split(',').filter(Boolean)
const cases = JSON.parse(fs.readFileSync(new URL('./field_cases.json', import.meta.url), 'utf8')).filter(c => !only.length || only.includes(c.state))
const cull = (dots, budget) => {
  const vis = dots.filter(d => d.alpha > 0 && d.r > 0)
  if (!budget || vis.length <= budget) return vis
  const eye = vis.filter(d => d.role === 'eyespot')
  const keep = new Set([...vis.filter(d => d.role !== 'eyespot').sort((a, b) => b.alpha - a.alpha).slice(0, Math.max(0, budget - eye.length)), ...eye])
  return vis.filter(d => keep.has(d))
}
const browser = await chromium.launch({ executablePath: process.env.HOME + '/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome', args: ['--disable-gpu', '--force-color-profile=srgb'] })
const page = await (await browser.newContext({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 })).newPage()
const index = []
for (const v of variants) for (const c of cases) {
  const dots = renderField({ seed: c.seed, width: v.w, height: v.h, hueDeg: allocate(c.seed, []).hue_deg, ground: c.ground, pattern: patternOf(DEFAULT_SETTINGS, c.state),
    intensity: 1, motion: 'still', reducedMotion: false, tMs: v.tMs ?? 4200, sinceChangeMs: 99999 })
  const budget = c.state === 'working' && v.cullClouds !== undefined ? v.cullClouds : v.cull
  const svg = toSvg(cull(dots, budget), v.w, v.h)
  const url = `url('data:image/svg+xml,${encodeURIComponent(svg)}')`
  await page.setContent(`<html><body style="margin:0;background:${c.ground}"><div style="position:absolute;left:260px;top:34px;width:1339px;height:944px;overflow:hidden;background:${url} 0 0/${v.w}px ${v.h}px no-repeat,${c.ground}"></div></body></html>`)
  const file = `${v.name}.${c.state}.png`
  await page.screenshot({ path: path.join(out, file) })
  index.push({ variant: v.name, state: c.state, file, organs: cull(dots, budget).length })
}
fs.writeFileSync(path.join(out, 'index.json'), JSON.stringify(index))
await browser.close()
