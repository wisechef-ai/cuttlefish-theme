// Unit tests for the pure parts of tools/desktop_harness.ts (no Electron, no display).
// Run: cd tools && node --test tests/
import assert from 'node:assert/strict'
import * as fs from 'node:fs'
import * as os from 'node:os'
import * as path from 'node:path'
import { test } from 'node:test'

// Skip the real venv probe: buildEnv() resolves the backend interpreter eagerly.
process.env.CF_HERMES_PYTHON = '/usr/bin/python3'
process.env.TMPDIR = fs.mkdtempSync(path.join(os.tmpdir(), 'cf-harness-test-'))

const h = await import('../desktop_harness.ts')

test('buildEnv refuses the live displays', () => {
  const sb = h.createSandbox('t')
  for (const d of [':0', ':1']) {
    assert.throws(() => h.buildEnv(sb, '/x', d), /refusing DISPLAY/)
  }
})

test('buildEnv pins every home to the sandbox and strips inherited secrets + HERMES_*', () => {
  const sb = h.createSandbox('t')
  const saved = { ...process.env }
  Object.assign(process.env, {
    OPENAI_API_KEY: 'sk-leak',
    GH_TOKEN: 'leak',
    OPENROUTER_BASE_URL: 'http://leak',
    HERMES_YOLO_MODE: '1',
    HERMES_SESSION_ID: 'live',
    HERMES_DESKTOP_REMOTE_URL: 'http://operator',
  })
  try {
    const env = h.buildEnv(sb, '/checkout', ':93', { EXTRA: 'y' })
    assert.equal(env.HOME, sb.root)
    assert.equal(env.HERMES_HOME, sb.hermesHome)
    assert.equal(env.HERMES_DESKTOP_USER_DATA_DIR, sb.userDataDir)
    assert.equal(env.HERMES_DESKTOP_ISOLATED_BACKEND, '1')
    assert.equal(env.HERMES_DESKTOP_HERMES_ROOT, '/checkout')
    assert.equal(env.DISPLAY, ':93')
    assert.equal(env.EXTRA, 'y')
    for (const k of ['OPENAI_API_KEY', 'GH_TOKEN', 'OPENROUTER_BASE_URL', 'HERMES_YOLO_MODE', 'HERMES_SESSION_ID', 'HERMES_DESKTOP_REMOTE_URL']) {
      assert.equal(k in env, false, k)
    }
    assert.ok(sb.root.startsWith(process.env.TMPDIR!), 'sandbox lives under TMPDIR')
  } finally {
    for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k]
    Object.assign(process.env, saved)
  }
})

test('writeConfig targets the $0 local lane and never clobbers a spike-written config', () => {
  const sb = h.createSandbox('t')
  h.writeConfig(sb, { modelBaseUrl: 'http://127.0.0.1:9/v1', extraConfig: 'approvals:\n  mode: manual' })
  const cfg = fs.readFileSync(path.join(sb.hermesHome, 'config.yaml'), 'utf8')
  assert.match(cfg, /provider: custom:qwen38-local/)
  assert.match(cfg, /base_url: http:\/\/127\.0\.0\.1:9\/v1/)
  assert.match(cfg, /approvals:\n {2}mode: manual/)
  fs.writeFileSync(path.join(sb.hermesHome, 'config.yaml'), 'mine\n')
  h.writeConfig(sb)
  assert.equal(fs.readFileSync(path.join(sb.hermesHome, 'config.yaml'), 'utf8'), 'mine\n')
})

test('installUnifiedPackage copies into <home>/plugins/<name>', () => {
  const sb = h.createSandbox('t')
  const fixture = path.resolve(import.meta.dirname, '../spikes/fixtures/cf-spike')
  const target = h.installUnifiedPackage(sb, fixture)
  assert.equal(target, path.join(sb.hermesHome, 'plugins', 'cf-spike'))
  assert.ok(fs.existsSync(path.join(target, 'desktop', 'plugin.js')))
  assert.ok(fs.existsSync(path.join(target, 'dashboard', 'plugin_api.py')))
})

test('resolveCheckout rejects a non-checkout and an unbuilt checkout', () => {
  assert.throws(() => h.resolveCheckout(os.tmpdir()), /not a hermes-agent checkout/)
  const fake = fs.mkdtempSync(path.join(process.env.TMPDIR!, 'co-'))
  fs.mkdirSync(path.join(fake, 'hermes_cli'))
  fs.writeFileSync(path.join(fake, 'hermes_cli', 'main.py'), '')
  assert.throws(() => h.resolveCheckout(fake), /desktop not built/)
})
