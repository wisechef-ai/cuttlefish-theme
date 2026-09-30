/**
 * Spike 09 follow-up — does setColor(id, null) repaint the tab dot and the sidebar row dot?
 *   node tools/spikes/09-setcolor-override/null-repaint.ts [--runtime installed|upstream]
 * One idle, focused session; set pink -> null -> set -> null; poll every dot every 250 ms and print transitions.
 */
import * as path from 'node:path'
import { parseArgs } from 'node:util'

import { createSandbox, installUnifiedPackage, launchDesktop, shot, waitForShell } from '../../desktop_harness.ts'
import { enablePluginViaSettings, gotoRoute } from '../../desktop_ui.ts'

const { values } = parseArgs({ options: { runtime: { type: 'string', default: 'installed' } } })
const sandbox = createSandbox('cf-s09n')
installUnifiedPackage(sandbox, path.resolve(import.meta.dirname, '..', 'fixtures', 'cf-spike'), 'cf-spike')
const l = await launchDesktop({ runtime: values.runtime, sandbox })
const p = l.page
const dots = () =>
  p.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>('span.rounded-full')]
      .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.width < 12 && (r.y < 40 || (r.x < 60 && r.y > 380)) })
      .map(e => `${e.getBoundingClientRect().y < 40 ? 'tab' : 'row'}=${getComputedStyle(e).backgroundColor.replace(/color\(srgb .*/, 'grey')}${e.getAttribute('aria-label') ? `(${e.getAttribute('aria-label')})` : ''}`)
      .join('  '),
  )
const ls = () => p.evaluate(() => localStorage.getItem('hermes.desktop.sessionColors'))
const out: string[] = []
const poll = async (label: string, ms: number) => {
  const t0 = Date.now()
  let last = ''
  while (Date.now() - t0 < ms) {
    const d = await dots()
    if (d !== last) { out.push(`${label} +${Date.now() - t0}ms  ${d}   ls=${await ls()}`); last = d }
    await p.waitForTimeout(250)
  }
}
try {
  await waitForShell(p)
  await enablePluginViaSettings(p, 'CF Spike')
  await gotoRoute(p, '/')
  await p.waitForTimeout(1500)
  const ed = p.locator('[data-slot="composer-root"] [contenteditable="true"]:visible').first()
  await ed.click()
  await p.keyboard.type('Reply with just the word alpha.')
  await p.keyboard.press('Enter')
  {
    // idle = no "Session running" dot for 6 consecutive seconds (a 4 s turn plus title/list refresh)
    let quiet = 0
    const t0 = Date.now()
    while (Date.now() - t0 < 180_000 && quiet < 6) {
      await p.waitForTimeout(1000)
      quiet = (await dots()).includes('Session running') || Date.now() - t0 < 8000 ? 0 : quiet + 1
    }
    out.push(`idle after ${Date.now() - t0}ms`)
  }
  const A = await p.evaluate(() => (window as any).__cfSpike.states.at(-1).focusedStoredSessionId)
  const set = (c: string | null) => p.evaluate(([id, c]) => (window as any).__cfSpike.setColor(id, c), [A, c] as any)
  out.push(`stored id A=${A}`)
  const fiberProps = () => p.evaluate(() => {
    const res: any[] = []
    for (const el of document.querySelectorAll<HTMLElement>('span.rounded-full')) {
      const r = el.getBoundingClientRect()
      if (!(r.width > 0 && r.width < 12 && (r.y < 40 || (r.x < 60 && r.y > 380)))) continue
      const key = Object.keys(el).find(k => k.startsWith('__reactFiber$'))
      let f: any = key ? (el as any)[key] : null
      for (let i = 0; f && i < 12; i++, f = f.return) {
        const pr = f.memoizedProps
        if (pr && 'storedSessionId' in pr) { res.push({ where: r.y < 40 ? 'tab' : 'row', storedSessionId: pr.storedSessionId, session: pr.session && { id: pr.session.id, root: pr.session._lineage_root_id, ids: pr.session._lineage_ids, title: pr.session.title, profile: pr.session.profile } }); break }
      }
    }
    return res
  })
  // What (if anything) makes an idle dot pick up a colour written to the store?
  await set('#e0457b'); await poll('set pink (idle)        ', 3000)
  await gotoRoute(p, '/capabilities?tab=plugins'); await p.waitForTimeout(800); await gotoRoute(p, '/'); await poll('route away + back (remount)', 4000)
  await p.setViewportSize({ width: 1300, height: 860 }); await p.waitForTimeout(500); await p.setViewportSize({ width: 1400, height: 900 }); await poll('viewport resize', 3000)
  await p.evaluate(() => window.dispatchEvent(new Event('storage'))); await poll('storage event', 2000)
  out.push('sidebar rows in DOM: ' + (await p.locator('[aria-label="Session actions"]').count()))
  await p.evaluate(() => location.reload()); await waitForShell(p); await p.waitForTimeout(2500); await poll('location.reload()', 3000)
  console.log(out.join('\n'))
} finally {
  await l.close()
}
