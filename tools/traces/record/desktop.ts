/**
 * Desktop trace recorder: the real Electron build of the upstream runtime, driven with Playwright
 * (adapted from tools/spikes/07-host-onevent-vocabulary/run.ts, which proved the vocabulary).
 *
 *   CF_DISPLAY=:111 tools/spikes/run-desktop.sh ../traces/record/desktop.ts   # via the wrapper below, or:
 *   CF_DISPLAY=:111 tools/traces/record/run-desktop.sh [--only main,error,kill]
 *
 * Phases (each = its own throwaway sandbox + launch, approvals.mode=manual, model custom:qwen38-local):
 *   main  -> desktop-main   : plain turn, clarify answered, approval rejected
 *   error -> desktop-error  : dead model base_url; the turn ends with message.complete status:'error' (needs ~9 min)
 *   kill  -> desktop-kill   : SIGKILL the python backend mid-turn
 * Raw (unscrubbed) recording -> vault projects/cuttlefish-theme/p2/traces-raw/<name>/ ; the repo file
 * tools/traces/<name>.jsonl is produced by record/convert.py (whitelist only).
 */
import { execFileSync, execSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import type { Page } from '@playwright/test'

import { createSandbox, installUnifiedPackage, launchDesktop, shot, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute } from '../../desktop_ui.ts'

const HERE = import.meta.dirname
const REPO = path.resolve(HERE, '..', '..', '..')
const FIXTURE = path.resolve(HERE, '..', '..', 'spikes', 'fixtures', 'cf-spike')
const RAW_ROOT =
  process.env.CF_TRACES_RAW || path.join(os.homedir(), 'obsidian-vault', 'projects', 'cuttlefish-theme', 'p2', 'traces-raw')
const MODEL = 'custom:qwen38-local'

const { values } = parseArgs({ options: { only: { type: 'string', default: 'main,error,kill' } } })
const phases = values.only!.split(',')

const runtimeSha = execSync(
  `git -C ${path.join(os.homedir(), '.worktrees/hermes-agent/cf2909-upstream')} rev-parse --short=11 HEAD`,
  { encoding: 'utf8' }
).trim()

const mark = (page: Page, label: string) =>
  page.evaluate(l => (window as any).__cfSpike.events.push({ t: Date.now(), mark: l }), label)

async function send(page: Page, text: string) {
  const c = page.locator('[data-slot="composer-root"] [contenteditable="true"]:visible').first()
  await c.click()
  await page.keyboard.type(text, { delay: 5 })
  await page.keyboard.press('Enter')
}

const dotLabels = (page: Page) =>
  page.evaluate(() => [...document.querySelectorAll('[role="status"]')].map(el => el.getAttribute('aria-label') ?? ''))

const busyNow = (page: Page) =>
  page.evaluate(() => {
    const s = (window as any).__cfSpike
    const st = s.host.state
    return { busy: st.busyBySession.get(), gw: st.gateway.get() }
  })

/** Wait until a turn has started and then finished (busy true -> false), or `until(dots)` is satisfied. */
async function waitTurn(page: Page, ms: number, until: (labels: string[]) => boolean = () => false) {
  const t0 = Date.now()
  let seenBusy = false
  while (Date.now() - t0 < ms) {
    const b = await busyNow(page)
    const anyBusy = Object.values(b.busy ?? {}).some(Boolean)
    seenBusy ||= anyBusy
    if (until(await dotLabels(page))) return 'until'
    if (seenBusy && !anyBusy) return 'idle'
    await page.waitForTimeout(500)
  }
  return 'timeout'
}

const needsInput = (labels: string[]) => labels.some(l => /needs your input/i.test(l))

async function boot(name: string, opts: { modelBaseUrl?: string }) {
  const sandbox = createSandbox(`cf-trace-${name}`)
  installUnifiedPackage(sandbox, FIXTURE, 'cf-spike')
  const t0 = Date.now() / 1000
  const l = await launchDesktop({ runtime: 'upstream', sandbox, modelBaseUrl: opts.modelBaseUrl, extraConfig: 'approvals:\n  mode: manual\n' })
  await waitForShell(l.page)
  await enablePluginViaSettings(l.page, 'CF Spike')
  await gotoRoute(l.page, '/')
  await l.page.waitForSelector('[data-testid="cf-spike-chip"]', { timeout: 30_000 })
  await l.page.waitForTimeout(1000)
  // DOM-parity timeline: every change of the set of [role=status] labels (core's SessionStatusDot).
  await l.page.evaluate(() => {
    const s = (window as any).__cfSpike
    s.dots = []
    let last = ''
    setInterval(() => {
      const cur = [...document.querySelectorAll('[role="status"]')]
        .map(el => `${el.closest('aside,nav,[data-sidebar]') ? 'side' : 'main'}:${el.getAttribute('aria-label') ?? ''}`)
        .filter(x => !x.endsWith(':') && !/:Loading$/.test(x))
        .sort()
        .join('|')
      if (cur !== last) {
        last = cur
        s.dots.push({ t: Date.now(), dots: cur })
      }
    }, 200)
  })
  return { l, sandbox, t0 }
}

/** Dump the page's recorded events/states/dots + a state.db copy, then convert to the repo trace. */
async function finish(name: string, page: Page, sandbox: any, t0: number, notes: string) {
  const raw = path.join(RAW_ROOT, name)
  fs.rmSync(raw, { recursive: true, force: true })
  fs.mkdirSync(raw, { recursive: true })
  const d = await page.evaluate(() => {
    const s = (window as any).__cfSpike
    return { events: s.events, states: s.states, dots: s.dots ?? [] }
  })
  for (const k of ['events', 'states', 'dots'] as const) {
    fs.writeFileSync(path.join(raw, `${k}.jsonl`), d[k].map((e: any) => JSON.stringify(e)).join('\n') + '\n')
  }
  const db = path.join(sandbox.hermesHome, 'state.db')
  if (fs.existsSync(db)) {
    execFileSync('python3', ['-c', 'import sqlite3,sys\ns=sqlite3.connect("file:%s?mode=ro"%sys.argv[1],uri=True);d=sqlite3.connect(sys.argv[2]);s.backup(d);d.close()', db, path.join(raw, 'state-A.db')])
  }
  fs.writeFileSync(
    path.join(raw, 'meta.json'),
    JSON.stringify({ name, host: 'desktop', runtime: 'upstream', runtime_sha: runtimeSha, recorded_at: new Date(t0 * 1000).toISOString().replace(/\.\d+Z$/, 'Z'), model: MODEL, profiles: ['A'], notes, t0 }, null, 1)
  )
  await shot(page, path.join(raw, 'final.png')).catch(() => undefined)
  const out = path.join(REPO, 'tools', 'traces', `${name}.jsonl`)
  console.log(execFileSync('python3', [path.join(HERE, 'convert.py'), raw, out], { encoding: 'utf8' }).trim())
}

if (phases.includes('main')) {
  const { l, sandbox, t0 } = await boot('main', {})
  const p = l.page
  const victim = path.join(sandbox.root, 'victim-x')
  fs.mkdirSync(victim, { recursive: true })
  fs.writeFileSync(path.join(victim, 'f.txt'), 'x')
  try {
    await mark(p, 'turn start')
    await send(p, 'Reply with exactly the single word: pong')
    console.log('turn', await waitTurn(p, 300_000))
    await mark(p, 'clarify start')
    await send(p, 'Call the clarify tool right now and ask me: "Which colour, red or blue?" with choices red and blue. Do not answer yourself; you MUST call the clarify tool and wait.')
    const c = await waitTurn(p, 180_000, needsInput)
    console.log('clarify pending', c)
    if (c === 'until') {
      await p.waitForTimeout(3000) // pending: needs-you must hold
      await p.getByText('blue', { exact: true }).first().click({ timeout: 8000 })
      await p.getByRole('button', { name: /confirm and continue/i }).first().click({ timeout: 8000 })
      console.log('clarify answered', await waitTurn(p, 120_000))
    }
    await mark(p, 'approval start')
    await send(p, `Use the terminal tool to run exactly: rm -rf ${victim}`)
    const a = await waitTurn(p, 180_000, needsInput)
    console.log('approval pending', a)
    if (a === 'until') {
      await p.waitForTimeout(3000)
      await p.getByRole('button', { name: /^(reject|deny)/i }).first().click({ timeout: 8000 })
      console.log('approval rejected', await waitTurn(p, 120_000))
    }
    console.log('victim survived reject:', fs.existsSync(victim))
    await p.waitForTimeout(1500)
  } finally {
    await finish('desktop-main', p, sandbox, t0, 'plain turn, clarify answered by clicking a choice, approval Reject; dots sampled every 200 ms from core SessionStatusDot')
    await l.close().catch(() => undefined)
    fs.rmSync(sandbox.root, { recursive: true, force: true })
  }
}

if (phases.includes('error')) {
  const { l, sandbox, t0 } = await boot('error', { modelBaseUrl: 'http://127.0.0.1:9/v1' })
  const p = l.page
  try {
    await send(p, 'hello')
    console.log('error turn', await waitTurn(p, 600_000))
    await p.waitForTimeout(3000)
  } finally {
    await finish('desktop-error', p, sandbox, t0, 'dead model base_url: retries then message.complete status error; core paints no dot for the fault')
    await l.close().catch(() => undefined)
    fs.rmSync(sandbox.root, { recursive: true, force: true })
  }
}

if (phases.includes('kill')) {
  const { l, sandbox, t0 } = await boot('kill', {})
  const p = l.page
  try {
    await send(p, 'Write a 600 word essay about octopuses.')
    await p.waitForFunction(() => Object.values((window as any).__cfSpike.host.state.busyBySession.get() ?? {}).some(Boolean), null, { timeout: 60_000 })
    await p.waitForTimeout(2000)
    // the backend is the python child carrying this sandbox's HERMES_HOME
    const pids = execSync('pgrep -f "tui_gateway|hermes_cli.*(web|serve|dashboard)|hermes.*--port" || true', { encoding: 'utf8' }).trim().split('\n').filter(Boolean)
    const mine: string[] = []
    for (const pid of pids) {
      try {
        if (fs.readFileSync(`/proc/${pid}/environ`, 'utf8').includes(sandbox.hermesHome)) mine.push(pid)
      } catch { /* gone */ }
    }
    await mark(p, 'kill backend')
    console.log('killing', mine.length, 'backend process(es)')
    if (!mine.length) throw new Error('no backend process found for the sandbox')
    for (const pid of mine) {
      try { process.kill(Number(pid), 'SIGKILL') } catch { /* */ }
    }
    await p.waitForTimeout(35_000) // upstream keeps busy=true ~26 s after the kill
  } finally {
    await finish('desktop-kill', p, sandbox, t0, 'SIGKILL of the python backend mid-turn: gateway closed/connecting/open, busy stale for a while, core dot stale')
    await l.close().catch(() => undefined)
    fs.rmSync(sandbox.root, { recursive: true, force: true })
  }
}

process.exit(0)
