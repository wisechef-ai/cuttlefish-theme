/**
 * Spike 07 — host.onEvent vocabulary + §1.3 state sources.
 *
 *   tools/spikes/run-desktop.sh 07-host-onevent-vocabulary [--runtime installed|upstream] [--out DIR] [--only a,b,c,d]
 *
 * Phases (each is its own throwaway sandbox + launch, approvals.mode=manual):
 *   main  : scenarios 1 plain reply, 2 tool call, 3 clarify, 4 approval (allow + deny)
 *   error : model base_url dead (127.0.0.1:9)
 *   kill  : SIGKILL the python backend mid-turn, record what the renderer sees
 * Everything the fixture records (window.__cfSpike.events / .states) is dumped as JSONL, plus a
 * DOM probe of every [role=status] dot so the amber SessionStatusDot is on screen.
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { execSync } from 'node:child_process'
import { parseArgs } from 'node:util'

import type { Page } from '@playwright/test'

import { createSandbox, installUnifiedPackage, launchDesktop, shot, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute } from '../../desktop_ui.ts'

const FIXTURE = path.resolve(import.meta.dirname, '..', 'fixtures', 'cf-spike')
const { values } = parseArgs({
  options: {
    runtime: { type: 'string', default: 'installed' },
    out: { type: 'string', default: path.join(process.env.TMPDIR || '/tmp', 'cf-spike07') },
    only: { type: 'string', default: 'main,error,kill' },
  },
})
const runtime = values.runtime!
const out = path.resolve(values.out!, runtime.replace(/[^\w-]/g, '_'))
fs.mkdirSync(out, { recursive: true })
const phases = values.only!.split(',')
const result: Record<string, any> = { runtime, phases: {} }

const mark = (page: Page, label: string) =>
  page.evaluate(l => (window as any).__cfSpike.events.push({ t: Date.now(), mark: l }), label)

async function send(page: Page, text: string) {
  const c = page.locator('[data-slot="composer-root"] [contenteditable="true"]:visible').first()
  await c.click()
  await page.keyboard.type(text, { delay: 5 })
  await page.keyboard.press('Enter')
}

/** DOM parity probe: every status dot + visible buttons in the main pane. */
const domDots = (page: Page) =>
  page.evaluate(() => ({
    dots: [...document.querySelectorAll('[role="status"]')].map(el => ({
      label: el.getAttribute('aria-label'), title: el.getAttribute('title'), cls: (el as HTMLElement).className,
      inSidebar: Boolean(el.closest('aside,nav,[data-sidebar]')),
    })),
    buttons: [...document.querySelectorAll('button')].filter(b => (b as HTMLElement).offsetParent).map(b => (b.textContent || b.getAttribute('aria-label') || '').trim().slice(0, 40)).filter(Boolean),
  }))

const busyNow = (page: Page) =>
  page.evaluate(() => {
    const s = (window as any).__cfSpike
    const st = s.host.state
    return { busy: st.busyBySession.get(), gw: st.gateway.get(), fs: st.focusedSessionId.get(), fst: st.focusedStoredSessionId.get() }
  })

async function waitTurn(page: Page, ms: number, until: (dots: any) => boolean = () => false) {
  const t0 = Date.now()
  let seenBusy = false
  while (Date.now() - t0 < ms) {
    const b = await busyNow(page)
    const anyBusy = Object.values(b.busy ?? {}).some(Boolean)
    seenBusy ||= anyBusy
    const d = await domDots(page)
    if (until(d)) return 'until'
    if (seenBusy && !anyBusy) return 'idle'
    await page.waitForTimeout(500)
  }
  return 'timeout'
}

async function boot(sub: string, opts: { modelBaseUrl?: string; extra?: string }) {
  const sandbox = createSandbox(`cf-s07-${sub}`)
  installUnifiedPackage(sandbox, FIXTURE, 'cf-spike')
  const l = await launchDesktop({ runtime, sandbox, modelBaseUrl: opts.modelBaseUrl, extraConfig: `approvals:\n  mode: manual\n${opts.extra ?? ''}` })
  fs.mkdirSync(path.join(out, sub), { recursive: true })
  const log = fs.createWriteStream(path.join(out, sub, 'electron.log'))
  l.app.process().stdout?.pipe(log)
  l.app.process().stderr?.pipe(log)
  await waitForShell(l.page)
  await enablePluginViaSettings(l.page, 'CF Spike')
  await gotoRoute(l.page, '/')
  await l.page.waitForSelector('[data-testid="cf-spike-chip"]', { timeout: 30_000 })
  await l.page.waitForTimeout(1000)
  // DOM-parity timeline: every change of the set of [role=status] labels (core's SessionStatusDot
  // is a span role=status with aria-label; idle dots are aria-hidden and have no label).
  await l.page.evaluate(() => {
    const s = (window as any).__cfSpike
    s.dots = []
    let last = ''
    setInterval(() => {
      const cur = [...document.querySelectorAll('[role="status"]')]
        .map(el => `${el.closest('aside,nav,[data-sidebar]') ? 'side' : 'main'}:${el.getAttribute('aria-label') ?? ''}`)
        .filter(x => !x.endsWith(':') && !/:Loading$/.test(x))
        .sort().join('|')
      if (cur !== last) { last = cur; s.dots.push({ t: Date.now(), dots: cur }) }
    }, 200)
  })
  return { l, sandbox }
}

async function dump(page: Page, sub: string) {
  const d = await page.evaluate(() => {
    const s = (window as any).__cfSpike
    return { events: s.events, states: s.states, dots: s.dots ?? [] }
  }).catch(e => ({ events: [], states: [], dots: [], err: String(e) }))
  fs.writeFileSync(path.join(out, sub, 'dots.jsonl'), d.dots.map((e: any) => JSON.stringify(e)).join('\n') + '\n')
  fs.writeFileSync(path.join(out, sub, 'events.jsonl'), d.events.map((e: any) => JSON.stringify(e)).join('\n') + '\n')
  fs.writeFileSync(path.join(out, sub, 'states.jsonl'), d.states.map((e: any) => JSON.stringify(e)).join('\n') + '\n')
  return d
}

const clickText = async (page: Page, re: RegExp) => {
  const b = page.getByRole('button', { name: re }).first()
  await b.click({ timeout: 8000 })
}

if (phases.includes('main')) {
  const r: Record<string, any> = (result.phases.main = {})
  const { l, sandbox } = await boot('main', {})
  const p = l.page
  const victim = path.join(sandbox.root, 'victim-x')
  fs.mkdirSync(victim, { recursive: true })
  fs.writeFileSync(path.join(victim, 'f.txt'), 'x')
  try {
    // 1 plain reply
    await mark(p, 'S1 plain start')
    await send(p, 'Reply with exactly the single word: pong')
    r.s1 = await waitTurn(p, 300_000)
    await mark(p, 'S1 plain end')
    await shot(p, path.join(out, 'main', 's1-plain.png'))

    // 2 tool call
    await mark(p, 'S2 tool start')
    await send(p, 'Use the terminal tool to run: echo hi   Then tell me its output.')
    r.s2 = await waitTurn(p, 180_000, d => d.dots.some((x: any) => /needs|answer|input/i.test(x.label ?? '')))
    r.s2dom = await domDots(p)
    await shot(p, path.join(out, 'main', 's2-tool.png'))
    if (r.s2 === 'until') {
      await clickText(p, /^(run|allow|once)/i).catch(e => (r.s2click = String(e)))
      r.s2after = await waitTurn(p, 120_000)
    }
    await mark(p, 'S2 tool end')

    // 3 clarify
    await mark(p, 'S3 clarify start')
    await send(p, 'Call the clarify tool right now and ask me: "Which colour, red or blue?" with choices red and blue. Do not answer yourself; you MUST call the clarify tool and wait.')
    r.s3 = await waitTurn(p, 150_000, d => d.dots.some((x: any) => /needs|answer|input/i.test(x.label ?? '')))
    r.s3dom = await domDots(p)
    r.s3busy = await busyNow(p)
    await shot(p, path.join(out, 'main', 's3-clarify-pending.png'))
    if (r.s3 === 'until') {
      await mark(p, 'S3 answer click')
      await p.getByText('blue', { exact: true }).first().click({ timeout: 8000 }).catch(e => (r.s3click = String(e)))
      await p.getByRole('button', { name: /confirm and continue/i }).first().click({ timeout: 8000 }).catch(e => (r.s3click2 = String(e)))
      r.s3after = await waitTurn(p, 120_000)
    }
    await mark(p, 'S3 clarify end')

    // 4 approval (allow) then approval (deny)
    await mark(p, 'S4 approval start')
    await send(p, `Use the terminal tool to run exactly: rm -rf ${victim}`)
    r.s4 = await waitTurn(p, 150_000, d => d.dots.some((x: any) => /needs|answer|input/i.test(x.label ?? '')))
    r.s4dom = await domDots(p)
    r.s4busy = await busyNow(p)
    await shot(p, path.join(out, 'main', 's4-approval-pending.png'))
    if (r.s4 === 'until') {
      await mark(p, 'S4 click deny')
      await clickText(p, /^(reject|deny)/i).catch(e => (r.s4click = String(e)))
      r.s4after = await waitTurn(p, 120_000)
    }
    await mark(p, 'S4 approval end')
    r.victimSurvivedDeny = fs.existsSync(victim)
    await shot(p, path.join(out, 'main', 's4-after.png'))
  } catch (e) {
    r.error = String((e as Error).stack ?? e)
    await shot(p, path.join(out, 'main', 'zz-fail.png')).catch(() => undefined)
  }
  r.finalDom = await domDots(p).catch(() => null)
  r.counts = countTypes((await dump(p, 'main')).events)
  await l.close()
  fs.rmSync(sandbox.root, { recursive: true, force: true })
}

if (phases.includes('error')) {
  const r: Record<string, any> = (result.phases.error = {})
  const { l, sandbox } = await boot('error', { modelBaseUrl: 'http://127.0.0.1:9/v1' })
  const p = l.page
  try {
    await mark(p, 'E start')
    await send(p, 'hello')
    r.turn = await waitTurn(p, 150_000)
    await p.waitForTimeout(3000)
    r.dom = await domDots(p)
    r.text = (await p.evaluate(() => document.body.innerText)).slice(-600)
    await shot(p, path.join(out, 'error', 'e-fault.png'))
  } catch (e) {
    r.error = String((e as Error).stack ?? e)
  }
  r.counts = countTypes((await dump(p, 'error')).events)
  await l.close()
  fs.rmSync(sandbox.root, { recursive: true, force: true })
}

if (phases.includes('kill')) {
  const r: Record<string, any> = (result.phases.kill = {})
  const { l, sandbox } = await boot('kill', {})
  const p = l.page
  try {
    await send(p, 'Write a 600 word essay about octopuses.')
    await p.waitForFunction(() => Object.values((window as any).__cfSpike.host.state.busyBySession.get() ?? {}).some(Boolean), null, { timeout: 60_000 })
    await p.waitForTimeout(2000)
    r.before = await busyNow(p)
    // the backend is the python child of electron carrying this sandbox's HERMES_HOME
    const pids = execSync(`pgrep -f "tui_gateway|hermes_cli.*(web|serve|dashboard)|hermes.*--port" || true`, { encoding: 'utf8' }).trim().split('\n').filter(Boolean)
    const mine: string[] = []
    for (const pid of pids) {
      try {
        const env = fs.readFileSync(`/proc/${pid}/environ`, 'utf8')
        if (env.includes(sandbox.hermesHome)) mine.push(pid)
      } catch { /* gone */ }
    }
    r.killed = mine
    await mark(p, `K kill ${mine.join(',')}`)
    for (const pid of mine) { try { process.kill(Number(pid), 'SIGKILL') } catch { /* */ } }
    for (const s of [1, 3, 8, 20]) {
      await p.waitForTimeout(s * 1000)
      r[`t+${s}s`] = { st: await busyNow(p).catch(e => String(e)), dom: await domDots(p).catch(() => null) }
    }
    await shot(p, path.join(out, 'kill', 'k-after.png'))
  } catch (e) {
    r.error = String((e as Error).stack ?? e)
    await shot(p, path.join(out, 'kill', 'zz-fail.png')).catch(() => undefined)
  }
  r.counts = countTypes((await dump(p, 'kill')).events)
  await l.close().catch(() => undefined)
  fs.rmSync(sandbox.root, { recursive: true, force: true })
}

function countTypes(events: any[]) {
  const c: Record<string, number> = {}
  for (const e of events) c[e.event?.type ?? `mark:${e.mark}`] = (c[e.event?.type ?? `mark:${e.mark}`] ?? 0) + 1
  return c
}

fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(result, null, 2))
console.log(JSON.stringify(result, null, 2))
process.exit(0)
