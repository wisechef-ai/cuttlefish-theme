// Exploratory: what does Capabilities ▸ Plugins list as Installed with a unified package present?
import * as fs from 'node:fs'
import * as path from 'node:path'
import { createSandbox, installUnifiedPackage, launchDesktop, shot, waitForShell } from '../desktop_harness.ts'
import { gotoRoute } from '../desktop_ui.ts'

const out = process.argv[2] ?? '/tmp/cf-probe-plugins'
fs.mkdirSync(out, { recursive: true })
const sandbox = createSandbox('cf-probe-pl')
installUnifiedPackage(sandbox, path.resolve(import.meta.dirname, 'fixtures', 'cf-spike'), 'cf-spike')
const l = await launchDesktop({ sandbox })
try {
  await waitForShell(l.page)
  await gotoRoute(l.page, '/capabilities?tab=plugins')
  await l.page.waitForTimeout(3000)
  await l.page.getByText('Installed', { exact: true }).first().click()
  await l.page.waitForTimeout(1500)
  await shot(l.page, `${out}/installed.png`)
  const cards = await l.page.evaluate(() =>
    [...document.querySelectorAll('[data-catalog-card]')].map(c => ({
      id: c.getAttribute('data-entry-id'),
      text: (c as HTMLElement).innerText.slice(0, 160),
    })),
  )
  console.log(JSON.stringify(cards, null, 1))
  const rows = await l.page.evaluate(() =>
    [...document.querySelectorAll('[data-testid^="plugin-row-"]')].map(e => e.getAttribute('data-testid')),
  )
  console.log('rows', rows)
} finally {
  await l.close()
  fs.rmSync(sandbox.root, { recursive: true, force: true })
}
