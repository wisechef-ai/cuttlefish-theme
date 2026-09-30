/**
 * Spike 08 — ctx.rest / ctx.socket against a local spawned backend and a remote
 * (URL+token) backend.   tools/spikes/run-desktop.sh 08-ctx-rest-local-remote [--runtime installed|upstream] [--out DIR]
 *
 * cases:
 *  local-degraded : plugin installed, plugins.enabled NOT set  → ctx.rest error shape (P4 degraded path)
 *  local          : plugins.enabled has cf-spike               → restGet body.hermes_home == sandbox home
 *  remote         : second throwaway home + `hermes serve` on another port, app pointed at it via
 *                   HERMES_DESKTOP_REMOTE_URL/TOKEN            → body.marker == 'remote'
 *  remote-nolocal : plugin exists ONLY on the remote           → is a desktop half loaded at all?
 */
import { spawn, type ChildProcess } from 'node:child_process'
import * as fs from 'node:fs'
import * as net from 'node:net'
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import {
  createSandbox, installUnifiedPackage, launchDesktop, resolveBackendPython, resolveCheckout, checkoutSha,
  shot, waitForShell, writeConfig, type Sandbox,
} from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute, listSwitches } from '../../desktop_ui.ts'

const FIXTURE = path.resolve(import.meta.dirname, '..', 'fixtures', 'cf-spike')
const ENABLE = 'plugins:\n  enabled:\n    - cf-spike\n'
const { values } = parseArgs({
  options: {
    runtime: { type: 'string', default: 'installed' },
    out: { type: 'string', default: path.join(process.env.TMPDIR || '/tmp', 'cf-spike08') },
    only: { type: 'string', default: '' },
  },
})
const out = path.resolve(values.out!, values.runtime!.replace(/[^\w-]/g, '_'))
fs.mkdirSync(out, { recursive: true })
const checkout = resolveCheckout(values.runtime)
const result: Record<string, any> = { runtime: values.runtime, sha: checkoutSha(checkout), checkout, cases: {} }

const freePort = () =>
  new Promise<number>(res => {
    const s = net.createServer()
    s.listen(0, '127.0.0.1', () => { const p = (s.address() as net.AddressInfo).port; s.close(() => res(p)) })
  })

async function startRemote(): Promise<{ proc: ChildProcess; url: string; token: string; sandbox: Sandbox; log: string }> {
  const sandbox = createSandbox('cf-s08r')
  installUnifiedPackage(sandbox, FIXTURE, 'cf-spike')
  writeConfig(sandbox, { extraConfig: ENABLE })
  const port = await freePort()
  const token = 'cf-spike-remote-token-' + Math.random().toString(36).slice(2)
  const log = path.join(out, 'remote-backend.log')
  const ws = fs.createWriteStream(log)
  const env: Record<string, string> = {}
  for (const [k, v] of Object.entries(process.env)) if (v && !k.startsWith('HERMES_') && !/(_API_KEY|_TOKEN|_SECRET)$/.test(k)) env[k] = v
  Object.assign(env, {
    HOME: sandbox.root, HERMES_HOME: sandbox.hermesHome, HERMES_DISABLE_LAZY_INSTALLS: '1',
    HERMES_DASHBOARD_SESSION_TOKEN: token, CF_SPIKE_BACKEND_MARKER: 'remote',
  })
  const proc = spawn(resolveBackendPython(checkout), ['-m', 'hermes_cli.main', 'serve', '--host', '127.0.0.1', '--port', String(port)], { cwd: checkout, env })
  proc.stdout.pipe(ws); proc.stderr.pipe(ws)
  const url = `http://127.0.0.1:${port}`
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch(`${url}/api/plugins/cf-spike/ping`, { headers: { Authorization: `Bearer ${token}` } })
      if (r.ok) { return { proc, url, token, sandbox, log } }
    } catch {}
    await new Promise(r => setTimeout(r, 1000))
  }
  proc.kill()
  throw new Error('remote backend never answered /ping; see ' + log)
}

const median = (a: number[]) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)]

async function probe(page: any, tag: string) {
  const r: Record<string, any> = {}
  r.hasSpike = await page.evaluate(() => Boolean((window as any).__cfSpike?.restGet))
  if (!r.hasSpike) return r
  r.first = await page.evaluate(() => (window as any).__cfSpike.restGet('/ping'))
  r.nope = await page.evaluate(() => (window as any).__cfSpike.restGet('/does-not-exist'))
  const lat = await page.evaluate(async () => {
    const ms: number[] = []
    for (let i = 0; i < 20; i++) { const x = await (window as any).__cfSpike.restGet('/ping'); if (x.ok) ms.push(x.ms) }
    return ms
  })
  r.latencyMs = { n: lat.length, median: median(lat), min: Math.min(...lat), max: Math.max(...lat) }
  r.socket = await page.evaluate(() => (window as any).__cfSpike.socketProbe('/events', 4500))
  r.socketFrames = r.socket.frames.length
  return r
}

async function runCase(name: string, opts: { local?: boolean; enableAgent?: boolean; remote?: Awaited<ReturnType<typeof startRemote>>; pluginLocal?: boolean }) {
  if (values.only && values.only !== name) return
  const c: Record<string, any> = {}
  result.cases[name] = c
  const sandbox = createSandbox('cf-s08')
  if (opts.pluginLocal !== false) installUnifiedPackage(sandbox, FIXTURE, 'cf-spike')
  c.sandbox = sandbox.hermesHome
  const env: Record<string, string> = { CF_SPIKE_BACKEND_MARKER: 'local' }
  if (opts.remote) { env.HERMES_DESKTOP_REMOTE_URL = opts.remote.url; env.HERMES_DESKTOP_REMOTE_TOKEN = opts.remote.token; c.remoteHome = opts.remote.sandbox.hermesHome }
  const t0 = Date.now()
  const l = await launchDesktop({ runtime: values.runtime, sandbox, extraConfig: opts.enableAgent ? ENABLE : '', env })
  const log = fs.createWriteStream(path.join(out, `${name}-electron.log`))
  l.app.process().stdout?.pipe(log); l.app.process().stderr?.pipe(log)
  try {
    await waitForShell(l.page)
    c.bootMs = Date.now() - t0
    await shot(l.page, path.join(out, `${name}-01-boot.png`))
    c.materialized = fs.existsSync(path.join(sandbox.hermesHome, 'desktop-plugins', 'cf-spike', 'plugin.js'))
    await gotoRoute(l.page, '/capabilities?tab=plugins')
    await l.page.waitForTimeout(2500)
    await shot(l.page, path.join(out, `${name}-02-plugins-tab.png`))
    try {
      c.enabled = await enablePluginViaSettings(l.page, 'CF Spike', 20_000)
    } catch (e) {
      c.enableError = String((e as Error).message).split('\n')[0]
      c.switches = await listSwitches(l.page)
      await shot(l.page, path.join(out, `${name}-03-enable-failed.png`))
    }
    await gotoRoute(l.page, '/')
    await l.page.waitForTimeout(2500)
    await shot(l.page, path.join(out, `${name}-04-main.png`))
    c.probe = await probe(l.page, name)
    c.chip = await l.page.evaluate(() => (document.querySelector('[data-testid="cf-spike-chip"]') as HTMLElement | null)?.innerText ?? null)
    c.connection = await l.page.evaluate(async () => {
      try { const x = await (window as any).hermesDesktop.getConnection(); return { baseUrl: x.baseUrl, authMode: x.authMode, kind: x.kind ?? null, hasToken: Boolean(x.token) } } catch (e) { return { error: String(e) } }
    })
  } catch (e) {
    c.error = String((e as Error).stack ?? e)
    await shot(l.page, path.join(out, `${name}-zz-failure.png`)).catch(() => undefined)
  } finally {
    await l.close()
    fs.rmSync(sandbox.root, { recursive: true, force: true })
  }
}

let remote: Awaited<ReturnType<typeof startRemote>> | undefined
try {
  await runCase('local-degraded', {})
  await runCase('local', { enableAgent: true })
  remote = await startRemote()
  result.remote = { url: remote.url, home: remote.sandbox.hermesHome }
  const direct = await fetch(`${remote.url}/api/plugins/cf-spike/ping`, { headers: { Authorization: `Bearer ${remote.token}` } })
  result.remoteDirectPing = await direct.json()
  const lat: number[] = []
  for (let i = 0; i < 20; i++) { const t = performance.now(); await (await fetch(`${remote.url}/api/plugins/cf-spike/ping`, { headers: { Authorization: `Bearer ${remote.token}` } })).text(); lat.push(performance.now() - t) }
  result.remoteDirectLatencyMs = { median: median(lat) }
  await runCase('remote', { remote })
  await runCase('remote-nolocal', { remote, pluginLocal: false })
} catch (e) {
  result.error = String((e as Error).stack ?? e)
} finally {
  remote?.proc.kill()
  if (remote) fs.rmSync(remote.sandbox.root, { recursive: true, force: true })
}
fs.writeFileSync(path.join(out, 'result.json'), JSON.stringify(result, null, 2))
console.log(JSON.stringify(result, (k, v) => (k === 'socket' ? undefined : v), 2))
process.exit(result.error ? 1 : 0)
