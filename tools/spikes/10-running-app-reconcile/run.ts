/**
 * Spike 10 — running-app reconcile (plan fact G, §1.5 step 2 "triggers the desktop
 * reconcile if the app is running").
 *
 *   tools/spikes/run-desktop.sh 10-running-app-reconcile [--runtime installed|upstream] [--out DIR]
 *
 * The app is booted with NO plugin. Then, while it runs, we install the scratch
 * unified package the way an agent-side CLI would (a plain copy into
 * <home>/plugins/cf-spike) and measure what picks it up:
 *
 *   A passive   copy only; wait 20 s; also fire window blur/focus + a route change.
 *               → is desktop-plugins/cf-spike materialized? is the plugin inventoried?
 *   B poke      write a file into <home>/desktop-plugins/ (the dir the renderer
 *               fs-watches). → time until materialized + until inventoried.
 *   C consent   first install: the half is opt-in, so the user still flips the
 *               Desktop switch → time from click to first chip pixel.
 *   D update    rewrite the SOURCE desktop/plugin.js (chip text v2) while enabled;
 *               passive 15 s, then poke → does the running plugin hot-reload?
 *   E remove    delete <home>/plugins/cf-spike; passive 15 s, then poke → is the
 *               root copy pruned and the chip gone?
 *   F re-install with the prior "enabled" decision still in localStorage:
 *               poke → time to first chip pixel with NO click.
 *
 * Ground truth is the filesystem (marker file) + the DOM (chip) + screenshots.
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import type { Page } from '@playwright/test'

import { createSandbox, launchDesktop, shot, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute } from '../../desktop_ui.ts'

const HERE = import.meta.dirname
const FIXTURE = path.resolve(HERE, '..', 'fixtures', 'cf-spike')

const { values } = parseArgs({
  options: {
    runtime: { type: 'string', default: 'installed' },
    out: { type: 'string', default: path.join(process.env.TMPDIR || '/tmp', 'cf-spike10') },
    keep: { type: 'boolean', default: false },
    passiveMs: { type: 'string', default: '20000' },
    // file: leave a .cuttlefish-poke file (residue); dir: mkdir+rmdir a temp dir (no residue)
    poke: { type: 'string', default: 'file' },
  },
})

const out = path.resolve(values.out!, values.runtime!.replace(/[^\w-]/g, '_') + (values.poke === 'file' ? '' : `-poke-${values.poke}`))
fs.mkdirSync(out, { recursive: true })
const passiveMs = Number(values.passiveMs)

const sandbox = createSandbox('cf-s10')
const pkgDir = path.join(sandbox.hermesHome, 'plugins', 'cf-spike')
const rootDir = path.join(sandbox.hermesHome, 'desktop-plugins')
const halfDir = path.join(rootDir, 'cf-spike')
const marker = path.join(halfDir, '.hermes-package.json')

const result: Record<string, any> = { runtime: values.runtime, sandbox: sandbox.root, passiveMs, poke: values.poke }
const steps: any[] = []
const note = (step: string, data: Record<string, unknown> = {}) => {
  const rec = { t: Date.now(), step, ...data }
  steps.push(rec)
  console.error(JSON.stringify(rec))
}

async function chipText(page: Page): Promise<null | string> {
  return page.evaluate(
    () => (document.querySelector('[data-testid="cf-spike-chip"]') as HTMLElement | null)?.innerText ?? null,
  )
}

/** Poll until `fn` is truthy; returns elapsed ms or null on timeout. */
async function until(fn: () => Promise<unknown> | unknown, timeoutMs: number, everyMs = 50): Promise<null | number> {
  const t0 = Date.now()

  while (Date.now() - t0 < timeoutMs) {
    if (await fn()) return Date.now() - t0
    await new Promise(r => setTimeout(r, everyMs))
  }

  return null
}

function poke(tag: string): string {
  // What `hermes cuttlefish setup` could do: cause one entry change in the watched root.
  fs.mkdirSync(rootDir, { recursive: true })

  if (values.poke === 'dir') {
    const dir = path.join(rootDir, `.cuttlefish-poke-${process.pid}-${Date.now()}`)
    fs.mkdirSync(dir)
    fs.rmdirSync(dir)

    return dir
  }

  const file = path.join(rootDir, `.cuttlefish-poke`)
  fs.writeFileSync(file, `${tag} ${Date.now()}\n`)

  return file
}

/** Is the desktop half in the app's plugin inventory? Read what the Installed filter shows. */
async function inventoried(page: Page): Promise<boolean> {
  return page.evaluate(() => Boolean(document.querySelector('[data-catalog-card][data-entry-id="installed:cf-spike"]')))
}

const l = await launchDesktop({ runtime: values.runtime, sandbox })
result.sha = l.sha
const log = fs.createWriteStream(path.join(out, 'electron.log'))
l.app.process().stdout?.pipe(log)
l.app.process().stderr?.pipe(log)
const page = l.page

try {
  await waitForShell(page)
  note('shell')
  result.rootExistsAtBoot = fs.existsSync(rootDir)
  await shot(page, path.join(out, '00-boot-no-plugin.png'))

  // ── A: passive ──────────────────────────────────────────────────────────
  fs.cpSync(FIXTURE, pkgDir, { recursive: true })
  const tInstall = Date.now()
  note('A.installed-into-plugins')
  const aMaterialized = await until(() => fs.existsSync(marker), passiveMs)
  result.A_passive_materializedMs = aMaterialized
  // focus / blur / route change — plausible incidental triggers
  await l.app.evaluate(({ BrowserWindow }) => {
    const w = BrowserWindow.getAllWindows()[0]
    w.blur()
    w.focus()
  })
  await gotoRoute(page, '/')
  await page.waitForTimeout(3000)
  result.A_afterFocusMaterialized = fs.existsSync(marker)
  note('A.done', { materialized: fs.existsSync(marker) })

  // ── B: poke ─────────────────────────────────────────────────────────────
  // Navigate to the Installed view FIRST so the inventory check reads a live DOM
  // (visiting the Plugins tab does not itself reconcile — A proved it didn't fire).
  await gotoRoute(page, '/capabilities?tab=plugins')
  await page.getByText('Installed', { exact: true }).first().click()
  await page.waitForTimeout(1500)
  result.B_inventoriedBeforePoke = await inventoried(page)
  result.B_materializedBeforePoke = fs.existsSync(marker)
  await shot(page, path.join(out, '01-installed-before-poke.png'))
  const tPoke = Date.now()
  poke('B')
  note('B.poke')
  result.B_poke_materializedMs = await until(() => fs.existsSync(marker), 15_000)
  result.B_poke_inventoriedMs = await until(() => inventoried(page), 15_000)
  result.B_sinceInstallMs = Date.now() - tInstall
  await shot(page, path.join(out, '02-installed-after-poke.png'))
  note('B.done', { materialized: fs.existsSync(marker) })

  // ── C: first-install consent → first pixel ─────────────────────────────
  await gotoRoute(page, '/')
  result.C_chipBeforeConsent = await chipText(page)
  const tClick = Date.now()
  await enablePluginViaSettings(page, 'CF Spike')
  await gotoRoute(page, '/')
  result.C_clickToChipMs = await until(async () => Boolean(await chipText(page)), 15_000)
  result.C_totalSinceClickMs = Date.now() - tClick
  result.C_chip = await chipText(page)
  await shot(page, path.join(out, '03-enabled-chip.png'))
  result.C_pokeToFirstPixelMs = Date.now() - tPoke
  note('C.done', { chip: result.C_chip })

  // ── D: update the SOURCE (unified package) ─────────────────────────────
  const srcJs = path.join(pkgDir, 'desktop', 'plugin.js')
  fs.writeFileSync(srcJs, fs.readFileSync(srcJs, 'utf8').replace('`CF-SPIKE ${n} busy`', '`CF-SPIKE v2 ${n} busy`'))
  note('D.source-updated')
  result.D_passive_updatedMs = await until(async () => /v2/.test((await chipText(page)) ?? ''), passiveMs)
  poke('D')
  result.D_poke_updatedMs = await until(async () => /v2/.test((await chipText(page)) ?? ''), 15_000)
  result.D_chip = await chipText(page)
  await shot(page, path.join(out, '04-after-update.png'))
  note('D.done', { chip: result.D_chip })

  // ── E: remove the package ───────────────────────────────────────────────
  fs.rmSync(pkgDir, { recursive: true, force: true })
  note('E.removed')
  result.E_passive_goneMs = await until(async () => !(await chipText(page)), passiveMs)
  result.E_rootCopyAfterPassive = fs.existsSync(halfDir)
  poke('E')
  result.E_poke_prunedMs = await until(() => !fs.existsSync(halfDir), 15_000)
  result.E_poke_chipGoneMs = await until(async () => !(await chipText(page)), 15_000)
  await shot(page, path.join(out, '05-after-remove.png'))
  note('E.done', { rootCopy: fs.existsSync(halfDir), chip: await chipText(page) })

  // ── F: re-install with the prior enabled decision ───────────────────────
  result.F_decisions = await page.evaluate(() => localStorage.getItem('hermes.desktop.pluginDecisions.v2'))
  fs.cpSync(FIXTURE, pkgDir, { recursive: true })
  const tF = Date.now()
  poke('F')
  result.F_pokeToChipMs = await until(async () => Boolean(await chipText(page)), 15_000)
  result.F_total = Date.now() - tF
  result.F_chip = await chipText(page)
  await shot(page, path.join(out, '06-reinstall-auto.png'))
  note('F.done', { chip: result.F_chip })
} catch (error) {
  result.error = String((error as Error)?.stack ?? error)
  await shot(page, path.join(out, 'zz-failure.png')).catch(() => undefined)
} finally {
  result.steps = steps
  result.rootResidue = fs.existsSync(rootDir) ? fs.readdirSync(rootDir) : null
  await l.close()
  if (!values.keep) fs.rmSync(sandbox.root, { recursive: true, force: true })
}

fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(result, null, 2))
const { steps: _s, ...summary } = result
console.log(JSON.stringify(summary, null, 2))
process.exit(result.error ? 1 : 0)
