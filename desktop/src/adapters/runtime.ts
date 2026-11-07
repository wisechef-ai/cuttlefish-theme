/// <reference path="./sdk.d.ts" />
// The wiring (C1–C10): one attach(ctx) call owns everything the plugin keeps
// alive — the ONE view, the ONE owned <style>, the ONE budgeted loop, the host
// feed, the config watch + poll, the reduced-motion listener and the surfaces —
// and one disposer that undoes all of it. Eager side effects (style paint, root
// attributes) happen at apply time so the skin exists even while the loop is
// parked; the loop only exists to animate (working clouds, the bloom).
import { createBudgetedLoop, host, type PluginContext } from '@hermes/plugin-sdk'
import { pollPlan, resolveSettings, type FeedInput } from '../domain/index.ts'
import { eventToFeed, stateSnapshot, type StateAtoms } from './feedmap.ts'
import { parseGround } from './ground.ts'
import { wireWatch } from './configwatch.ts'
import { drawClock, idleSince, initialClock, noteStateChange, wantsFrame } from './looplogic.ts'
import { fieldCss } from './painter.ts'
import { registerSurfaces } from './surfaces.ts'
import { applyEnv, applyFeed, applySettings, initialView, type CfEnv, type CfView } from './view.ts'

const FALLBACK_GROUND = '#141416'
const REDUCE_QUERY = '(prefers-reduced-motion: reduce)'
const LOOP_FPS = 8

const isRec = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/** The user's own chat-surface ground, read from a thrown-away probe of our own. */
function sampleGround(): string {
  const probe = document.createElement('div')
  document.body.appendChild(probe)
  const computed = getComputedStyle(probe).getPropertyValue('--ui-chat-surface-background')
  probe.remove()
  return parseGround(computed) ?? FALLBACK_GROUND
}

/** The window the field paints for: the host's viewport atom, window size as the fallback. */
function viewportOf(): { width: number; height: number } {
  const vp = host.state.viewport.get()
  return { width: vp.width > 0 ? vp.width : 1200, height: vp.height > 0 ? vp.height : 800 }
}

/** Wire the plugin. Idempotent per ctx; every registration flows through ctx so unload cleans up. */
export function attach(ctx: PluginContext): void {
  const env: CfEnv = { ...viewportOf(), ground: sampleGround(), reducedMotion: matchMedia(REDUCE_QUERY).matches }
  const v: CfView = initialView(env)
  const clock = initialClock()
  const offs: (() => void)[] = []

  // The ONE owned <style>, created by the title-bar mount's effect (A4: a host that
  // never mounts us paints nothing) and kept current by every paint below.
  const holder: { el: HTMLStyleElement | null; css: string } = { el: null, css: '' }
  const paintField = (): void => {
    holder.css = fieldCss(v)
    if (holder.el !== null) holder.el.textContent = holder.css
  }
  const mountStyle = (): (() => void) => {
    const el = document.createElement('style')
    document.head.appendChild(el)
    el.textContent = holder.css
    holder.el = el
    return () => {
      el.remove()
      if (holder.el === el) holder.el = null
    }
  }

  const paintRoot = (): void => {
    const el = document.documentElement
    el.setAttribute('data-cf-state', v.focusedState)
    if (v.focusedStored === null) el.removeAttribute('data-cf-session')
    else el.setAttribute('data-cf-session', v.focusedStored)
  }
  const paint = (): void => {
    paintField()
    paintRoot()
  }

  const loop = createBudgetedLoop(
    now => {
      v.tMs = now
      v.sinceChangeMs = drawClock(clock, now)
      paintField()
    },
    { fps: LOOP_FPS, idleWhen: () => !wantsFrame(v, idleSince(clock)) },
  )

  const armBloom = (): void => {
    noteStateChange(clock)
    v.sinceChangeMs = 0
    loop.wake()
  }
  const applyInput = (input: FeedInput): void => {
    if (applyFeed(v, input)) armBloom()
    paint()
  }
  const applyConfig = (config: unknown): void => {
    if (applySettings(v, resolveSettings(isRec(config) ? config.settings : undefined).settings)) armBloom()
    paint()
  }

  // the host feed: state atoms (initial sight included) and every gateway event that is ours
  const atoms: StateAtoms = {
    activeSessionId: host.state.activeSessionId,
    busy: host.state.busy,
    busyBySession: host.state.busyBySession,
    focusedSessionId: host.state.focusedSessionId,
    focusedStoredSessionId: host.state.focusedStoredSessionId,
    gateway: host.state.gateway,
  }
  for (const atom of Object.values(atoms)) {
    offs.push(atom.listen(() => applyInput(stateSnapshot(atoms, Date.now()))))
  }
  offs.push(host.state.viewport.listen(vp => {
    applyEnv(v, vp)
    paint()
  }))
  offs.push(ctx.onEvent('*', event => {
    const input = eventToFeed(event, Date.now())
    if (input !== null) applyInput(input)
  }))

  // C5 live config + C9 the Python-half poll, on scoped timers (≥ 2 s apart)
  offs.push(wireWatch(
    {
      request: (method, params) => host.request(method, params),
      rest: path => ctx.rest(path),
      setTimeout: (fn, ms) => ctx.setTimeout(fn, ms),
      setInterval: (fn, ms) => ctx.setInterval(fn, ms),
      now: () => Date.now(),
    },
    { onFeed: applyInput, onSettings: applyConfig, pollWanted: () => pollPlan(v.feed, 0).pollActiveList },
  ))

  // C3: the OS reduced-motion switch is honoured live
  const media = matchMedia(REDUCE_QUERY)
  const onReduce = (event: { matches: boolean }): void => {
    applyEnv(v, { reducedMotion: event.matches })
    paint()
  }
  media.addEventListener('change', onReduce)

  offs.push(registerSurfaces(ctx, v, mountStyle))
  applyInput(stateSnapshot(atoms, Date.now()))

  ctx.onDispose(() => {
    loop.dispose()
    for (const off of offs.reverse()) off()
    media.removeEventListener('change', onReduce)
    if (holder.el !== null) holder.el.remove()
    holder.el = null
    const el = document.documentElement
    el.removeAttribute('data-cf-state')
    el.removeAttribute('data-cf-session')
  })
}
