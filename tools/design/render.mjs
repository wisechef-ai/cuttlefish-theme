// Golden renders (dev-only). Run where Playwright + headless Chromium live (hercules):  node render.mjs <outdir> [--only=cells,sheets,apps]
// Writes: cells@{1,2}x.png + cells.json (the measurement grid), sheet-*.png, app-<ground>-<state>.png, contact-*.png
import fs from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
import { BOX, STATES, HUES, RIM_H, glyphSvg } from './model.mjs'
import { GROUNDS, LABELS, appHtml, css, rowHtml, stripHtml, rimHtml } from './pages.mjs'

const out = path.resolve(process.argv[2] ?? 'out')
const only = (process.argv.find(a => a.startsWith('--only=')) ?? '--only=cells,sheets,apps').slice(7).split(',')
fs.mkdirSync(out, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.HOME + '/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome', args: ['--disable-gpu', '--force-color-profile=srgb', '--font-render-hinting=none'] })
const shot = async (html, file, { w, h, dpr = 1 }) => {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr })
  const page = await ctx.newPage()
  await page.setContent(`<html><head><style>${css}</style></head><body style="margin:0">${html}</body></html>`)
  await page.screenshot({ path: path.join(out, file) })
  await ctx.close()
}
const full = async (html, file, w, h, dpr = 1) => {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr })
  const page = await ctx.newPage()
  await page.setContent(html)
  await page.screenshot({ path: path.join(out, file) })
  await ctx.close()
}

// ---- measurement grid: every state x hue x ground x (unselected|selected) on the flat row ground --------------------
if (only.includes('cells')) {
  const MEAS_HUES = [100, 150, 205, 260, 310, 350]
  const cells = []
  let html = '<div style="position:relative">'
  const CW = 40, CH = 28
  let y = 0
  for (const g of Object.keys(GROUNDS)) {
    for (const sel of [false, true]) {
      for (const hue of MEAS_HUES) {
        let x = 0
        for (const s of STATES) {
          const bg = sel ? GROUNDS[g].sel : GROUNDS[g].side
          cells.push({ ground: g, sel, hue, state: s, x, y, w: CW, h: CH, bg, gx: 8, gy: 6 })
          html += `<div style="position:absolute;left:${x}px;top:${y}px;width:${CW}px;height:${CH}px;background:${bg}"><div style="position:absolute;left:8px;top:6px">${glyphSvg(s, hue, GROUNDS[g].chat)}</div></div>`
          x += CW
        }
        y += CH
      }
    }
  }
  html += '</div>'
  const W = CW * STATES.length, H = y
  for (const dpr of [1, 2]) await shot(html, `cells@${dpr}x.png`, { w: W, h: H, dpr })
  fs.writeFileSync(path.join(out, 'cells.json'), JSON.stringify({ box: BOX, cells, W, H }))
}

// ---- sheets ---------------------------------------------------------------------------------------------------------
if (only.includes('sheets')) {
  for (const dpr of [1, 2]) {
    const cols = Object.keys(GROUNDS).map(g => {
      const G = GROUNDS[g]
      const one = sel => STATES.map((s, i) => rowHtml(g, s, HUES[i], sel)).join('')
      return `<div style="background:${G.side};padding:10px;width:270px">
        <div style="color:${G.mute};font:11px sans-serif;margin:2px 10px 6px">${g} · unselected</div>${one(false)}
        <div style="color:${G.mute};font:11px sans-serif;margin:10px 10px 6px">${g} · selected</div>${one(true)}</div>`
    })
    await shot(`<div style="display:flex">${cols.join('')}</div>`, `sheet-sidebar@${dpr}x.png`, { w: 810, h: 330, dpr })
  }
  // rim + strip per ground
  const parts = Object.keys(GROUNDS).map(g => {
    const G = GROUNDS[g]
    const rows = STATES.map((s, i) => `<div style="display:flex;align-items:center;gap:16px;margin:10px 0">
        <div style="width:480px;border-radius:6px 6px 0 0;overflow:hidden">${rimHtml(g, s, HUES[i], 480)}<div style="height:30px;border:1px solid ${G.edge};border-top:0;background:${G.card};border-radius:0 0 8px 8px"></div></div>
        <div style="width:130px;height:22px;display:flex;align-items:center;justify-content:flex-end;padding:0 10px;background:${G.bar};border:1px solid ${G.edge}">${stripHtml(g, s, HUES[i])}</div></div>`).join('')
    return `<div style="background:${G.chat};padding:12px 16px;color:${G.mute};font:11px sans-serif">${g}${rows}</div>`
  })
  await shot(`<div style="width:700px">${parts.join('')}</div>`, 'sheet-rim-strip@2x.png', { w: 700, h: 3 * 330, dpr: 2 })
}

// ---- whole app mocks --------------------------------------------------------------------------------------------------
if (only.includes('apps')) {
  for (const g of Object.keys(GROUNDS)) for (const s of STATES) await full(appHtml(g, s), `app-${g}-${s}.png`, 1280, 800, 1)
  for (const g of ['light', 'dark']) {
    const imgs = STATES.map(s => `<figure style="margin:0"><img src="app-${g}-${s}.png" style="width:640px;display:block"/><figcaption style="font:12px sans-serif;color:#888;padding:2px 6px">${g} · ${s}</figcaption></figure>`).join('')
    fs.writeFileSync(path.join(out, `contact-${g}.html`), `<html><body style="margin:0;background:#888;display:grid;grid-template-columns:640px 640px;gap:6px;width:1286px">${imgs}</body></html>`)
    const ctx = await browser.newContext({ viewport: { width: 1286, height: 3 * 406 }, deviceScaleFactor: 1 })
    const page = await ctx.newPage()
    await page.goto('file://' + path.join(out, `contact-${g}.html`))
    await page.screenshot({ path: path.join(out, `contact-${g}.png`), fullPage: true })
    await ctx.close()
  }
}
await browser.close()
console.log('rendered to', out)
