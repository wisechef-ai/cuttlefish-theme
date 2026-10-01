#!/usr/bin/env node
/**
 * cf2909 P1 host (lane H): drive ONE real Hermes desktop boot through a list of scenes.
 *
 *   node tools/p1/hosts/desktop-capture.ts --job job.json
 *
 * Called by tools/p1/capture_matrix.py (which writes the job); not meant to be run by hand. The job:
 *   { runtime, display, gpu, width, height,
 *     package:  dir of a unified package (plugin.yaml + desktop/plugin.js) installed into the temp home,
 *     plugin_name: display name for the consent path (Installed ▸ card ▸ "Desktop: <name>"),
 *     seed:     { python, script, checkout } → runs `python script --checkout checkout` with the temp HERMES_HOME,
 *     desktop:  [{ scene, file, targets: [{ id, kind: field|chip|swatch|sidebar, idx? }] }],
 *     pane:     { tui_home, scene_path, ack_path, cmd, cols, shots: [{ id, scene, file, ack_out }] },
 *     result:   path for the result json }
 *
 * Everything runs in the P0-DESK sandbox (tools/desktop_harness.ts): temp HOME / HERMES_HOME /
 * HERMES_DESKTOP_USER_DATA_DIR, HERMES_DESKTOP_PYTHON + HERMES_DISABLE_LAZY_INSTALLS=1, private Xvfb.
 * Each shot records `ps` of the electron process tree at the instant of capture (the proof that a
 * real hermes/electron process produced it).
 */
import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import type { Page } from '@playwright/test'

import { buildEnv, createSandbox, installUnifiedPackage, launchDesktop, resolveCheckout, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute } from '../../desktop_ui.ts'

const { values } = parseArgs({ options: { job: { type: 'string' } } })
if (!values.job) throw new Error('--job job.json is required')
const job = JSON.parse(fs.readFileSync(values.job, 'utf8'))
const result: Record<string, any> = { job: values.job, shots: [], errors: [] }
const t0 = Date.now()

/** `ps` rows of `root` and all its descendants: pid ppid elapsed_s args. */
export function processTree(root: number): string {
  const raw = execFileSync('ps', ['-e', '-o', 'pid=,ppid=,etimes=,args='], { encoding: 'utf8' })
  const rows = raw.split('\n').map(l => l.trim().match(/^(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/)).filter(Boolean) as RegExpMatchArray[]
  const kids = new Map<number, RegExpMatchArray[]>()
  for (const r of rows) kids.set(+r[2], [...(kids.get(+r[2]) ?? []), r])
  const out = rows.filter(r => +r[1] === root)
  for (let i = 0; i < out.length; i++) out.push(...(kids.get(+out[i][1]) ?? []))
  return 'PID PPID ELAPSED_S ARGS\n' + out.map(r => `${r[1]} ${r[2]} ${r[3]} ${r[4]}`).join('\n') + '\n'
}

const box = async (page: Page, selector: string) => {
  const b = await page.locator(selector).first().boundingBox()
  return b ? [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)] : null
}

async function waitAck(page: Page, seq: number, ms = 20_000) {
  await page.waitForFunction(s => (window as any).__cfP1?.ack === s, seq, { timeout: ms })
  await page.waitForTimeout(300)
}

const sandbox = createSandbox('cf-p1h')
if (job.package) installUnifiedPackage(sandbox, job.package, 'cuttlefish')
if (job.seed) {
  const checkout = resolveCheckout(job.runtime)
  const env = buildEnv(sandbox, checkout, job.display)
  result.seed = execFileSync(job.seed.python, [job.seed.script, '--checkout', job.seed.checkout ?? checkout], {
    env: { ...env, PYTHONDONTWRITEBYTECODE: '1' }, encoding: 'utf8',
  }).trim()
}
result.sandbox = sandbox.root
result.hermes_home = sandbox.hermesHome

const l = await launchDesktop({ runtime: job.runtime, sandbox, display: job.display, width: job.width ?? 1900, height: job.height ?? 2900, gpu: !!job.gpu })
const page = l.page
result.sha = l.sha
result.checkout = l.checkout
result.electron_pid = l.app.process().pid
result.command = [l.app.process().spawnfile, ...(l.app.process().spawnargs ?? []).slice(1)].join(' ')
const elog = fs.createWriteStream(path.join(path.dirname(job.result), `electron-${job.gpu ? 'gpu' : 'dom'}.log`))
l.app.process().stdout?.pipe(elog)
l.app.process().stderr?.pipe(elog)

try {
  result.boot_ms = await waitForShell(page) + 0
  result.boot_total_ms = Date.now() - t0

  if (job.desktop?.length) {
    result.enabled = await enablePluginViaSettings(page, job.plugin_name ?? 'Cuttlefish')
    await gotoRoute(page, '/')
    await page.waitForFunction(() => (window as any).__cfP1?.setScene, null, { timeout: 30_000 })
    await page.evaluate(() => (window as any).__cfP1.revealField?.())
    await page.waitForSelector('[data-testid="cf-p1-field-box"]', { timeout: 30_000 })
    await page.waitForSelector('[data-testid^="cf-p1-swatch-"]', { timeout: 60_000 })
    await page.waitForTimeout(1500)
    result.plugin = await page.evaluate(() => ({ directions: (window as any).__cfP1.directions, loads: (window as any).__cfP1.loads, fixture: (window as any).__cfP1.fixtureSessions }))
    // The sessions column: everything left of the first vertical sash.
    const sash = await page.evaluate(() => {
      const s = [...document.querySelectorAll('[role="separator"]')].map(e => e.getBoundingClientRect()).filter(r => r.height > 400).sort((a, b) => a.x - b.x)[0]
      return s ? Math.round(s.x) : null
    })

    for (const shot of job.desktop) {
      const swatches: number[] = await page.evaluate(() =>
        [...document.querySelectorAll('[data-testid^="cf-p1-swatch-"]')].map(e => Number(e.getAttribute('data-testid')!.split('-').pop())))
      const seq = await page.evaluate(s => (window as any).__cfP1.setScene(s), { ...shot.scene, expectSwatches: swatches })
      await waitAck(page, seq)
      const ps = processTree(result.electron_pid)
      fs.mkdirSync(path.dirname(shot.file), { recursive: true })
      await page.screenshot({ path: shot.file })
      for (const tg of shot.targets) {
        let crop: number[] | null = null
        let tiles: unknown = null
        if (tg.kind === 'field') crop = await box(page, '[data-testid="cf-p1-field"]')
        else if (tg.kind === 'chip') crop = await box(page, '[data-testid="cf-p1-chip"]')
        else if (tg.kind === 'swatch') crop = await box(page, `[data-testid="cf-p1-swatch-${tg.idx}"]`)
        else if (tg.kind === 'sidebar') {
          const rects = await page.evaluate(() => [...document.querySelectorAll('[data-testid^="cf-p1-swatch-"]')].map(e => e.getBoundingClientRect().toJSON()))
          if (rects.length) {
            const y0 = Math.min(...rects.map(r => r.y)) - 8, y1 = Math.max(...rects.map(r => r.y + r.height)) + 8
            crop = [0, Math.round(y0), sash ?? 260, Math.round(y1 - y0)]
          }
          result.sidebar_rows = rects.length
          tiles = await page.evaluate(() => [...document.querySelectorAll('[data-testid^="cf-p1-swatch-"]')].map(e => {
            const r = e.getBoundingClientRect()
            return { session_idx: Number(e.getAttribute('data-testid')!.split('-').pop()), crop: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] }
          }).sort((a, b) => a.session_idx - b.session_idx))
        }
        result.shots.push({ id: tg.id, file: shot.file, crop, ps, seq, kind: tg.kind, tiles })
        if (!crop) result.errors.push(`${tg.id}: no crop for ${tg.kind}`)
      }
    }
    result.plugin_errors = await page.evaluate(() => (window as any).__cfP1.errors)
  }

  if (job.pane?.shots?.length) {
    const pn = job.pane
    const xterm = page.locator('.xterm').first()
    for (let i = 0; i < 5 && !(await xterm.isVisible().catch(() => false)); i++) {
      await page.keyboard.press('Control+Backquote')
      await page.waitForTimeout(2500)
    }
    await xterm.waitFor({ state: 'visible', timeout: 30_000 })
    // Widen the terminal column: drag the sash on its left edge (the user's gesture) toward the sidebar.
    const dragSash = async (toX: number) => {
      const pb = await xterm.boundingBox()
      const sx = await page.evaluate(px => {
        const s = [...document.querySelectorAll('[role="separator"]')].map(e => e.getBoundingClientRect()).filter(r => r.height > 400 && Math.abs(r.x + r.width / 2 - px) < 30)[0]
        return s ? s.x + s.width / 2 : null
      }, pb!.x)
      if (sx == null) throw new Error('no sash at the terminal column edge')
      const y = pb!.y - 200
      await page.mouse.move(sx, y); await page.mouse.down(); await page.mouse.move(toX, y, { steps: 20 }); await page.mouse.up()
      await page.waitForTimeout(800)
    }
    await dragSash(300)
    await xterm.click()
    fs.writeFileSync(pn.scene_path, JSON.stringify(pn.shots[0].scene))
    fs.rmSync(pn.ack_path, { force: true })
    await page.keyboard.type(pn.cmd, { delay: 2 })
    await page.keyboard.press('Enter')
    const readAck = () => { try { return JSON.parse(fs.readFileSync(pn.ack_path, 'utf8')) } catch { return null } }
    const until = async (pred: (a: any) => boolean, ms: number) => {
      const end = Date.now() + ms
      while (Date.now() < end) { const a = readAck(); if (a && pred(a)) return a; await page.waitForTimeout(250) }
      throw new Error(`pane: ack not observed; last ${JSON.stringify(readAck())}`)
    }
    let ack = await until(a => a.seq === pn.shots[0].scene.seq, 120_000)
    // Closed loop on the grid: nudge the sash until the TUI reports exactly `cols` columns.
    for (let i = 0; i < 6 && ack.cols !== pn.cols; i++) {
      const cellW = ((await xterm.boundingBox())!.width) / ack.cols
      const pb = (await xterm.boundingBox())!
      await dragSash(pb.x + (ack.cols - pn.cols) * cellW)
      await page.waitForTimeout(1500)
      ack = await until(() => true, 10_000)
    }
    result.pane_grid = { cols: ack.cols, rows: ack.term_rows }
    if (ack.cols !== pn.cols) result.errors.push(`pane: TUI has ${ack.cols} cols, wanted ${pn.cols}`)
    result.pane_renderer = await page.evaluate(() => {
      const el = document.querySelector('.xterm')
      return { canvases: el ? el.querySelectorAll('canvas').length : 0, domRows: !!el?.querySelector('.xterm-rows') }
    })
    for (const shot of pn.shots) {
      const tmp = pn.scene_path + '.tmp'
      fs.writeFileSync(tmp, JSON.stringify(shot.scene))
      fs.renameSync(tmp, pn.scene_path)
      const a = await until(x => x.seq === shot.scene.seq, 20_000)
      await page.waitForTimeout(600)
      const ps = processTree(result.electron_pid)
      const pb = (await xterm.boundingBox())!
      fs.mkdirSync(path.dirname(shot.file), { recursive: true })
      await page.screenshot({ path: shot.file, clip: pb })
      if (shot.ack_out) fs.writeFileSync(shot.ack_out, JSON.stringify(a))
      result.shots.push({ id: shot.id, file: shot.file, crop: null, ps, seq: shot.scene.seq, kind: 'pane', ack: a })
    }
  }
} catch (error) {
  result.errors.push(String((error as Error)?.stack ?? error))
  await page.screenshot({ path: path.join(path.dirname(job.result), `zz-failure-${job.gpu ? 'gpu' : 'dom'}.png`) }).catch(() => undefined)
} finally {
  await l.close()
  result.total_ms = Date.now() - t0
  if (!job.keep) fs.rmSync(sandbox.root, { recursive: true, force: true })
}
fs.writeFileSync(job.result, JSON.stringify(result, null, 1))
console.log(JSON.stringify({ result: job.result, shots: result.shots.length, errors: result.errors.length, boot_ms: result.boot_ms }))
process.exit(result.errors.length ? 1 : 0)
