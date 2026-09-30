#!/usr/bin/env node
/**
 * cf2909 spike 12, cell 5: the REAL Hermes desktop build's embedded terminal pane (xterm.js,
 * plan §2 fact Q) running the REAL `hermes --tui` with the 2-row test mantle.
 *
 *   node tools/spikes/12-terminal-rendering-real-tui/capture-desktop-pane.ts --out DIR
 *        [--runtime installed|upstream] [--display :93] [--wait 45]
 *
 * Uses the P0-DESK harness (tools/desktop_harness.ts: throwaway HOME/HERMES_HOME/userData,
 * private Xvfb) and goes through the user's path: Ctrl+` reveals the terminal pane, then the
 * command is typed into the pane's shell. The TUI gets its OWN throwaway HERMES_HOME holding only
 * mantle.mjs + an offline config (launch-tui.sh refuses the live ~/.hermes).
 *
 * Writes DIR/desktop-window.png (whole window) and DIR/desktop-pane.png (the .xterm element),
 * and prints one JSON line: { runtime, sha, renderer, fontFamily, cols, rows, shots }.
 */
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseArgs } from 'node:util'

import { _electron } from '@playwright/test'

import { buildEnv, checkoutSha, createSandbox, electronBinary, launchDesktop, resolveCheckout, writeConfig } from '../../desktop_harness.ts'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const { values } = parseArgs({
  options: {
    out: { type: 'string' },
    runtime: { type: 'string', default: 'installed' },
    display: { type: 'string', default: process.env.CF_DISPLAY ?? ':93' },
    wait: { type: 'string', default: '45' },
    // 'dom' = the harness default (--disable-gpu: xterm falls back to its DOM renderer);
    // 'gpu' = no --disable-gpu, so xterm tries its WebGL addon (SwiftShader on Xvfb).
    renderer: { type: 'string', default: 'dom' },
  },
})
if (!values.out) throw new Error('--out DIR is required')
const out = path.resolve(values.out)
fs.mkdirSync(out, { recursive: true })

// The TUI's throwaway home (separate from the desktop sandbox's home on purpose).
const tuiHome = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'cf-spike12-pane-'))
fs.mkdirSync(path.join(tuiHome, 'tui-widgets'))
fs.copyFileSync(path.join(HERE, 'mantle.mjs'), path.join(tuiHome, 'tui-widgets', 'cfmantle.mjs'))
fs.writeFileSync(path.join(tuiHome, 'config.yaml'),
  'model:\n  default: stub\n  provider: custom\n  base_url: http://127.0.0.1:9/v1\n  api_key: stub\ndisplay:\n  interface: tui\n')

async function launchGpu() {
  const checkout = resolveCheckout(values.runtime)
  const sandbox = createSandbox('cf-pane-gpu')
  writeConfig(sandbox, {})
  // Same window pin as desktop_harness.ts pinWindow (not exported), so both renderers get 1600x1000.
  fs.writeFileSync(path.join(sandbox.userDataDir, 'window-state.json'), JSON.stringify({ x: 0, y: 0, width: 1600, height: 1000, isMaximized: false }))
  fs.writeFileSync(path.join(sandbox.userDataDir, 'zoom-state.json'), JSON.stringify({ zoomLevel: 0 }))
  const desktopDir = path.join(checkout, 'apps', 'desktop')
  const app = await _electron.launch({
    executablePath: electronBinary(checkout), args: [desktopDir, '--no-sandbox', '--ignore-gpu-blocklist'],
    env: buildEnv(sandbox, checkout, values.display!), cwd: desktopDir, timeout: 120_000,
  })
  const page = await app.firstWindow({ timeout: 120_000 })
  return { app, page, sandbox, checkout, sha: checkoutSha(checkout), close: async () => { await app.close().catch(() => undefined) } }
}
const launched = values.renderer === 'gpu'
  ? await launchGpu()
  : await launchDesktop({ runtime: values.runtime, display: values.display, width: 1600, height: 1000 })
const page = launched.page
const shots: string[] = []
let info: Record<string, unknown> = {}
try {
  // Only the renderer needs to be up; the chat backend is irrelevant to the terminal pane.
  await page.waitForLoadState('domcontentloaded')
  await page.waitForTimeout(8000)
  const xterm = page.locator('.xterm').first()
  for (let i = 0; i < 5 && !(await xterm.isVisible().catch(() => false)); i++) {
    await page.keyboard.press('Control+Backquote')
    await page.waitForTimeout(2500)
  }
  await xterm.waitFor({ state: 'visible', timeout: 30_000 })
  // Best effort: the pane opens small (bottom of the right sidebar, ~309x130 px at 1600x1000).
  // Try the column sash on its left edge like a user would. On f42f579 this drag does NOT grow
  // the pane (measured: paneBox unchanged), so the TUI runs at the pane's default ~45x10 grid.
  const sashes = await page.evaluate(() => [...document.querySelectorAll('*')]
    .filter(e => getComputedStyle(e).cursor === 'col-resize' && e.getAttribute('role'))
    .map(e => e.getBoundingClientRect().toJSON()))
  const paneBox0 = await xterm.boundingBox()
  const sash = paneBox0 && sashes.find(b => Math.abs(b.x + b.width / 2 - paneBox0.x) < 20)
  if (sash) {
    const cx = sash.x + sash.width / 2, cy = paneBox0!.y + paneBox0!.height / 2
    await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(420, cy, { steps: 20 }); await page.mouse.up()
  }
  await page.waitForTimeout(1500)
  await xterm.click()
  await page.waitForTimeout(1500)
  const node = process.execPath
  const cmd = `HERMES_HOME=${tuiHome} CF_NODE=${node} CF_HERMES_SRC=${launched.checkout} ` +
    `exec bash ${path.join(HERE, 'launch-tui.sh')}`
  await page.keyboard.type(cmd, { delay: 5 })
  await page.keyboard.press('Enter')
  await page.waitForTimeout(Number(values.wait) * 1000)

  info = await page.evaluate(() => {
    const el = document.querySelector('.xterm') as HTMLElement | null
    const cs = el ? getComputedStyle(el.querySelector('.xterm-rows, .xterm-screen') ?? el) : null
    return {
      renderer: [...(el?.classList ?? [])].find(c => c.includes('renderer')) ?? (el?.querySelector('canvas') ? 'canvas' : 'unknown'),
      canvases: el ? el.querySelectorAll('canvas').length : 0,
      fontFamily: (el?.querySelector('.xterm-rows span, .xterm-rows div') ? getComputedStyle(el.querySelector('.xterm-rows span, .xterm-rows div')!).fontFamily : null) ?? cs?.fontFamily ?? null,
      fontSize: el?.querySelector('.xterm-rows') ? getComputedStyle(el.querySelector('.xterm-rows')!).fontSize : null,
      paneBox: el ? el.getBoundingClientRect().toJSON() : null,
      accessibleText: (document.querySelector('.xterm-accessibility-tree') as HTMLElement | null)?.innerText?.slice(0, 400) ?? null,
    }
  })
  const win = path.join(out, `desktop-window.${values.renderer}.png`)
  await page.screenshot({ path: win })
  shots.push(win)
  // Clip from the page (not xterm.screenshot): element shots came out offset under the GPU path.
  const pane = path.join(out, `desktop-pane.${values.renderer}.png`)
  const pb = await xterm.boundingBox()
  await page.screenshot({ path: pane, clip: pb! })
  shots.push(pane)
} finally {
  await launched.close()
  fs.rmSync(launched.sandbox.root, { recursive: true, force: true })
  fs.rmSync(tuiHome, { recursive: true, force: true })
}
console.log(JSON.stringify({ runtime: values.runtime, sha: launched.sha, ...info, shots }))
