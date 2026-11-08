/** S1 diagnostics (dev only): WHY a computed value / pixel did or did not change. node tools/desktop/spike_s1_diag.ts <outdir> */
import * as fs from 'node:fs'
import * as path from 'node:path'

import { createSandbox, installDiskPlugin, launchDesktop, shot, startXvfb, waitForShell } from './harness.ts'
import { PLUGIN } from './spike_s1.ts'

const out = path.resolve(process.argv[2] ?? path.join(process.env.HOME ?? '.', 'cf2/m04-diag'))
fs.mkdirSync(out, { recursive: true })
const xvfb = await startXvfb(process.env.CF_DISPLAY ?? ':94')
const sb = createSandbox('m04diag')
installDiskPlugin(sb, 'cf-spike', PLUGIN)
const l = await launchDesktop({ sandbox: sb, display: xvfb.display })
const res: Record<string, unknown> = {}
try {
  await waitForShell(l.page); await l.page.waitForTimeout(3000)
  res.diag = await l.page.evaluate(async () => {
    const root = document.documentElement
    root.setAttribute('data-cfspike-field', '1'); root.setAttribute('data-cfspike-ring', '1')
    await new Promise(r => setTimeout(r, 1500))
    const surface = document.querySelector('[data-chat-surface]') as HTMLElement
    const cs = document.querySelector('[data-slot="composer-surface"]') as HTMLElement
    const sr = surface.getBoundingClientRect()
    const chain = (el: Element | null) => { const o: unknown[] = []; for (let e = el; e && e !== document.body; e = e.parentElement) { const s = getComputedStyle(e); o.push([e.tagName.toLowerCase(), e.getAttribute('data-slot') ?? '', s.backgroundColor, s.backgroundImage.slice(0, 20), s.opacity, s.position, s.zIndex]) } return o }
    const covering: unknown[] = []
    for (const e of surface.querySelectorAll('*')) { const r = e.getBoundingClientRect(); if (r.width >= sr.width * 0.9 && r.height >= sr.height * 0.5) { const s = getComputedStyle(e); covering.push([e.tagName.toLowerCase(), e.getAttribute('data-slot') ?? '', e.className.toString().slice(0, 80), s.backgroundColor, s.backgroundImage.slice(0, 20), s.position, s.zIndex]) } }
    const st = getComputedStyle(cs)
    return {
      surface_rect: [sr.x, sr.y, sr.width, sr.height], surface_bg: getComputedStyle(surface).backgroundColor,
      surface_bg_image: getComputedStyle(surface).backgroundImage.slice(0, 30), surface_bg_size: getComputedStyle(surface).backgroundSize,
      covering, chain_at_point: chain(document.elementFromPoint(sr.x + 400, sr.y + 300)),
      composer_border: st.borderTopColor, composer_transition: st.transition, composer_cls: cs.className.slice(0, 200),
      ring_var: st.getPropertyValue('--dt-composer-ring'), strength: st.getPropertyValue('--composer-ring-strength'), input: st.getPropertyValue('--dt-input'),
      animations: cs.getAnimations().map(a => [a.playState, (a as CSSTransition).transitionProperty ?? '']),
      visibility: document.visibilityState, hidden: document.hidden,
    }
  })
  await l.page.waitForTimeout(800)
  await shot(l.page, path.join(out, 'd1-both-on.png'))
  res.after_more = await l.page.evaluate(() => getComputedStyle(document.querySelector('[data-slot="composer-surface"]')!).borderTopColor)
} catch (e) { res.error = String(e) } finally {
  await l.close(); xvfb.proc.kill()
  fs.writeFileSync(path.join(out, 'diag.json'), JSON.stringify(res, null, 1)); console.log(JSON.stringify(res, null, 1))
}
