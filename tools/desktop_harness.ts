/**
 * Playwright harness for the REAL Hermes desktop build (Electron `_electron.launch`).
 *
 * One job: boot the actual `apps/desktop` build of a Hermes checkout against a
 * THROWAWAY home, so a spike or gate can drive it and look at real pixels.
 * Nothing here ever reads or writes the operator's live ~/.hermes:
 *
 *   HOME                          -> <sandbox>            (profile roots are HOME-anchored)
 *   HERMES_HOME                   -> <sandbox>/hermes-home
 *   HERMES_DESKTOP_USER_DATA_DIR  -> <sandbox>/electron-user-data
 *   HERMES_DESKTOP_ISOLATED_BACKEND=1, HERMES_DESKTOP_IGNORE_EXISTING=1
 *
 * The env recipe mirrors the upstream e2e fixtures (apps/desktop/e2e/fixtures.ts,
 * `buildAppEnv`), including stripping credentials and every inherited HERMES_*
 * runtime var (a harness launched from inside an agent otherwise leaks
 * HERMES_YOLO_MODE / HERMES_SESSION_ID into the sandboxed backend).
 *
 * Runtimes:
 *   installed -> ~/.hermes/hermes-agent            (what Adam runs; has a dist/)
 *   upstream  -> ~/.worktrees/hermes-agent/cf2909-upstream (build it first)
 *   or any checkout path via HERMES_CHECKOUT / { checkout }.
 */
import { execFileSync } from 'node:child_process'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'

import { _electron, type ElectronApplication, type Page } from '@playwright/test'

export const RUNTIMES: Record<string, string> = {
  installed: path.join(os.homedir(), '.hermes', 'hermes-agent'),
  upstream: path.join(os.homedir(), '.worktrees', 'hermes-agent', 'cf2909-upstream'),
}

/** The $0, private-safe local model lane (plan §12). No key: vLLM is open on the tailnet. */
export const QWEN38 = {
  name: 'qwen38-local',
  baseUrl: 'http://100.106.27.136:8000/v1',
  model: 'qwen3.8-27b-heretic',
}

export interface Sandbox {
  root: string
  hermesHome: string
  userDataDir: string
}

export interface LaunchOptions {
  /** 'installed' | 'upstream' | an absolute checkout path. */
  runtime?: string
  /** Reuse an existing sandbox (e.g. to relaunch against the same home). */
  sandbox?: Sandbox
  /** X display. Never ':1' (the operator's live desktop). */
  display?: string
  /** Extra config.yaml text appended verbatim (YAML). */
  extraConfig?: string
  /** Model endpoint; default QWEN38. Pass a dead URL to force provider errors. */
  modelBaseUrl?: string
  /** Extra env for the Electron process (e.g. HERMES_DESKTOP_REMOTE_URL). */
  env?: Record<string, string>
  /** Window size. */
  width?: number
  height?: number
}

export interface Launched {
  app: ElectronApplication
  page: Page
  sandbox: Sandbox
  checkout: string
  sha: string
  close: () => Promise<void>
}

export function resolveCheckout(runtime = process.env.HERMES_CHECKOUT || 'installed'): string {
  const checkout = RUNTIMES[runtime] ?? path.resolve(runtime)

  if (!fs.existsSync(path.join(checkout, 'hermes_cli', 'main.py'))) {
    throw new Error(`not a hermes-agent checkout: ${checkout}`)
  }

  const main = path.join(checkout, 'apps', 'desktop', 'dist', 'electron-main.mjs')

  if (!fs.existsSync(main)) {
    throw new Error(`desktop not built (missing ${main}); run npm ci && npm run build in apps/desktop`)
  }

  return checkout
}

export function checkoutSha(checkout: string): string {
  try {
    return execFileSync('git', ['-C', checkout, 'rev-parse', '--short=11', 'HEAD'], { encoding: 'utf8' }).trim()
  } catch {
    return 'unknown'
  }
}

export function electronBinary(checkout: string): string {
  for (const root of [path.join(checkout, 'apps', 'desktop'), checkout]) {
    const bin = path.join(root, 'node_modules', 'electron', 'dist', 'electron')

    if (fs.existsSync(bin)) {
      return bin
    }
  }

  throw new Error(`no electron binary under ${checkout} (npm ci first)`)
}

/**
 * The interpreter for the spawned backend. With HERMES_HOME redirected to a temp
 * home, a source checkout's self-update guard (hermes_cli/venv_sync.py) finds no
 * PM facts and starts a FULL dependency sync into the temp home, and the app
 * SIGTERMs the backend mid-sync ("exited before port announcement"). So: pin the
 * checkout's committed venv (resolved read-only, against the real home) and
 * disable lazy installs. Override with CF_HERMES_PYTHON.
 */
export function resolveBackendPython(checkout: string): string {
  if (process.env.CF_HERMES_PYTHON) {
    return process.env.CF_HERMES_PYTHON
  }

  const probe = (root: string): null | string => {
    const py = path.join(root, 'venv', 'bin', 'python')

    if (!fs.existsSync(py)) return null

    try {
      const env = { ...process.env }
      delete env.HERMES_HOME
      const venv = execFileSync(
        py,
        ['-c', 'from pathlib import Path; from pm.environments import selected_venv; print(selected_venv(Path(".").resolve()))'],
        { cwd: root, encoding: 'utf8', env },
      ).trim()
      const bin = path.join(venv, 'bin', 'python')

      return fs.existsSync(bin) ? bin : null
    } catch {
      return null
    }
  }

  // A checkout without its own venv (the upstream reference worktree) borrows the
  // installed runtime's environment; the receipt must say so (dependency drift).
  const found = probe(checkout) ?? probe(RUNTIMES.installed)

  if (!found) {
    throw new Error(`no Python environment for ${checkout}; set CF_HERMES_PYTHON`)
  }

  return found
}

export function createSandbox(prefix = 'cf-desk'): Sandbox {
  const base = process.env.TMPDIR || os.tmpdir()
  const root = fs.mkdtempSync(path.join(base, `${prefix}-`))
  const hermesHome = path.join(root, 'hermes-home')
  const userDataDir = path.join(root, 'electron-user-data')

  fs.mkdirSync(hermesHome, { recursive: true })
  fs.mkdirSync(userDataDir, { recursive: true })

  return { root, hermesHome, userDataDir }
}

/** Minimal config: the $0 local model, approvals prompting (so approval events fire). */
export function writeConfig(sandbox: Sandbox, opts: { modelBaseUrl?: string; extraConfig?: string } = {}): void {
  const baseUrl = opts.modelBaseUrl ?? QWEN38.baseUrl
  const configPath = path.join(sandbox.hermesHome, 'config.yaml')

  if (fs.existsSync(configPath)) {
    return // a reused sandbox keeps whatever the spike wrote
  }

  const yaml = [
    '# written by cuttlefish-theme tools/desktop_harness.ts (throwaway home)',
    'model:',
    `  default: ${QWEN38.model}`,
    `  provider: custom:${QWEN38.name}`,
    `  base_url: ${baseUrl}`,
    '  context_length: 65536',
    'custom_providers:',
    `  - name: ${QWEN38.name}`,
    `    base_url: ${baseUrl}`,
    '    api_mode: chat_completions',
    '    key_env: QWEN38_API_KEY',
    'auxiliary:',
    '  title_generation:',
    '    enabled: false',
    opts.extraConfig ?? '',
    '',
  ].join('\n')

  fs.writeFileSync(configPath, yaml, 'utf8')
  // Inert placeholder: the local vLLM needs no key, but the provider resolver wants one set.
  fs.writeFileSync(path.join(sandbox.hermesHome, '.env'), 'QWEN38_API_KEY=local-no-key\n', 'utf8')
}

function pinWindow(sandbox: Sandbox, width: number, height: number): void {
  const write = (name: string, value: unknown) => {
    const file = path.join(sandbox.userDataDir, name)

    if (!fs.existsSync(file)) {
      fs.writeFileSync(file, JSON.stringify(value, null, 2), 'utf8')
    }
  }

  write('window-state.json', { x: 0, y: 0, width, height, isMaximized: false })
  write('zoom-state.json', { zoomLevel: 0 })
}

const CREDENTIAL_SUFFIXES = ['_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD', '_CREDENTIALS', '_ACCESS_KEY', '_PRIVATE_KEY']

function cleanEnv(): Record<string, string> {
  const out: Record<string, string> = {}

  for (const [key, value] of Object.entries(process.env)) {
    if (!value) continue
    if (CREDENTIAL_SUFFIXES.some(s => key.endsWith(s))) continue
    if (/_BASE_URL$/.test(key)) continue
    if (key.startsWith('HERMES_') && !key.startsWith('HERMES_DESKTOP_') && !key.startsWith('HERMES_E2E_')) continue
    if (key.startsWith('HERMES_DESKTOP_')) continue // never inherit the operator's desktop knobs
    out[key] = value
  }

  return out
}

export function buildEnv(sandbox: Sandbox, checkout: string, display: string, extra: Record<string, string> = {}) {
  if (display === ':1' || display === ':0') {
    throw new Error(`refusing DISPLAY=${display}: that is a live desktop, use a private Xvfb`)
  }

  return {
    ...cleanEnv(),
    DISPLAY: display,
    HOME: sandbox.root,
    HERMES_HOME: sandbox.hermesHome,
    HERMES_DESKTOP_USER_DATA_DIR: sandbox.userDataDir,
    HERMES_DESKTOP_IGNORE_EXISTING: '1',
    HERMES_DESKTOP_ISOLATED_BACKEND: '1',
    HERMES_DESKTOP_HERMES_ROOT: checkout,
    HERMES_DESKTOP_APP_NAME: `CuttlefishHarness-${process.pid}-${Date.now()}`,
    HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1',
    HERMES_DESKTOP_PYTHON: resolveBackendPython(checkout),
    HERMES_DISABLE_LAZY_INSTALLS: '1',
    ...extra,
  }
}

export async function launchDesktop(opts: LaunchOptions = {}): Promise<Launched> {
  const checkout = resolveCheckout(opts.runtime)
  const sandbox = opts.sandbox ?? createSandbox()
  const display = opts.display ?? process.env.CF_DISPLAY ?? ':93'
  const width = opts.width ?? 1400
  const height = opts.height ?? 900

  writeConfig(sandbox, { modelBaseUrl: opts.modelBaseUrl, extraConfig: opts.extraConfig })
  pinWindow(sandbox, width, height)

  const desktopDir = path.join(checkout, 'apps', 'desktop')
  const app = await _electron.launch({
    executablePath: electronBinary(checkout),
    args: [desktopDir, '--disable-gpu', '--no-sandbox'],
    env: buildEnv(sandbox, checkout, display, opts.env),
    cwd: desktopDir,
    timeout: 120_000,
  })

  const page = await app.firstWindow({ timeout: 120_000 })

  return {
    app,
    page,
    sandbox,
    checkout,
    sha: checkoutSha(checkout),
    close: async () => {
      await app.close().catch(() => undefined)
    },
  }
}

/**
 * Wait until the app is really usable: the composer editor (not the aria-hidden
 * sr-only textarea) is visible AND hit-testable, i.e. no boot/connecting overlay
 * is on top of it. Same predicate as upstream tests-js/scripts/desktop-chat-smoke.ts
 * `waitForChatReady`. A bare `textarea` query passes behind the boot overlay.
 */
export async function waitForShell(page: Page, timeoutMs = 180_000): Promise<number> {
  const t0 = Date.now()
  const composer = page
    .locator('[data-slot="composer-root"]')
    .locator('[contenteditable="true"]:visible, textarea:not([aria-hidden="true"]):not(.sr-only):visible')
    .first()

  await composer.waitFor({ state: 'visible', timeout: timeoutMs })
  await composer.click({ trial: true, timeout: timeoutMs })
  await page.waitForTimeout(1000)

  return Date.now() - t0
}

export async function shot(page: Page, file: string): Promise<string> {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  await page.screenshot({ path: file })

  return file
}

/** Install a unified package (agent half + desktop/plugin.js) into <home>/plugins/<name>. */
export function installUnifiedPackage(sandbox: Sandbox, packageDir: string, name = path.basename(packageDir)): string {
  const target = path.join(sandbox.hermesHome, 'plugins', name)

  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.cpSync(packageDir, target, { recursive: true, force: true })

  return target
}

/** Every renderer-visible text node, for grep-free assertions on what is ON SCREEN. */
export async function visibleText(page: Page): Promise<string> {
  return page.evaluate(() => document.body.innerText)
}
