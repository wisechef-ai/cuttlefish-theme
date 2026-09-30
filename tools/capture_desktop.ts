#!/usr/bin/env node
/**
 * capture_desktop.ts — screenshot the REAL Hermes desktop build (plan §3 tools/).
 *
 *   node tools/capture_desktop.ts --out /tmp/shot.png
 *        [--runtime installed|upstream|<checkout>]   default: installed
 *        [--package <unified plugin dir>]           install into the temp home before launch
 *        [--enable <plugin id>]                      flip it on via Settings → Plugins (the UI path)
 *        [--display :93]                             private Xvfb; ':1' is refused
 *        [--keep]                                    keep the temp sandbox (prints its path)
 *
 * Prints one JSON line: { runtime, sha, sandbox, shots: [...], enabled }.
 * Everything runs against a throwaway HOME/HERMES_HOME/userData (desktop_harness.ts).
 */
import * as fs from 'node:fs'
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import { createSandbox, installUnifiedPackage, launchDesktop, shot, waitForShell } from './desktop_harness.ts'
import { enablePluginViaSettings } from './desktop_ui.ts'

const { values } = parseArgs({
  options: {
    out: { type: 'string', default: 'desktop.png' },
    runtime: { type: 'string', default: 'installed' },
    package: { type: 'string' },
    enable: { type: 'string' },
    display: { type: 'string', default: process.env.CF_DISPLAY ?? ':93' },
    keep: { type: 'boolean', default: false },
  },
})

const sandbox = createSandbox('cf-capture')

if (values.package) {
  installUnifiedPackage(sandbox, path.resolve(values.package))
}

const launched = await launchDesktop({ runtime: values.runtime, sandbox, display: values.display })
const shots: string[] = []
let enabled: boolean | null = null

try {
  await waitForShell(launched.page)
  const out = path.resolve(values.out!)
  shots.push(await shot(launched.page, out))

  if (values.enable) {
    enabled = await enablePluginViaSettings(launched.page, values.enable)
    shots.push(await shot(launched.page, out.replace(/\.png$/, '') + '.settings.png'))
    await launched.page.keyboard.press('Escape')
    await launched.page.waitForTimeout(1500)
    shots.push(await shot(launched.page, out.replace(/\.png$/, '') + '.enabled.png'))
  }
} finally {
  await launched.close()

  if (!values.keep) {
    fs.rmSync(sandbox.root, { recursive: true, force: true })
  }
}

console.log(
  JSON.stringify({ runtime: values.runtime, sha: launched.sha, sandbox: values.keep ? sandbox.root : null, shots, enabled }),
)
