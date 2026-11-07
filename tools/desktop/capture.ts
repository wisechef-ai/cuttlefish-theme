/**
 * THE real-Desktop capture (dev only, never shipped): one re-runnable command that records the evidence tree under
 * <repo>/evidence/v2 from the SHIPPED desktop/plugin.js of the checkout it runs in.
 *
 *   node tools/desktop/capture.ts            (normally through tools/desktop/capture.sh <commit>)
 *
 * sandbox up → plugin switched ON through the real Capabilities ▸ Plugins switch → scripted scenario through the mock model and
 * core's real paths (8 sessions: 4 resting, working, needs you, error, finished unseen) → DOM dumps + screen stills while
 * each session is focused → CPU windows with the plugin toggled for real (on, off, on) → manifest → sandbox down.
 * Nothing is poked into the plugin: every number is read from the DOM or the screen.
 */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import * as fs from 'node:fs'
import * as net from 'node:net'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { buildManifest, uncovered, type CpuWindowSpec, type SessionSpec, type StillSpec } from './manifest.ts'
import { clipRects, cpuPct, csvOf, listRawFiles, parseStatTicks, roleOf, sha256Hex, unionCoverage, type Rect, type Role } from './evidence_lib.ts'
import { createSandbox, launchDesktop, listenNow, send, startXvfb, waitForShell, type Launched } from './harness.ts'
import * as P from './pagecode.ts'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const REPO = path.resolve(HERE, '..', '..')
const OUT = path.join(REPO, 'evidence', 'v2')
const STAGE = `${OUT}.staging`
const RAW = path.join(STAGE, 'raw')
const DISPLAY = process.env.CF_DISPLAY ?? ':93'
const MOCK_PORT = Number(process.env.CF_MOCK_PORT ?? 18931)
const SCREEN = { w: 1600, h: 1000 }
const WINDOW_S = 62 // each CPU window samples a little over the 60 s the budget names
const SETTLE_PERF_S = 20 // after a toggle or a focus change, before a CPU window opens
const SETTLE_S = 8 // a state change blooms for a few seconds; stills are taken after it settled (C7)
const T0 = Date.now()
const log = (m: string) => console.log(`[${((Date.now() - T0) / 1000).toFixed(1).padStart(6)}s] ${m}`)
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
const now = () => Date.now() / 1000

function w(rel: string, data: string | Buffer): void {
  const p = path.join(RAW, rel)
  fs.mkdirSync(path.dirname(p), { recursive: true })
  fs.writeFileSync(p, data)
}
const wj = (rel: string, v: unknown) => w(rel, JSON.stringify(v, null, 2) + '\n')

// ---- processes we start (and stop: only these PIDs) ------------------------------------------------------------------
const portFree = (p: number) => new Promise<boolean>(res => {
  const s = net.createServer().once('error', () => res(false)).once('listening', () => s.close(() => res(true)))
  s.listen(p, '127.0.0.1')
})

function grab(file: string): void {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'x11grab', '-draw_mouse', '0', '-video_size', `${SCREEN.w}x${SCREEN.h}`, '-i', DISPLAY, '-frames:v', '1', '-pix_fmt', 'rgb24', file])
}

function startVideo(file: string): ChildProcess {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  return spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'x11grab', '-draw_mouse', '0', '-framerate', '10', '-video_size', `${SCREEN.w}x${SCREEN.h}`, '-i', DISPLAY,
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '32', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', file], { stdio: ['pipe', 'ignore', 'inherit'] })
}
async function stopVideo(p: ChildProcess): Promise<void> {
  const done = new Promise<void>(res => p.once('exit', () => res()))
  p.stdin?.write('q')
  await Promise.race([done, sleep(20_000)])
  if (p.exitCode === null) p.kill('SIGINT')
}

// ---- CPU sampling (renderer + GPU process of OUR app tree) ------------------------------------------------------------
function descendantsOf(root: number): number[] {
  const kids = new Map<number, number[]>()
  for (const d of fs.readdirSync('/proc')) {
    if (!/^\d+$/.test(d)) continue
    try {
      const ppid = Number(fs.readFileSync(`/proc/${d}/stat`, 'utf8').replace(/^.*\) \S+ /, '').split(' ')[0])
      kids.set(ppid, [...(kids.get(ppid) ?? []), Number(d)])
    } catch { /* vanished */ }
  }
  const out = [root]
  for (let i = 0; i < out.length; i++) out.push(...(kids.get(out[i]) ?? []))
  return out
}
function sampledPids(appPid: number): Map<number, Role> {
  const m = new Map<number, Role>()
  for (const pid of descendantsOf(appPid)) {
    try {
      const role = roleOf(fs.readFileSync(`/proc/${pid}/cmdline`, 'utf8').replace(/\0/g, ' '), pid === appPid)
      if (role === 'renderer' || role === 'gpu') m.set(pid, role)
    } catch { /* vanished */ }
  }
  return m
}
const ticksOf = (pid: number) => parseStatTicks(fs.readFileSync(`/proc/${pid}/stat`, 'utf8'))

interface CpuRun { rows: (string | number)[][]; roles: Record<string, string>; first: number; last: number }
/** 1 Hz samples of every sampled pid for `seconds`; `during` runs concurrently (dumps, stills, the css sampler). */
async function cpuWindow(appPid: number, seconds: number, during: () => Promise<void>): Promise<CpuRun> {
  const pids = sampledPids(appPid)
  if (pids.size < 2) throw new Error(`only ${pids.size} renderer/gpu pid(s) in the app tree: ${[...pids.entries()]}`)
  const prev = new Map<number, number>()
  for (const pid of pids.keys()) prev.set(pid, ticksOf(pid) ?? 0)
  let last = now()
  const rows: (string | number)[][] = []
  const work = during()
  const first = last
  for (let i = 0; i < seconds; i++) {
    await sleep(Math.max(0, 1000 - (now() - last) * 1000)) // 1 s after the previous sample
    const t = now()
    for (const pid of pids.keys()) {
      const cur = ticksOf(pid)
      if (cur === null) throw new Error(`pid ${pid} vanished during a CPU window`)
      rows.push([pid, t.toFixed(3), cpuPct(prev.get(pid)!, cur, t - last).toFixed(3)])
      prev.set(pid, cur)
    }
    last = t
  }
  await work
  return { rows, roles: Object.fromEntries([...pids].map(([pid, r]) => [String(pid), r])), first, last }
}

// ---- the scenario's helpers --------------------------------------------------------------------------------------------
async function dismissBanner(page: Page): Promise<void> {
  await page.getByText('No thanks').click({ timeout: 4000 }).catch(() => undefined)
}

async function openPluginCard(page: Page): Promise<void> {
  await page.getByText('Capabilities').first().click()
  await page.getByText('Plugins', { exact: true }).first().click()
  await page.getByPlaceholder('Search plugins').fill('cuttle')
  await page.locator('[role="switch"][aria-label="Cuttlefish"]').waitFor({ timeout: 20_000 })
}

/** Flip the plugin through the real Capabilities ▸ Plugins switch; returns once the switch reads the wanted state. */
async function setPlugin(page: Page, on: boolean): Promise<void> {
  await openPluginCard(page)
  const want = on ? 'true' : 'false'
  if ((await page.evaluate(P.switchState)) !== want) await page.locator('[role="switch"][aria-label="Cuttlefish"]').click()
  for (let i = 0; i < 40 && (await page.evaluate(P.switchState)) !== want; i++) await sleep(250)
  if ((await page.evaluate(P.switchState)) !== want) throw new Error(`the plugin switch did not reach ${want}`)
  await sleep(3000)
}

const rowLocator = (page: Page, title: string) => page.locator('[data-sessions-mode] [data-slot="context-menu-trigger"]', { hasText: title }).first()
/** Focus a session row. Never straight from a busy session: the plugin pairs the focused RUNTIME id with the focused STORED id
 *  from two atoms that move one after the other, so a direct switch maps the session being left onto the one being entered
 *  (reported as a product finding). Going through an empty new chat first leaves the pairs intact. */
async function focusRow(page: Page, title: string): Promise<void> {
  await page.keyboard.press('Control+n')
  await sleep(900)
  await rowLocator(page, title).click()
  await page.mouse.move(SCREEN.w - 5, SCREEN.h / 2) // park the pointer: no hover tooltip in a still
  await sleep(500)
}
async function newSession(page: Page, firstMessage: string): Promise<void> {
  await page.keyboard.press('Control+n')
  await sleep(1200)
  await send(page, firstMessage)
}
async function storedIdOf(page: Page, title: string): Promise<string> {
  for (let i = 0; i < 40; i++) {
    const rows = await page.evaluate(P.readRows)
    const r = rows.find(x => x.title === title && x['data-cf-session'])
    if (r) return r['data-cf-session']!
    await sleep(500)
  }
  throw new Error(`no sidebar row with a swatch titled ${title}`)
}

// ---- the dumps and the stills ------------------------------------------------------------------------------------------
const PLUGIN_SHA = sha256Hex(fs.readFileSync(path.join(REPO, 'desktop', 'plugin.js')))

interface Dump { schema: string; stored_id: string; state: string; focused: boolean; plugin_js_sha256: string; captured_at: number; html: Record<string, string>; row: P.RowInfo | Record<string, unknown>; rows: P.RowInfo[]; strip: { text: string }; composer: { rim: unknown; ring_vars: Record<string, string> }; transcript_messages: number }

async function domDump(page: Page, title: string, stored: string, state: string, focused: boolean, st: Taken | null, geo: P.Geometry): Promise<Dump> {
  const rows = await page.evaluate(P.readRows)
  const row = rows.find(r => r['data-cf-session'] === stored)
  if (!row) throw new Error(`session ${title} (${stored}) has no sidebar row`)
  const chrome = await page.evaluate(P.readChrome)
  // transcript messages no exclusion rectangle covers: what the measured pixels would still show (L6). Not focused: nothing is measured.
  const shown = focused && st ? uncovered(geo.messages, st.exclude, st.region) : 0
  return {
    schema: 'cf2-dom-dump/1', stored_id: stored, state, focused, plugin_js_sha256: PLUGIN_SHA, captured_at: now(),
    html: await page.evaluate(P.readHtmlAttrs),
    row: { 'data-cf-session': row['data-cf-session'], 'data-cf-state': row['data-cf-state'], swatch_circles: row.swatch_circles },
    rows: rows.map(r => ({ title: r.title, 'data-cf-session': r['data-cf-session'], 'data-cf-state': r['data-cf-state'], swatch_circles: r.swatch_circles })),
    strip: { text: chrome.strip },
    composer: { rim: chrome.rim ?? { 'data-cf-state': '', svg_sha256: '0'.repeat(64) }, ring_vars: { '--dt-composer-ring': chrome.ring } },
    transcript_messages: shown,
  }
}

interface Taken { state: string; rel: string; png: string; meta: string; region: Rect; exclude: Rect[]; at: number; geo: P.Geometry }
/** A screen still of the focused session + its sidecar. The PNG comes from the REAL screen (x11grab), not from the page. */
async function still(page: Page, state: string, key = state): Promise<Taken> {
  const geo = await page.evaluate(P.readGeometry)
  if (geo.surface === null) throw new Error('no chat surface on screen')
  if (geo.offset[0] !== 0 || geo.offset[1] !== 0) throw new Error(`the window is offset ${geo.offset} on the screen: client pixels are not screen pixels`)
  // the region is the chat surface above the composer (the composer is excluded by leaving it out of the region, ≥ 50% of the still stays)
  const [sx, sy, sw, sh] = geo.surface as Rect
  const region: Rect = [sx, sy, sw, Math.min(sh, Math.max(1, (geo.composerTop ?? sy + sh) - 4 - sy))]
  const png = `stills/${key}.png`
  const at = now()
  grab(path.join(RAW, png))
  const exclude = clipRects(geo.boxes, region, 3)
  if (unionCoverage(exclude) > 0.25 * region[2] * region[3]) throw new Error(`${key}: exclusions cover more than 25% of the region: ${JSON.stringify(geo.boxes)} -> ${JSON.stringify(exclude)}`)
  const meta = `stills/${key}.json`
  wj(meta, { schema: 'cf2-still/1', state, png_sha256: sha256Hex(fs.readFileSync(path.join(RAW, png))), taken_at: at, region, exclude })
  return { state, rel: png, png: `evidence/v2/raw/${png}`, meta, region, exclude, at, geo }
}

/** EXTRA ground (best effort, report only): Desktop colour mode → dark through the command palette, the plugin re-attached so it samples
 *  the new ground, one still per field state. A failure is recorded in the log; it never fails the capture. */
async function darkGround(page: Page, ids: Record<string, string>): Promise<void> {
  try {
    await page.keyboard.press('Control+k'); await sleep(800)
    await page.keyboard.type('dark'); await sleep(800)
    await page.keyboard.press('Enter'); await sleep(2000)
    const mode = await page.evaluate(() => document.documentElement.getAttribute('data-hermes-mode'))
    if (mode !== 'dark') throw new Error(`colour mode is ${mode}`)
    await setPlugin(page, false); await setPlugin(page, true)
    for (const [key, state] of [['r4', 'resting'], ['b', 'needs_you'], ['c', 'error'], ['a', 'working']]) {
      await focusRow(page, TITLES[key as keyof typeof TITLES]); await sleep(SETTLE_S * 1000)
      await still(page, state, `dark.${state}`)
    }
    log('dark ground captured')
  } catch (e) { log(`dark ground skipped: ${String(e).slice(0, 200)}`) }
  void ids
}

// ---- main --------------------------------------------------------------------------------------------------------------
const TITLES = { r1: 'calm sea [done]', r2: 'mottle study [done]', a: 'long task [work]', b: 'risky command [approve]', c: 'broken request [fail]',
  r3: 'quiet note [done]', d: 'slow answer [brief]', r4: 'last calm [done]' }

function installPackage(home: string): void {
  const target = path.join(home, 'plugins', 'cuttlefish-theme')
  fs.mkdirSync(path.dirname(target), { recursive: true })
  const skip = /(^|\/)(\.git|\.venv|node_modules|__pycache__|evidence|tests|tools|contract|docs|reviews)(\/|$)|^desktop\/(src|test)(\/|$)/
  fs.cpSync(REPO, target, { recursive: true, force: true, filter: src => !skip.test(path.relative(REPO, src)) })
  const shipped = sha256Hex(fs.readFileSync(path.join(target, 'desktop', 'plugin.js')))
  if (shipped !== PLUGIN_SHA) throw new Error('the installed plugin.js differs from the checkout')
}

async function main(): Promise<void> {
  fs.rmSync(STAGE, { recursive: true, force: true })
  fs.mkdirSync(RAW, { recursive: true })
  const commit = execFileSync('git', ['-C', REPO, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  const started: ChildProcess[] = []
  let launched: Launched | undefined
  let video: ChildProcess | undefined
  try {
    const xvfb = await startXvfb(DISPLAY, `${SCREEN.w}x${SCREEN.h}x24`); started.push(xvfb.proc)
    if (!(await portFree(MOCK_PORT))) throw new Error(`mock port ${MOCK_PORT} busy`)
    const mock = spawn(process.env.CF_MOCK_PYTHON ?? 'python3', [path.join(HERE, 'mock_llm.py'), String(MOCK_PORT)], {
      stdio: 'ignore', env: { ...process.env, CF_MOCK_WORK_S: '7200', CF_MOCK_BRIEF_S: '6' } })
    started.push(mock); await sleep(800)

    const sandbox = createSandbox('evidence')
    installPackage(sandbox.hermesHome)
    launched = await launchDesktop({ sandbox, display: xvfb.display, width: SCREEN.w, height: SCREEN.h, modelBaseUrl: `http://127.0.0.1:${MOCK_PORT}/v1`,
      extraConfig: 'plugins:\n  enabled:\n    - cuttlefish-theme\n' })
    const page = launched.page
    const appPid = launched.app.process().pid!
    log(`booted in ${await waitForShell(page)} ms`)
    await dismissBanner(page)

    // ISOLATION: asserted in code (recordIsolation throws), recorded for the manifest
    const iso = launched.isolation()
    const conn = JSON.stringify(await page.evaluate(() => (window as unknown as { hermesDesktop: { getConnection: () => Promise<unknown> } }).hermesDesktop.getConnection()))
    const gw = [...conn.matchAll(/:(\d{4,5})\b/g)].map(m => Number(m[1])).filter(p => iso.gateway_ports.includes(p))
    const gatewayPort = gw[0] ?? iso.gateway_ports[0]
    const live = launched.liveAtLaunch // the snapshot taken BEFORE the app started (afterwards our own gateway would be in it)
    if (iso.gateway_ports.some(p => live.some(l => l.port === p))) throw new Error('isolation: a sandbox port collides with a live Hermes port')
    log(`isolation ok: gateway ${gatewayPort}, sandbox ports ${iso.gateway_ports}, live ${live.map(l => l.port)}`)

    // 1. VIDEO of the scenario; the plugin is switched ON through the real switch
    const videoPath = path.join(STAGE, 'capture.mp4')
    video = startVideo(videoPath)
    const videoStart = now()
    await sleep(1500)
    await setPlugin(page, true)
    await page.getByText('New session').first().click()
    await sleep(1000)

    // 2. the scenario: 8 sessions through the real send path
    const ids: Record<string, string> = {}
    await send(page, TITLES.r1); ids.r1 = await storedIdOf(page, TITLES.r1); await sleep(3000)
    await newSession(page, TITLES.r2); ids.r2 = await storedIdOf(page, TITLES.r2); await sleep(3000)
    await newSession(page, TITLES.a); ids.a = await storedIdOf(page, TITLES.a); await sleep(3000)
    await newSession(page, TITLES.b); ids.b = await storedIdOf(page, TITLES.b); await sleep(6000)
    await newSession(page, TITLES.c); ids.c = await storedIdOf(page, TITLES.c); await sleep(6000)
    await newSession(page, TITLES.r3); ids.r3 = await storedIdOf(page, TITLES.r3); await sleep(3000)
    await newSession(page, TITLES.d); ids.d = await storedIdOf(page, TITLES.d)
    await newSession(page, TITLES.r4); ids.r4 = await storedIdOf(page, TITLES.r4) // another session takes the focus before D's 6 s turn ends: D finishes UNSEEN
    await sleep(10_000)
    log(`sessions: ${JSON.stringify(ids)}`)

    const sessions: SessionSpec[] = []
    const stills: StillSpec[] = []
    const timeline: { session: string; state: string; start_s: number; end_s: number }[] = []
    const take = async (key: string, state: string, focused: boolean, measure: boolean): Promise<void> => {
      const title = TITLES[key as keyof typeof TITLES]
      const t0 = now()
      if (focused) {
        await focusRow(page, title)
        // a state change blooms for a few seconds (C7): one extra, unmeasured-by-the-contract still while it blooms, then the settled one
        if (measure && state !== 'resting') { await sleep(1500); await still(page, state, `${state}.bloom`); await sleep((SETTLE_S - 1.5) * 1000) } else await sleep(SETTLE_S * 1000)
      }
      const geo = await page.evaluate(P.readGeometry)
      const st = measure ? await still(page, state) : null
      const dump = await domDump(page, title, ids[key], state, focused, st, geo)
      const rel = `dom/${ids[key]}.${state}.json`
      wj(rel, dump)
      sessions.push({ stored_id: ids[key], expected: state, dom_state: (dump.row as { 'data-cf-state': string })['data-cf-state'], dom_dump: rel, title })
      if (st) stills.push({ state, path: st.png, sha256: sha256Hex(fs.readFileSync(path.join(RAW, st.rel))), meta: st.meta, dom_dump: rel })
      timeline.push({ session: ids[key], state, start_s: t0 - videoStart, end_s: now() - videoStart })
      log(`${title}: ${state} dom=${(dump.row as { 'data-cf-state': string })['data-cf-state']} strip="${dump.strip.text}"`)
    }
    // D first, while it is still unseen and unfocused (focusing it would clear the state)
    await take('d', 'finished_unseen', false, false)
    await take('r4', 'resting', true, true)
    for (const k of ['r1', 'r2', 'r3']) await take(k, 'resting', true, false)
    await take('b', 'needs_you', true, true)
    await take('c', 'error', true, true)
    await take('a', 'working', true, true)
    await focusRow(page, TITLES.r4); await sleep(SETTLE_S * 1000)
    grab(path.join(RAW, 'stills/overview.png'))
    stills.push({ state: 'overview', path: 'evidence/v2/raw/stills/overview.png', sha256: sha256Hex(fs.readFileSync(path.join(RAW, 'stills/overview.png'))) })
    await stopVideo(video); video = undefined

    // 3. PERF: 8 sessions, 60 s windows, the plugin toggled for real. Focus r4 (resting) for idle, a (working) for working.
    const rows8 = (await page.evaluate(P.readRows)).length
    if (rows8 !== 8) throw new Error(`${rows8} sidebar rows, the perf run needs 8`)
    const windows: Record<string, CpuWindowSpec> = {}
    const order: string[] = []
    const winDump = async (name: string, plugin: 'on' | 'off') => {
      wj(`dom/win.${name}.json`, { schema: 'cf2-window-dump/1', window: name, plugin, captured_at: now(), html: await page.evaluate(P.readHtmlAttrs),
        rows: (await page.evaluate(P.readRows)).map(r => ({ 'data-cf-session': r['data-cf-session'], 'data-cf-state': r['data-cf-state'], swatch_circles: r.swatch_circles })) })
    }
    const runWindow = async (name: string, plugin: 'on' | 'off', during: () => Promise<void>) => {
      const run = await cpuWindow(appPid, WINDOW_S, async () => { await sleep(5000); await winDump(name, plugin); await during() })
      const rel = `cpu/${name.replace('_', '.')}.csv`
      w(rel, csvOf(['pid', 'ts', 'cpu_pct'], run.rows))
      windows[name] = { file: rel, dom_dump: `dom/win.${name}.json`, roles: run.roles }
      order.push(name)
      log(`window ${name}: ${run.rows.length} rows, roles ${JSON.stringify(run.roles)}`)
    }
    const pollCss = async (rel: string | null, seconds: number) => {
      const rows: (string | number)[][] = []
      const end = now() + seconds
      while (now() < end) { const t = now(); rows.push([t.toFixed(3), await page.evaluate(P.cssHash)]); await sleep(Math.max(0, 100 - (now() - t) * 1000)) }
      if (rel) w(rel, csvOf(['ts', 'css_sha256'], rows))
    }

    // Every window must carry the same toggle history: the FIRST switch-off of the plugin leaves the Desktop ~1.5 pp busier for good
    // (measured separately: ON-without-toggle 1.2-1.5 pp, OFF 3.0, ON again 3.0-4.2), so the plugin goes off and on once BEFORE
    // the first window, and every window below follows a toggle and a 20 s settle.
    await setPlugin(page, false); await setPlugin(page, true)
    await focusRow(page, TITLES.r4); await sleep(SETTLE_PERF_S * 1000)
    let idleStill: Taken | undefined
    await runWindow('idle_on', 'on', async () => {
      await sleep(15_000)
      idleStill = await still(page, 'resting-idle')
      const d = await domDump(page, TITLES.r4, ids.r4, 'resting', true, idleStill, idleStill.geo)
      wj('dom/idle-window.json', d)
      stills.push({ state: 'resting-idle', path: idleStill.png, sha256: sha256Hex(fs.readFileSync(path.join(RAW, idleStill.rel))), meta: idleStill.meta, dom_dump: 'dom/idle-window.json' })
    })
    await setPlugin(page, false); await focusRow(page, TITLES.r4); await sleep(SETTLE_PERF_S * 1000)
    await runWindow('idle_off', 'off', async () => undefined)
    await focusRow(page, TITLES.a); await sleep(SETTLE_PERF_S * 1000)
    await runWindow('working_off', 'off', () => pollCss(null, 40))
    await setPlugin(page, true); await focusRow(page, TITLES.a); await sleep(SETTLE_PERF_S * 1000)
    await runWindow('working_on', 'on', () => pollCss('cpu/working.field.csv', 40))
    await darkGround(page, ids)
    const order4 = ['idle_on', 'idle_off', 'working_off', 'working_on']

    // 4. manifest (numbers come from the contract's own instruments: measure.py recomputes everything from the raw files)
    const measured = JSON.parse(execFileSync(process.env.CF_PYTHON ?? 'python3', [path.join(HERE, 'measure.py'), STAGE], { encoding: 'utf8', maxBuffer: 1 << 26 }))
    const manifest = buildManifest({
      commit, pluginSha: PLUGIN_SHA, core: { version: 'v0.22.7', sha: launched.sha, desktop_build: 'source' },
      isolation: { hermes_home: iso.hermes_home, user_data_dir: iso.electron_user_data, gateway_port: gatewayPort, live_gateway_ports: live.map(l => l.port),
        display: iso.display, isolated_backend: iso.isolated_backend, sandbox_ports: iso.gateway_ports, ss_snapshot: listenNow() },
      video: { path: 'evidence/v2/capture.mp4', sha256: sha256Hex(fs.readFileSync(videoPath)), start_epoch: videoStart }, sessions, stills, windows, order: order4,
      rows: (await page.evaluate(P.readRows)).length, timeline, measured, files: listRawFiles(RAW), capturedAt: new Date().toISOString(),
    })
    fs.writeFileSync(path.join(STAGE, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
    log('manifest written')
  } finally {
    if (video) await stopVideo(video).catch(() => undefined)
    if (launched) await launched.close()
    for (const p of started.reverse()) p.kill()
  }
  // run-twice / crash-halfway safe: the old tree is replaced only once the new one is complete
  fs.rmSync(OUT, { recursive: true, force: true })
  fs.renameSync(STAGE, OUT)
  log(`evidence at ${OUT}`)
}

await main()
