/**
 * Spike 14 — Playwright `_electron.launch` on the REAL desktop build.
 *
 *   node tools/spikes/14-playwright-real-electron/run.ts [--runtime installed|upstream] [--out DIR]
 *
 * 1. temp HOME/HERMES_HOME/userData; scratch unified package `cf-spike` copied into
 *    <home>/plugins/cf-spike (agent half + desktop/ + dashboard/)
 * 2. launch → wait for a hit-testable composer → 01-main.png
 * 3. assert the desktop half was materialized (desktop-plugins/cf-spike + marker) and
 *    is inventoried but NOT running (defaultEnabled:false for unified halves)
 * 4. Capabilities ▸ Plugins → flip "Desktop: cf-spike" → 02-plugins-enabled.png
 * 5. back to the chat → the CF-SPIKE chip + "CF Spike" nav row are ON SCREEN → 03-main-enabled.png
 * Writes result.json next to the PNGs.
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import { createSandbox, installUnifiedPackage, launchDesktop, shot, visibleText, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute, listSwitches } from '../../desktop_ui.ts'

const HERE = import.meta.dirname
const FIXTURE = path.resolve(HERE, '..', 'fixtures', 'cf-spike')

const { values } = parseArgs({
  options: {
    runtime: { type: 'string', default: 'installed' },
    out: { type: 'string', default: path.join(process.env.TMPDIR || '/tmp', 'cf-spike14') },
    keep: { type: 'boolean', default: false },
  },
})

const out = path.resolve(values.out!, values.runtime!.replace(/[^\w-]/g, '_'))
fs.mkdirSync(out, { recursive: true })

const sandbox = createSandbox('cf-s14')
installUnifiedPackage(sandbox, FIXTURE, 'cf-spike')

const result: Record<string, unknown> = { runtime: values.runtime, sandbox: sandbox.root }
const t0 = Date.now()
const l = await launchDesktop({ runtime: values.runtime, sandbox })
result.sha = l.sha
result.checkout = l.checkout
const log = fs.createWriteStream(path.join(out, 'electron.log'))
l.app.process().stdout?.pipe(log)
l.app.process().stderr?.pipe(log)

try {
  await waitForShell(l.page)
  result.bootToShellMs = Date.now() - t0
  await shot(l.page, path.join(out, '01-main.png'))

  const root = path.join(sandbox.hermesHome, 'desktop-plugins', 'cf-spike')
  result.materialized = fs.existsSync(path.join(root, 'plugin.js'))
  result.marker = fs.existsSync(path.join(root, '.hermes-package.json'))
    ? JSON.parse(fs.readFileSync(path.join(root, '.hermes-package.json'), 'utf8'))
    : null

  const before = await l.page.evaluate(() => ({
    loaded: Boolean((window as any).__cfSpike?.loads?.length),
    chip: Boolean(document.querySelector('[data-testid="cf-spike-chip"]')),
  }))
  result.beforeEnable = before

  await gotoRoute(l.page, '/capabilities?tab=plugins')
  await l.page.waitForTimeout(2500)
  result.switchesBefore = await listSwitches(l.page)
  await shot(l.page, path.join(out, '02a-plugins-before.png'))

  result.enabled = await enablePluginViaSettings(l.page, 'CF Spike')
  await l.page.waitForTimeout(1500)
  result.switchesAfter = await listSwitches(l.page)
  await shot(l.page, path.join(out, '02-plugins-enabled.png'))

  await gotoRoute(l.page, '/')
  await l.page.waitForSelector('[data-testid="cf-spike-chip"]', { timeout: 20_000 })
  await l.page.waitForTimeout(1000)
  await shot(l.page, path.join(out, '03-main-enabled.png'))

  const text = await visibleText(l.page)
  result.afterEnable = await l.page.evaluate(() => ({
    loads: (window as any).__cfSpike?.loads?.length ?? 0,
    chip: (document.querySelector('[data-testid="cf-spike-chip"]') as HTMLElement | null)?.innerText ?? null,
  }))
  result.navRowVisible = /CF Spike/.test(text)
  result.decisions = await l.page.evaluate(() => localStorage.getItem('hermes.desktop.pluginDecisions.v2'))
} catch (error) {
  result.error = String((error as Error)?.stack ?? error)
  await shot(l.page, path.join(out, 'zz-failure.png')).catch(() => undefined)
} finally {
  await l.close()
  if (!values.keep) fs.rmSync(sandbox.root, { recursive: true, force: true })
}

fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(result, null, 2))
console.log(JSON.stringify(result, null, 2))
process.exit(result.error ? 1 : 0)
