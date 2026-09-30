// Exploratory probe: boot the installed build, screenshot, dump landmarks.
import * as fs from 'node:fs'
import { createSandbox, launchDesktop, shot, waitForShell } from '../desktop_harness.ts'

const outDir = process.argv[2] ?? '/tmp/cf-probe'
fs.mkdirSync(outDir, { recursive: true })
const sandbox = createSandbox('cf-probe')
const t0 = Date.now()
const l = await launchDesktop({ runtime: process.argv[3] ?? 'installed', sandbox })
l.app.process().stderr?.on('data', d => fs.appendFileSync(`${outDir}/electron.log`, d))
l.app.process().stdout?.on('data', d => fs.appendFileSync(`${outDir}/electron.log`, d))
try {
  await shot(l.page, `${outDir}/00-first.png`)
  try {
    await waitForShell(l.page, 150_000)
  } catch (e) {
    console.log('waitForShell failed', String(e))
  }
  console.log('shell after ms', Date.now() - t0)
  await shot(l.page, `${outDir}/01-shell.png`)
  const info = await l.page.evaluate(() => ({
    title: document.title,
    text: document.body.innerText.slice(0, 1500),
    buttons: [...document.querySelectorAll('button[aria-label],a[aria-label]')].map(b => b.getAttribute('aria-label')).slice(0, 80),
  }))
  console.log(JSON.stringify(info, null, 1))
} finally {
  await l.close()
  console.log('sandbox', sandbox.root)
}
