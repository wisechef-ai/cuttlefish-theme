// D3 proxy (dev-only): CPU cost per field update of candidate motion techniques in headless Chromium (software raster, no GPU).
// A relative instrument: it ranks techniques; the real v0.22.7 Desktop numbers come from the capture harness (docs/design/D3.md).
//   node d3_proxy.mjs <outdir> [seconds=30] [hz=5]
import fs from 'node:fs'
import path from 'node:path'
import { execSync, spawn } from 'node:child_process'
import { chromium } from 'playwright'
import { renderField, toSvg, patternOf, DEFAULT_SETTINGS, planGround } from '../../desktop/src/domain/index.ts'

const out = path.resolve(process.argv[2] ?? 'out'), SECS = Number(process.argv[3] ?? 30), HZ = Number(process.argv[4] ?? 5)
fs.mkdirSync(out, { recursive: true })
const W = 1340, H = 900, GROUND = '#fefefe', HUE = 205, SEED = 'cf-d3'
const frameDots = t => renderField({ seed: SEED, width: W, height: H, hueDeg: HUE, ground: GROUND, pattern: patternOf(DEFAULT_SETTINGS, 'working'), intensity: 1, motion: 'still', reducedMotion: false, tMs: t, sinceChangeMs: 99999 })
const url = svg => `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
const rule = layers => `[data-chat-surface]{--ui-chat-surface-background:transparent;background:${layers} 0 0/${W}px ${H}px no-repeat,var(--cf-ground);--dt-composer-ring:#336699}:root{--cf-ground:var(--ui-chat-surface-background)}`
const NF = 36                                         // one cloud cycle sampled at 36 frames (the loop revisits them)
const times = Array.from({ length: NF }, (_, i) => (i * 18000) / NF)
const variants = {
  static: () => [rule(url(toSvg(frameDots(0), W, H)))],                                       // one frame, never updated (floor)
  base: () => times.map(t => rule(url(toSvg(frameDots(t), W, H)))),                            // today: full 190 circles per update
  cull: () => times.map(t => rule(url(toSvg(frameDots(t).filter(d => d.alpha >= 0.08), W, H)))), // drop near-invisible circles
  crisp: () => times.map(t => rule(url(toSvg(frameDots(t), W, H).replace('<svg ', '<svg shape-rendering="crispEdges" ')))),
  layered: () => {                                                                             // static base layer + small moving cloud layer
    const base = frameDots(0).map(d => ({ ...d }))
    const baseUrl = url(toSvg(base, W, H))
    return times.map(t => {
      const dots = frameDots(t)
      const hot = dots.filter((d, i) => d.alpha > base[i].alpha * 1.6 + 0.05)
      return rule(`${url(toSvg(hot, W, H))},${baseUrl}`)
    })
  },
  samecss: () => { const r = rule(url(toSvg(frameDots(0), W, H))); return times.map((_, i) => r + ' '.repeat(i % 2)) }, // new text, same image: cost of the style change itself
}
const only = (process.argv.find(a => a.startsWith('--only=')) ?? '').slice(7).split(',').filter(Boolean)

const ticks = pid => { try { const s = fs.readFileSync(`/proc/${pid}/stat`, 'utf8'); const f = s.slice(s.lastIndexOf(')') + 2).split(' '); return Number(f[11]) + Number(f[12]) } catch { return null } }
const tree = root => { const all = [root]; for (let i = 0; i < all.length; i++) { try { all.push(...execSync(`pgrep -P ${all[i]}`, { encoding: 'utf8' }).split('\n').filter(Boolean).map(Number)) } catch { /* leaf */ } } return all }
const CLK = 100
const mainPid = marker => Number(execSync(`pgrep -f -- --cf-marker=${marker}`, { encoding: 'utf8' }).split('\n').filter(Boolean).find(p => !fs.readFileSync(`/proc/${p}/cmdline`, 'utf8').includes('--type=')))
const DISPLAY = process.env.CF_PROXY_DISPLAY ?? ':97'
const xvfb = spawn('Xvfb', [DISPLAY, '-screen', '0', '1600x1000x24', '-nolisten', 'tcp'], { stdio: 'ignore' })
await new Promise(r => setTimeout(r, 1500))
const results = {}
for (const [name, mk] of Object.entries(variants)) {
  if (only.length && !only.includes(name)) continue
  const frames = mk()
  const browser = await chromium.launch({ headless: false, env: { ...process.env, DISPLAY }, executablePath: process.env.HOME + '/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome', args: ['--disable-gpu', '--force-color-profile=srgb', `--cf-marker=d3-${name}-${process.pid}`] })
  const page = await (await browser.newContext({ viewport: { width: 1400, height: 960 } })).newPage()
  await page.setContent(`<html><body style="margin:0"><style id="own"></style><div data-chat-surface style="width:${W}px;height:${H}px;position:relative">${'<p style="padding:6px 24px;margin:0;font:14px sans-serif">The quick brown fox jumps over the lazy dog while the retry loop swallows the original error.</p>'.repeat(40)}</div></body></html>`)
  await page.evaluate(([f, hz, secs]) => { window.__n = 0; document.getElementById('own').textContent = f[0]; if (f.length > 1) window.__t = setInterval(() => { window.__n++; document.getElementById('own').textContent = f[window.__n % f.length] }, 1000 / hz) }, [frames, HZ, SECS])
  await new Promise(r => setTimeout(r, 4000))
  const pids = tree(mainPid(`d3-${name}-${process.pid}`)), t0 = Object.fromEntries(pids.map(p => [p, ticks(p)]))
  const n0 = await page.evaluate(() => window.__n), w0 = Date.now()
  await new Promise(r => setTimeout(r, SECS * 1000))
  const t1 = Object.fromEntries(pids.map(p => [p, ticks(p)])), n1 = await page.evaluate(() => window.__n), w1 = Date.now()
  const used = pids.reduce((s, p) => s + ((t1[p] ?? t0[p] ?? 0) - (t0[p] ?? 0)), 0) / CLK
  results[name] = { cpu_pct: +(100 * used / ((w1 - w0) / 1000)).toFixed(2), updates_per_s: +((n1 - n0) / ((w1 - w0) / 1000)).toFixed(2), kb: Math.round(frames[0].length / 1024) }
  console.log(name, JSON.stringify(results[name]))
  await browser.close()
}
xvfb.kill()
fs.writeFileSync(path.join(out, 'd3_proxy.json'), JSON.stringify({ W, H, HZ, SECS, results }, null, 1))
