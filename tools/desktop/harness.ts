/**
 * Real-Desktop harness (dev only, never shipped). Boots the v0.22.7 `apps/desktop` SOURCE BUILD against a throwaway
 * home, on a private X display, with a local mock model. Ported from v22 tools/desktop_harness.ts (sound, reused) with
 * three changes: durable sandboxes under /home/adam/repos/hackathon/sandboxes (the scratch pruner eats ~/.hermes/cache),
 * the default model is tools/desktop/mock_llm.py, and every launch records its isolation facts for the evidence.
 *
 *   HOME → <sandbox>   HERMES_HOME → <sandbox>/hermes-home   userData → <sandbox>/electron-user-data
 *   HERMES_DESKTOP_ISOLATED_BACKEND=1, HERMES_DESKTOP_IGNORE_EXISTING=1   (upstream e2e fixtures.ts recipe)
 */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron, type ElectronApplication, type Page } from '@playwright/test'

const HOME = os.homedir()
export const CHECKOUT = process.env.CF_HERMES_CORE ?? path.join(HOME, 'repos/hackathon/hermes-core')
export const SANDBOXES = process.env.CF_SANDBOXES ?? path.join(HOME, 'repos/hackathon/sandboxes')
export const BACKEND_PYTHON = process.env.CF_HERMES_PYTHON ?? path.join(HOME, '.hermes/hermes-agent/venv/bin/python')
const LIVE_HOME = path.join(HOME, '.hermes')
const LIVE_CONFIG = path.join(HOME, '.config')

export interface Sandbox { root: string; hermesHome: string; userDataDir: string }
export interface LaunchOptions {
  sandbox?: Sandbox; display?: string; width?: number; height?: number
  modelBaseUrl?: string; extraConfig?: string; env?: Record<string, string>
}
export interface Launched {
  app: ElectronApplication; page: Page; sandbox: Sandbox; sha: string; display: string; liveAtLaunch: ListenPort[]; isolation: () => IsolationFacts; close: () => Promise<void>
}

export function createSandbox(prefix = 'cf'): Sandbox {
  fs.mkdirSync(SANDBOXES, { recursive: true })
  const root = fs.mkdtempSync(path.join(SANDBOXES, `${prefix}-`))
  const sb = { root, hermesHome: path.join(root, 'hermes-home'), userDataDir: path.join(root, 'electron-user-data') }
  fs.mkdirSync(sb.hermesHome, { recursive: true })
  fs.mkdirSync(sb.userDataDir, { recursive: true })
  assertOutsideLive(sb)
  return sb
}

/** Isolation guard: nothing of the sandbox may live under the live ~/.hermes or ~/.config. */
export function assertOutsideLive(sb: Sandbox): void {
  for (const p of [sb.root, sb.hermesHome, sb.userDataDir]) {
    const r = path.resolve(p)
    for (const live of [LIVE_HOME, LIVE_CONFIG]) {
      if (r === live || r.startsWith(live + path.sep)) throw new Error(`sandbox path ${r} is inside live ${live}`)
    }
  }
}

const DISPLAY_RE = /^:(9\d)$/
/** Start a private Xvfb on a :9x display. Refuses :0/:1 and any display already taken (lock file or socket). */
export async function startXvfb(display = ':93', size = '1600x1000x24'): Promise<{ display: string; proc: ChildProcess }> {
  if (!DISPLAY_RE.test(display)) throw new Error(`refusing display ${display}: private displays are :90-:99`)
  const n = display.slice(1)
  if (fs.existsSync(`/tmp/.X${n}-lock`) || fs.existsSync(`/tmp/.X11-unix/X${n}`)) throw new Error(`display ${display} already in use`)
  const proc = spawn('Xvfb', [display, '-screen', '0', size, '-nolisten', 'tcp'], { stdio: 'ignore' })
  for (let i = 0; i < 50 && !fs.existsSync(`/tmp/.X11-unix/X${n}`); i++) await new Promise(r => setTimeout(r, 100))
  if (!fs.existsSync(`/tmp/.X11-unix/X${n}`)) { proc.kill(); throw new Error(`Xvfb ${display} did not come up`) }
  return { display, proc }
}

export interface ListenPort { port: number; pid: number | null; proc: string }
/** Parse `ss -ltnp` into LISTEN rows (127.0.0.1/0.0.0.0/[::] alike). */
export function parseListen(text: string): ListenPort[] {
  const rows: ListenPort[] = []
  for (const line of text.split('\n')) {
    const m = line.match(/^LISTEN\s+\d+\s+\d+\s+(\S+):(\d+)\s+\S+\s*(.*)$/)
    if (!m) continue
    const u = m[3].match(/\("([^"]+)",pid=(\d+)/)
    rows.push({ port: Number(m[2]), pid: u ? Number(u[2]) : null, proc: u ? u[1] : '' })
  }
  return rows
}
export function listenNow(): ListenPort[] {
  return parseListen(execFileSync('ss', ['-ltnp'], { encoding: 'utf8' }))
}
/** Every LISTEN port held by a process whose command line is a Hermes one (the gateways we must never collide with). */
export function liveHermesPorts(rows: ListenPort[] = listenNow()): ListenPort[] {
  return rows.filter(r => {
    if (r.pid == null) return false
    try { return /hermes/i.test(fs.readFileSync(`/proc/${r.pid}/cmdline`, 'utf8').replace(/\0/g, ' ')) } catch { return false }
  })
}
function descendants(root: number): Set<number> {
  const kids = new Map<number, number[]>()
  for (const d of fs.readdirSync('/proc')) {
    if (!/^\d+$/.test(d)) continue
    try {
      const ppid = Number(fs.readFileSync(`/proc/${d}/stat`, 'utf8').replace(/^.*\) \S+ /, '').split(' ')[0])
      kids.set(ppid, [...(kids.get(ppid) ?? []), Number(d)])
    } catch { /* process vanished */ }
  }
  const out = new Set<number>([root]); const q = [root]
  while (q.length) for (const k of kids.get(q.shift()!) ?? []) if (!out.has(k)) { out.add(k); q.push(k) }
  return out
}
/** Sandbox gateway ports = LISTEN ports owned by the app's own process tree, minus the model mock. */
export function sandboxGatewayPorts(appPid: number): ListenPort[] {
  const tree = descendants(appPid)
  return listenNow().filter(r => r.pid != null && tree.has(r.pid))
}

export interface IsolationFacts {
  hermes_home: string; electron_user_data: string; sandbox_root: string
  outside_live_hermes: boolean; outside_dot_config: boolean
  display: string; display_is_private: boolean; isolated_backend: true
  gateway_ports: number[]; live_hermes_ports_at_launch: ListenPort[]; gateway_port_disjoint_from_live: boolean
  backend_python: string; core_sha: string
}
export function recordIsolation(l: Pick<Launched, 'sandbox' | 'display' | 'sha'>, liveAtLaunch: ListenPort[], gateway: ListenPort[]): IsolationFacts {
  const under = (p: string, base: string) => { const r = path.resolve(p); return r === base || r.startsWith(base + path.sep) }
  const sb = l.sandbox
  const ports = gateway.map(g => g.port)
  const disjoint = ports.every(p => !liveAtLaunch.some(x => x.port === p))
  const facts: IsolationFacts = {
    hermes_home: sb.hermesHome, electron_user_data: sb.userDataDir, sandbox_root: sb.root,
    outside_live_hermes: ![sb.root, sb.hermesHome, sb.userDataDir].some(p => under(p, LIVE_HOME)),
    outside_dot_config: ![sb.root, sb.hermesHome, sb.userDataDir].some(p => under(p, LIVE_CONFIG)),
    display: l.display, display_is_private: DISPLAY_RE.test(l.display), isolated_backend: true,
    gateway_ports: ports, live_hermes_ports_at_launch: liveAtLaunch, gateway_port_disjoint_from_live: disjoint,
    backend_python: BACKEND_PYTHON, core_sha: l.sha,
  }
  if (!facts.outside_live_hermes || !facts.outside_dot_config || !facts.display_is_private || !disjoint || ports.length === 0) {
    throw new Error(`isolation violated: ${JSON.stringify(facts)}`)
  }
  return facts
}

export function writeConfig(sb: Sandbox, modelBaseUrl: string, extraConfig = ''): void {
  const yaml = [
    '# written by cuttlefish-theme tools/desktop/harness.ts (throwaway home)',
    '_config_version: 48',
    'model:',
    '  default: cf-mock',
    '  provider: custom:cf-mock',
    `  base_url: ${modelBaseUrl}`,
    '  context_length: 65536',
    'custom_providers:',
    '  - name: cf-mock',
    `    base_url: ${modelBaseUrl}`,
    '    api_mode: chat_completions',
    '    key_env: CF_MOCK_API_KEY',
    'auxiliary:',
    '  title_generation:',
    '    enabled: false',
    extraConfig,
    '',
  ].join('\n')
  fs.writeFileSync(path.join(sb.hermesHome, 'config.yaml'), yaml)
  fs.writeFileSync(path.join(sb.hermesHome, '.env'), 'CF_MOCK_API_KEY=mock-no-key\n')
}

function pinWindow(sb: Sandbox, width: number, height: number): void {
  const w = (n: string, v: unknown) => { const f = path.join(sb.userDataDir, n); if (!fs.existsSync(f)) fs.writeFileSync(f, JSON.stringify(v)) }
  w('window-state.json', { x: 0, y: 0, width, height, isMaximized: false })
  w('zoom-state.json', { zoomLevel: 0 })
}

const CREDENTIAL_SUFFIXES = ['_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD', '_CREDENTIALS', '_ACCESS_KEY', '_PRIVATE_KEY']
function cleanEnv(): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(process.env)) {
    if (!v || CREDENTIAL_SUFFIXES.some(s => k.endsWith(s)) || /_BASE_URL$/.test(k)) continue
    if (k.startsWith('HERMES_') || k.startsWith('BUZZ_') || k === 'AI_AGENT' || k === 'TMPDIR') continue
    out[k] = v
  }
  return out
}

export function buildEnv(sb: Sandbox, display: string, extra: Record<string, string> = {}) {
  if (display === ':0' || display === ':1') throw new Error(`refusing DISPLAY=${display}: a live desktop`)
  return {
    ...cleanEnv(), DISPLAY: display, HOME: sb.root, TMPDIR: '/tmp',
    HERMES_HOME: sb.hermesHome, HERMES_DESKTOP_USER_DATA_DIR: sb.userDataDir,
    HERMES_DESKTOP_IGNORE_EXISTING: '1', HERMES_DESKTOP_ISOLATED_BACKEND: '1',
    HERMES_DESKTOP_HERMES_ROOT: CHECKOUT, HERMES_DESKTOP_APP_NAME: `CuttlefishHarness-${process.pid}-${Date.now()}`,
    HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1', HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1',
    HERMES_DESKTOP_PYTHON: BACKEND_PYTHON, HERMES_DISABLE_LAZY_INSTALLS: '1',
    ...extra,
  }
}

export async function launchDesktop(opts: LaunchOptions = {}): Promise<Launched> {
  const sandbox = opts.sandbox ?? createSandbox()
  const display = opts.display ?? process.env.CF_DISPLAY ?? ':93'
  if (!DISPLAY_RE.test(display)) throw new Error(`refusing display ${display}: private displays are :90-:99`)
  assertOutsideLive(sandbox)
  if (!fs.existsSync(path.join(sandbox.hermesHome, 'config.yaml'))) {
    writeConfig(sandbox, opts.modelBaseUrl ?? 'http://127.0.0.1:18931/v1', opts.extraConfig)
  }
  pinWindow(sandbox, opts.width ?? 1440, opts.height ?? 900)
  const liveAtLaunch = liveHermesPorts()
  const desktopDir = path.join(CHECKOUT, 'apps', 'desktop')
  const app = await _electron.launch({
    executablePath: path.join(CHECKOUT, 'node_modules', 'electron', 'dist', 'electron'),
    args: [desktopDir, '--disable-gpu', '--no-sandbox'],
    env: buildEnv(sandbox, display, opts.env), cwd: desktopDir, timeout: 180_000,
  })
  const page = await app.firstWindow({ timeout: 180_000 })
  const sha = execFileSync('git', ['-C', CHECKOUT, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
  const pid = app.process().pid!
  const base = { sandbox, display, sha }
  return {
    app, page, sandbox, sha, display, liveAtLaunch,
    isolation: () => recordIsolation(base, liveAtLaunch, sandboxGatewayPorts(pid)),
    close: async () => { await app.close().catch(() => undefined) },
  }
}

/** The composer is visible AND hit-testable (no boot overlay on top). Same predicate as upstream desktop-chat-smoke. */
export async function waitForShell(page: Page, timeoutMs = 300_000): Promise<number> {
  const t0 = Date.now()
  const composer = page.locator('[data-slot="composer-root"]')
    .locator('[contenteditable="true"]:visible, textarea:not([aria-hidden="true"]):not(.sr-only):visible').first()
  await composer.waitFor({ state: 'visible', timeout: timeoutMs })
  await composer.click({ trial: true, timeout: timeoutMs })
  await page.waitForTimeout(800)
  return Date.now() - t0
}

export async function send(page: Page, text: string): Promise<void> {
  const c = page.locator('[data-slot="composer-root"] [contenteditable="true"]:visible').first()
  await c.click()
  await c.fill(text)
  await page.keyboard.press('Enter')
}

export async function shot(page: Page, file: string): Promise<string> {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  await page.screenshot({ path: file })
  return file
}

export function installDiskPlugin(sb: Sandbox, id: string, pluginJs: string): void {
  const dir = path.join(sb.hermesHome, 'desktop-plugins', id)
  fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(path.join(dir, 'plugin.js'), pluginJs)
}

/** Copy a unified package (agent half + desktop/plugin.js) into <home>/plugins/<name> (the real install shape). */
export function installUnifiedPackage(sb: Sandbox, packageDir: string, name: string): string {
  const target = path.join(sb.hermesHome, 'plugins', name)
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.cpSync(packageDir, target, {
    recursive: true, force: true,
    filter: src => !/(^|\/)(\.git|\.venv|node_modules|__pycache__|evidence|tests|tools|contract)(\/|$)/.test(path.relative(packageDir, src)),
  })
  return target
}
