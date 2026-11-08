/**
 * M0.4 driver (dev only): private Xvfb + mock model + isolated real Desktop → ONE session renders a reply → spike S1.
 * Writes spike.json + PNGs into <outdir>. Never touches a live home, display or gateway: isolation is asserted
 * (harness.recordIsolation throws) and recorded.
 *   node tools/desktop/m04_spike.ts <outdir>
 */
import { execFileSync, spawn } from 'node:child_process'
import * as fs from 'node:fs'
import * as net from 'node:net'
import * as path from 'node:path'

import { createSandbox, installDiskPlugin, launchDesktop, listenNow, send, shot, startXvfb, waitForShell } from './harness.ts'
import { PLUGIN, probeS1 } from './spike_s1.ts'

const out = path.resolve(process.argv[2] ?? path.join(process.env.HOME ?? '.', 'cf2/m04-out'))
fs.mkdirSync(out, { recursive: true })
const here = path.dirname(new URL(import.meta.url).pathname)
const MOCK_PORT = Number(process.env.CF_MOCK_PORT ?? 18931)
const REPLY = /mock|done|hello|ok|answer/i

const portFree = (p: number) => new Promise<boolean>(res => {
  const s = net.createServer().once('error', () => res(false)).once('listening', () => s.close(() => res(true)))
  s.listen(p, '127.0.0.1')
})

const res: Record<string, unknown> = { lane: 'desktop-spike', session_rendered: false }
const xvfb = await startXvfb(process.env.CF_DISPLAY ?? ':93')
if (!(await portFree(MOCK_PORT))) throw new Error(`mock port ${MOCK_PORT} busy`)
const mock = spawn(process.env.CF_MOCK_PYTHON ?? 'python3', [path.join(here, 'mock_llm.py'), String(MOCK_PORT)], { stdio: 'ignore' })
await new Promise(r => setTimeout(r, 800))
let l: Awaited<ReturnType<typeof launchDesktop>> | undefined
try {
  const sb = createSandbox('m04')
  installDiskPlugin(sb, 'cf-spike', PLUGIN)
  const t0 = Date.now()
  l = await launchDesktop({ sandbox: sb, display: xvfb.display, modelBaseUrl: `http://127.0.0.1:${MOCK_PORT}/v1` })
  const log = fs.createWriteStream(path.join(out, 'electron.log'))
  l.app.process().stdout?.pipe(log); l.app.process().stderr?.pipe(log)
  res.boot_ms = await waitForShell(l.page)
  res.isolation = l.isolation()
  res.mock = { port: MOCK_PORT, listen_pid_is_ours: listenNow().some(r => r.port === MOCK_PORT && r.pid === mock.pid) }
  await shot(l.page, path.join(out, '01-shell.png'))
  await send(l.page, 'hello [done]')
  const t1 = Date.now()
  const reply = await l.page.waitForFunction(() => {
    const t = (document.querySelector('[data-chat-surface]') as HTMLElement | null)?.innerText ?? ''
    return t.includes('hello [done]') && t.length > 'hello [done]'.length + 5 ? t : null
  }, undefined, { timeout: 120_000 }).then(h => h.jsonValue() as Promise<string>)
  await l.page.waitForTimeout(2500)
  const seen = await l.page.evaluate(() => (document.querySelector('[data-chat-surface]') as HTMLElement).innerText)
  res.reply_wait_ms = Date.now() - t1
  res.chat_text_seen = seen.slice(0, 600)
  res.session_rendered = seen.includes('hello [done]') && seen.replace('hello [done]', '').trim().length > 3 && REPLY.test(seen)
  await shot(l.page, path.join(out, '02-reply.png'))
  res.s1 = await probeS1(l.page, out)
} catch (e) {
  res.error = String(e)
  if (l) await shot(l.page, path.join(out, '99-error.png')).catch(() => undefined)
} finally {
  if (l) await l.close()
  mock.kill(); xvfb.proc.kill()
  fs.writeFileSync(path.join(out, 'run.json'), JSON.stringify(res, null, 2))
  console.log(JSON.stringify(res, null, 2))
}
