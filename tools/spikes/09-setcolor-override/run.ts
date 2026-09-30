/**
 * Spike 09 — host.sessions.setColor persistence + user-override detection.
 *   tools/spikes/run-desktop.sh 09-setcolor-override [--runtime installed|upstream] [--out DIR]
 * Stages (result.json + PNGs):
 *  1 two real sessions A(alpha) B(beta) via the composer ($0 qwen38)
 *  2 plugin setColor(A) -> localStorage key, sidebar row + tab dot pixels
 *  3 USER picks a colour on B through the real row menu (Appearance ▸ swatch)
 *  4 detection: (i) ledger reconcile  (ii) localStorage.setItem wrapper; plugin re-run must not clobber B
 *  5 setColor(A,null) -> what renders
 *  6 relaunch same sandbox -> colours survive?   7 second window   8 backend never sees it (grep sandbox)
 */
import { execSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { parseArgs } from 'node:util'
import type { Page } from '@playwright/test'

import { createSandbox, installUnifiedPackage, launchDesktop, shot, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute } from '../../desktop_ui.ts'

const FIXTURE = path.resolve(import.meta.dirname, '..', 'fixtures', 'cf-spike')
const { values } = parseArgs({
  options: {
    runtime: { type: 'string', default: 'installed' },
    out: { type: 'string', default: path.join(process.env.TMPDIR || '/tmp', 'cf-spike09') },
  },
})
const out = path.resolve(values.out!, values.runtime! + (process.env.CF_NOHOOK ? '-nohook' : ''))
fs.mkdirSync(out, { recursive: true })
const KEY = 'hermes.desktop.sessionColors'
const PLUGIN_HEX = '#e0457b'
const NOHOOK = !!process.env.CF_NOHOOK
const R: Record<string, any> = { runtime: values.runtime, nohook: NOHOOK }

const sandbox = createSandbox('cf-s09')
installUnifiedPackage(sandbox, FIXTURE, 'cf-spike')

const ls = (p: Page) => p.evaluate(k => localStorage.getItem(k), KEY)
const send = async (p: Page, t: string) => {
  const ed = p.locator('[data-slot="composer-root"] [contenteditable="true"]:visible').first()
  await ed.click()
  await p.keyboard.type(t)
  await p.keyboard.press('Enter')
}
const idle = async (p: Page, ms = 150_000) => {
  const t0 = Date.now()
  await p.waitForTimeout(3000)
  while (Date.now() - t0 < ms) {
    const busy = await p.evaluate(() => Object.values((window as any).__cfSpike.states.at(-1).busyBySession || {}).some(Boolean) || !!document.querySelector('[aria-label="Session running"]'))
    if (!busy) return Date.now() - t0
    await p.waitForTimeout(1000)
  }
  return -1
}
const stored = (p: Page) => p.evaluate(() => (window as any).__cfSpike.states.at(-1).focusedStoredSessionId as string)

// Every element whose computed background/border is (r,g,b) — the colour dot(s), with a rect + ancestor hint.
const paint = (p: Page, hex: string) =>
  p.evaluate(h => {
    const n = parseInt(h.slice(1), 16)
    const want = `rgb(${n >> 16}, ${(n >> 8) & 255}, ${n & 255})`
    const hits: any[] = []
    for (const el of document.querySelectorAll<HTMLElement>('*')) {
      const cs = getComputedStyle(el)
      const bg = cs.backgroundColor, bc = cs.borderTopColor, c = cs.color
      const r = el.getBoundingClientRect()
      if ((bg === want || (bc === want && cs.borderTopWidth !== '0px') || c === want) && r.width > 0 && r.width < 40 && r.height > 0)
        hits.push({ w: Math.round(r.width), x: Math.round(r.x), y: Math.round(r.y), zone: r.y < 40 ? 'tabstrip' : r.x < 260 ? 'sidebar' : 'other', cls: (el.className?.toString?.() || '').slice(0, 60) })
    }
    return { want, hits }
  }, hex)

// every status dot on screen (sidebar rows + tab strip): computed bg + class, so a hidden colour is explained
const dots = (p: Page) =>
  p.evaluate(() => {
    const wordOf = (el: HTMLElement) => {
      for (let n: HTMLElement | null = el; n; n = n.parentElement) {
        const t = n.innerText || ''
        const a = /\balpha\b/i.test(t), b = /\bbeta\b/i.test(t)
        if (a !== b) return a ? 'alpha' : 'beta'
      }
      return '?'
    }
    return [...document.querySelectorAll<HTMLElement>('span.rounded-full')]
      .map(el => ({ el, r: el.getBoundingClientRect(), cs: getComputedStyle(el) }))
      .filter(x => x.r.width > 0 && x.r.width < 12 && x.r.height < 12 && (x.r.y < 40 || (x.r.x < 60 && x.r.y > 380)))
      .map(x => ({ zone: x.r.y < 40 ? 'tab' : 'row', word: x.r.y < 40 ? '(tab)' : wordOf(x.el), bg: x.cs.backgroundColor.replace(/color\(srgb .*/, 'grey-idle'), aria: x.el.getAttribute('aria-label') || '' }))
      .sort((a, b) => a.zone.localeCompare(b.zone) || a.word.localeCompare(b.word))
  })
// index of the sidebar row's action button for a session word
const btnIdx = (p: Page, word: string) =>
  p.evaluate(w => {
    const btns = [...document.querySelectorAll<HTMLElement>('[aria-label="Session actions"]')]
    return btns.findIndex(b => { for (let n: HTMLElement | null = b; n; n = n.parentElement) { const t = n.innerText || ''; const a = /\balpha\b/i.test(t), b = /\bbeta\b/i.test(t); if (a !== b) return (w === 'alpha') === a } return false })
  }, word)

// wait until the dot readout is stable for 2.5s (cap 20s); returns ms taken, so lag is measured not guessed
const settle = async (p: Page) => {
  const t0 = Date.now()
  let prev = '', since = Date.now()
  while (Date.now() - t0 < 20000) {
    const cur = JSON.stringify(await dots(p))
    if (cur !== prev) { prev = cur; since = Date.now() } else if (Date.now() - since > 2500) break
    await p.waitForTimeout(300)
  }
  return Date.now() - t0
}

async function boot(sb = sandbox) {
  const l = await launchDesktop({ runtime: values.runtime, sandbox: sb })
  await waitForShell(l.page)
  return l
}

let l = await boot()
R.sha = l.sha
R.checkout = l.checkout
const p = l.page
try {
  await enablePluginViaSettings(p, 'CF Spike')
  await gotoRoute(p, '/')
  await p.waitForTimeout(1500)

  // 1 sessions
  await send(p, 'Reply with just the word alpha.')
  R.idleA = await idle(p)
  const A = await stored(p)
  await p.keyboard.press('Control+n')
  await p.waitForTimeout(2000)
  await send(p, 'Reply with just the word beta.')
  R.idleB = await idle(p)
  const B = await stored(p)
  R.ids = { A, B }
  R.lsInitial = await ls(p)
  await shot(p, path.join(out, '01-two-sessions.png'))

  // install the detection layer INSIDE the renderer, exactly what a plugin could do (same-origin localStorage).
  await p.evaluate(({ KEY, NOHOOK }) => {
    const w = window as any
    const ctx = w.__cfSpike.ctx
    const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') } catch { return {} } }
    const det = (w.__cfDet = { ledger: ctx.storage.get('ledger', {}), userPicks: [] as any[], own: 0, hookCalls: 0 })
    // (ii) synchronous hook on setItem: anything that writes KEY while we are not inside our own write is the app/user.
    const orig = Storage.prototype.setItem
    if (!NOHOOK) Storage.prototype.setItem = function (k: string, v: string) {
      if (k === KEY && this === localStorage) {
        det.hookCalls++
        const before = read()
        const res = orig.call(this, k, v)
        const after = read()
        if (det.own) return res
        for (const id of new Set([...Object.keys(before), ...Object.keys(after)]))
          if (before[id] !== after[id]) det.userPicks.push({ id, from: before[id] ?? null, to: after[id] ?? null })
        return res
      }
      return orig.call(this, k, v)
    }
    // (i) ledger reconcile: apply() writes only when the stored value is absent or equals what WE last wrote.
    w.__cfApply = (id: string, color: string | null) => {
      const cur = read()[id]
      const mine = det.ledger[id]
      if (cur !== undefined && cur !== mine) return { wrote: false, reason: 'user-owned(value differs)', cur, mine: mine ?? null }
      if (cur === undefined && mine !== undefined && color !== null) return { wrote: false, reason: 'user-owned(cleared our colour)', cur: null, mine }
      det.own++
      try { w.__cfSpike.setColor(id, color) } finally { det.own-- }
      if (color) det.ledger[id] = color; else delete det.ledger[id]
      ctx.storage.set('ledger', det.ledger)
      return { wrote: true, cur: cur ?? null }
    }
  }, { KEY, NOHOOK })

  // 2 plugin write on A (through the ledgered apply)
  R.applyA = await p.evaluate(([id, c]) => (window as any).__cfApply(id, c), [A, PLUGIN_HEX])
  await p.waitForTimeout(800)
  R.afterPluginA = { ls: await ls(p), paint: await paint(p, PLUGIN_HEX), userPicksSeen: await p.evaluate(() => (window as any).__cfDet.userPicks) }
  await p.locator('[aria-label="Session actions"]').nth(await btnIdx(p, 'alpha')).locator('xpath=ancestor::*[contains(@class,"group")][1]').click({ position: { x: 60, y: 10 }, force: true }).catch(() => undefined)
  await p.waitForTimeout(1500)
  R.afterFocusA = { focused: await stored(p), paint: await paint(p, PLUGIN_HEX) }
  // poll: how long until the SIDEBAR ROW dot turns pink (tab dot is immediate)
  {
    const t0 = Date.now()
    let rowMs: number | null = null
    while (Date.now() - t0 < 30000) {
      if ((await dots(p)).some(d => d.zone === 'row' && d.word === 'alpha' && d.bg === 'rgb(224, 69, 123)')) { rowMs = Date.now() - t0; break }
      await p.waitForTimeout(250)
    }
    R.rowPinkAfterMs = rowMs
  }
  R.dots02 = await dots(p)
  await shot(p, path.join(out, '02-plugin-color-A.png'))

  // 3 user picks on B through the real UI: row menu -> Appearance -> swatch
  const USER_LABEL = 'hsl(210 68% 58%)'
  const rowsInfo = async () => p.evaluate(() => [...document.querySelectorAll('[aria-label="Session actions"]')].map(e => e.parentElement?.innerText.replace(/\s+/g, ' ').slice(0, 50)))
  R.rowsInfo = await dots(p)
  const pickViaUI = async (rowIdx: number, label: string) => {
    await p.evaluate(() => { (window as any).__cfDet.userPicks.length = 0 })
    await p.locator('[aria-label="Session actions"]').nth(rowIdx).click({ force: true })
    await p.getByText('Appearance', { exact: true }).first().hover()
    await p.waitForTimeout(700)
    await (label === 'No color' ? p.getByText('No color', { exact: true }).first() : p.locator(`[aria-label="${label}"]`).first()).click()
    await p.waitForTimeout(700)
    await p.keyboard.press('Escape')
    await p.waitForTimeout(500)
  }
  // rows carry no id in the DOM; the list is newest-first (B created after A), so A = row 1, B = row 0.
    await pickViaUI(await btnIdx(p, 'beta'), USER_LABEL)
  R.afterUserB = {
    ls: await ls(p),
    userPicksSeen: await p.evaluate(() => (window as any).__cfDet.userPicks),
    paint: await paint(p, '#4b94dd'),
  }
  R.settle_dots03 = await settle(p)
  R.dots03 = await dots(p)
  await shot(p, path.join(out, '03-user-picked-B.png'))

  // 4 plugin re-run must not clobber B
  R.rerun = {
    B_apply: await p.evaluate(([id, c]) => (window as any).__cfApply(id, c), [B, PLUGIN_HEX]),
    A_apply_same: await p.evaluate(([id, c]) => (window as any).__cfApply(id, c), [A, PLUGIN_HEX]),
    lsAfter: await ls(p),
  }
  // control: the naive plugin (no guard) DOES clobber the user's pick
  await p.evaluate(([id, c]) => (window as any).__cfSpike.setColor(id, c), [B, PLUGIN_HEX])
  R.naiveClobber = { ls: await ls(p) }
  // restore user's pick through the UI for the remaining stages
  await pickViaUI(await btnIdx(p, 'beta'), USER_LABEL)
  R.userRestored = await ls(p)
  // user overrides A (plugin-owned) through the UI, then plugin re-run
  await pickViaUI(await btnIdx(p, 'alpha'), 'hsl(120 68% 58%)')
  R.afterUserOverridesA = { ls: await ls(p), picks: await p.evaluate(() => (window as any).__cfDet.userPicks), rerunA: await p.evaluate(([id, c]) => (window as any).__cfApply(id, c), [A, PLUGIN_HEX]) }
  // user clears A ("No color"), then plugin re-run
  await pickViaUI(await btnIdx(p, 'alpha'), 'No color')
  R.afterUserClearsA = { ls: await ls(p), picks: await p.evaluate(() => (window as any).__cfDet.userPicks), rerunA: await p.evaluate(([id, c]) => (window as any).__cfApply(id, c), [A, PLUGIN_HEX]) }
  // same-colour edge: user picks exactly our hex? (indistinguishable) — plugin colour is off-palette, so document via direct write
  R.settle_dots04 = await settle(p)
  R.dots04 = await dots(p)
  await shot(p, path.join(out, '04-after-user-overrides-A.png'))

  // 5 null: plugin-owned colour -> restore. Give A back the plugin colour first (ledger cleared by hand: plugin "forgets")
  await p.evaluate(([id, c]) => { (window as any).__cfDet.ledger = {}; (window as any).__cfSpike.setColor(id, c) }, [A, PLUGIN_HEX])
  await p.waitForTimeout(600)
  R.settle_dots05a = await settle(p)
  R.dots05a = await dots(p)
  await shot(p, path.join(out, '05a-A-pink-before-null.png'))
  await p.evaluate(id => (window as any).__cfSpike.setColor(id, null), A)
  { const t0 = Date.now(); let ms: number | null = null; while (Date.now() - t0 < 20000) { if (!(await dots(p)).some(d => d.zone === 'row' && d.word === 'alpha' && d.bg === 'rgb(224, 69, 123)')) { ms = Date.now() - t0; break } await p.waitForTimeout(250) } R.rowPinkClearedAfterMs = ms }
  R.afterNullA = { ls: await ls(p), paintPink: (await paint(p, PLUGIN_HEX)).hits.length }
  R.settle_dots05 = await settle(p)
  R.dots05 = await dots(p)
  await shot(p, path.join(out, '05-after-null-A.png'))
  // put plugin colour on A again and persist ledger for the relaunch
  R.applyA2 = await p.evaluate(([id, c]) => { (window as any).__cfDet.ledger = {}; return (window as any).__cfApply(id, c) }, [A, PLUGIN_HEX])
  R.beforeRestart = { ls: await ls(p), ledger: await p.evaluate(() => (window as any).__cfSpike.ctx.storage.get('ledger', null)), lsKeys: await p.evaluate(() => Object.keys(localStorage).filter(k => /cf-spike|sessionColors/.test(k))) }
  await shot(p, path.join(out, '06-before-restart.png'))
  await p.waitForTimeout(1500)
  await l.close()

  // 6 relaunch same sandbox
  l = await boot()
  const p2 = l.page
  await enablePluginViaSettings(p2, 'CF Spike').catch(() => undefined)
  await gotoRoute(p2, '/'); await p2.waitForTimeout(2500)
  R.afterRestart = {
    ls: await ls(p2),
    ledger: await p2.evaluate(() => (window as any).__cfSpike?.ctx?.storage.get('ledger', null)),
    paintPink: (await paint(p2, PLUGIN_HEX)).hits,
    paintUser: (await paint(p2, '#4b94dd')).hits,
    rows: await p2.evaluate(() => [...document.querySelectorAll('[aria-label="Session actions"]')].map(e => e.parentElement?.innerText.replace(/\s+/g, ' ').slice(0, 40))),
  }
  R.settle_dots07 = await settle(p2)
  R.dots07 = await dots(p2)
  await shot(p2, path.join(out, '07-after-restart.png'))

  // 7 second window: row menu -> New window
  const before = l.app.windows().length
  await p2.locator('[aria-label="Session actions"]').first().click({ force: true })
  await p2.getByText('New window', { exact: true }).first().click().catch(() => undefined)
  await p2.waitForTimeout(8000)
  const wins = l.app.windows()
  R.secondWindow = { before, after: wins.length }
  if (wins.length > before) {
    const w2 = wins[wins.length - 1]
    await w2.waitForTimeout(6000)
    R.secondWindow.ls = await w2.evaluate(k => localStorage.getItem(k), KEY).catch(e => String(e))
    R.secondWindow.url = w2.url()
    await shot(w2, path.join(out, '08-second-window.png')).catch(() => undefined)
    // live sync? write in window 1, read in window 2 via storage event / current value
    await p2.evaluate(([id]) => (window as any).__cfSpike.setColor(id, '#12ab34'), [B])
    await w2.waitForTimeout(2000)
    R.secondWindow.lsAfterWindow1Write = await w2.evaluate(k => localStorage.getItem(k), KEY).catch(e => String(e))
    R.secondWindow.paintInW2 = await paint(w2, '#12ab34').then(x => x.hits.length).catch(() => 'n/a')
  }

  // 8 does the backend know? grep the sandbox's hermes-home for the colour values
  try {
    R.backendGrep = execSync(`grep -rIl -e '${PLUGIN_HEX.slice(1)}' -e sessionColors ${JSON.stringify(sandbox.hermesHome)} 2>/dev/null | head; true`, { encoding: 'utf8' }).trim() || '(no file under HERMES_HOME mentions the colour or key)'
    R.userDataGrep = execSync(`grep -rIla -e sessionColors ${JSON.stringify(sandbox.userDataDir)} 2>/dev/null | sed "s#${sandbox.userDataDir}##" | head; true`, { encoding: 'utf8' }).trim()
  } catch (e) { R.backendGrep = String(e) }
} catch (e) {
  R.error = String((e as Error)?.stack ?? e)
  await shot(l.page, path.join(out, 'zz-failure.png')).catch(() => undefined)
} finally {
  fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(R, null, 2))
  console.log(JSON.stringify(R, null, 2))
  await l.close()
  fs.rmSync(sandbox.root, { recursive: true, force: true })
}
process.exit(R.error ? 1 : 0)
