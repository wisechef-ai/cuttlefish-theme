/**
 * Spike S1 (dev only): on the REAL v0.22.7 Desktop, can a plugin's own <style> paint an organ-dot layer on
 * [data-chat-surface] behind the chat, and does --dt-composer-ring repaint the composer border?
 * Exports the plugin + probe so m04_spike.ts can run it after the chat-render step; runnable alone:
 *   node tools/desktop/spike_s1.ts <outdir>
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { createSandbox, installDiskPlugin, launchDesktop, shot, waitForShell } from './harness.ts'

export const DOT_SVG = (() => {
  let c = ''
  for (let i = 0; i < 260; i++) {
    const x = (i * 97) % 1440, y = (i * 53 + (i % 7) * 31) % 900
    c += `<circle cx="${x}" cy="${y}" r="${2 + (i % 3)}" fill="#7ad7c8" fill-opacity="0.55"/>`
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1440" height="900">${c}</svg>`
})()

/** The plugin's own <style>, gated by two root attributes so the probe can measure before/after. */
export const PLUGIN = `import { TITLEBAR_AREAS, STATUSBAR_AREAS, SESSION_ROW_AREAS } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'
import { useEffect } from 'react'
const URL_ = ${JSON.stringify('data:image/svg+xml,' + encodeURIComponent(DOT_SVG))}
function Mount() {
  useEffect(() => {
    const s = document.createElement('style')
    s.setAttribute('data-cfspike-style', '1')
    s.textContent = \`
      :root[data-cfspike-field~="direct"] [data-chat-surface] { background-image: url("\${URL_}"); background-repeat: no-repeat; background-size: cover; }
      :root[data-cfspike-field~="vars"] [data-chat-surface] { background-image: url("\${URL_}"); background-repeat: no-repeat; background-size: cover; background-color: var(--ui-bg-chrome); --ui-chat-surface-background: transparent; }
      :root[data-cfspike-field~="after"] [data-chat-surface]::after { content: ""; position: absolute; inset: 0; pointer-events: none; background-image: url("\${URL_}"); background-repeat: no-repeat; background-size: cover; }
      :root[data-cfspike-ring~="direct"] [data-chat-surface] { --dt-composer-ring: #ff00aa; --composer-ring-strength: 4; }
      :root[data-cfspike-ring~="stroke"] [data-chat-surface] { --ui-stroke-secondary: #ff00aa; }
    \`
    document.head.appendChild(s)
    document.documentElement.setAttribute('data-cfspike', '1')
    return () => { s.remove(); document.documentElement.removeAttribute('data-cfspike') }
  }, [])
  return null
}
export default {
  id: 'cf-spike', name: 'CF Spike',
  register(ctx) {
    ctx.register({ id: 'mount', area: TITLEBAR_AREAS.right, render: () => jsx(Mount, {}) })
    ctx.register({ id: 'strip', area: STATUSBAR_AREAS.left, render: () => jsx('span', { 'data-cfspike-strip': '1', children: 'CF-STRIP' }) })
    ctx.register({ id: 'row', area: SESSION_ROW_AREAS.leading, data: { render: ({ sessionId }) => jsx('span', { 'data-cfspike-row': sessionId, children: '◉' }) } })
  }
}
`

const readComposer = () => {
  const comp = document.querySelector('[data-slot="composer-root"]') as HTMLElement | null
  const ringEl = comp?.querySelector('[class*="composer-ring-strength"]') as HTMLElement | null
  const surface = document.querySelector('[data-chat-surface]') as HTMLElement | null
  return {
    composer_border: ringEl ? getComputedStyle(ringEl).borderTopColor : null,
    ring_el: ringEl ? `${ringEl.tagName.toLowerCase()}[data-slot=${ringEl.getAttribute('data-slot')}]` : null,
    ring_var: ringEl ? getComputedStyle(ringEl).getPropertyValue('--dt-composer-ring').trim() : null,
    surface_bg_image: surface ? getComputedStyle(surface).backgroundImage : null,
    surface_size: surface ? [surface.clientWidth, surface.clientHeight] : null,
    style_mounted: !!document.querySelector('style[data-cfspike-style]'),
    strip: !!document.querySelector('[data-cfspike-strip]'),
    rows: document.querySelectorAll('[data-cfspike-row]').length,
  }
}

export interface Stage { gate: string; value: string; composer_border: string | null; ring_var: string | null; surface_bg_image: string | null; png: string }
export interface S1Result {
  field_layer_applied: boolean; background_image_prefix: string | null
  composer_border_before: string | null; composer_border_after: string | null
  composer_repainted: boolean; stages: Stage[]; detail: Record<string, unknown>
}

async function stage(page: Page, out: string, n: number, gate: 'field' | 'ring' | null, value: string): Promise<Stage> {
  await page.evaluate(([g, v]) => {
    const r = document.documentElement
    r.removeAttribute('data-cfspike-field'); r.removeAttribute('data-cfspike-ring')
    if (g) r.setAttribute(`data-cfspike-${g}`, v)
  }, [gate, value] as const)
  await page.waitForTimeout(700) // border-color may transition
  const m = await page.evaluate(readComposer)
  const png = `s1-${n}-${gate ?? 'none'}-${value || 'off'}.png`
  await shot(page, path.join(out, png))
  return { gate: gate ?? 'none', value, composer_border: m.composer_border, ring_var: m.ring_var, surface_bg_image: m.surface_bg_image?.slice(0, 40) ?? null, png }
}

export async function probeS1(page: Page, out: string): Promise<S1Result> {
  const baseline = await stage(page, out, 0, null, '')
  const direct = await stage(page, out, 1, 'field', 'direct')
  const vars = await stage(page, out, 2, 'field', 'vars')
  const after = await stage(page, out, 3, 'field', 'after')
  const ringDirect = await stage(page, out, 4, 'ring', 'direct')
  const ringStroke = await stage(page, out, 5, 'ring', 'stroke')
  await stage(page, out, 6, null, '')
  return {
    field_layer_applied: !!direct.surface_bg_image?.startsWith('url('),
    background_image_prefix: direct.surface_bg_image,
    composer_border_before: baseline.composer_border, composer_border_after: ringDirect.composer_border,
    composer_repainted: baseline.composer_border !== ringDirect.composer_border,
    stages: [baseline, direct, vars, after, ringDirect, ringStroke],
    detail: { ring_stroke_border: ringStroke.composer_border, ring_stroke_repainted: ringStroke.composer_border !== baseline.composer_border },
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const out = path.resolve(process.argv[2] ?? path.join(process.env.HOME ?? '.', 'repos/hackathon/sandboxes/spike-s1'))
  fs.mkdirSync(out, { recursive: true })
  const sb = createSandbox('spike-s1')
  installDiskPlugin(sb, 'cf-spike', PLUGIN)
  const l = await launchDesktop({ sandbox: sb })
  try {
    await waitForShell(l.page)
    await l.page.waitForTimeout(4000)
    console.log(JSON.stringify(await probeS1(l.page, out), null, 2))
  } finally { await l.close() }
}
