/// <reference path="./sdk.d.ts" />
// The wiring (C1–C10): one attach(ctx) call owns everything the plugin keeps
// alive — the ONE view, the ONE owned <style>, the ONE budgeted loop, the host
// feed, the config watch + poll, the reduced-motion listener and the surfaces —
// and one disposer that undoes all of it. Eager side effects (style paint, root
// attributes) happen at apply time so the skin exists even while the loop is
// parked; the loop only exists to animate (working clouds, the bloom). attach
// itself stays straight-line wiring: every decision lives in a named helper.
import { createBudgetedLoop, host, type BudgetedLoop, type PluginContext } from '@hermes/plugin-sdk'
import { pollPlan, resolveSettings, type FeedInput, type Settings } from '../domain/index.ts'
import { eventToFeed, stateSnapshot, type StateAtoms } from './feedmap.ts'
import { parseGround } from './ground.ts'
import { wireWatch } from './configwatch.ts'
import { drawClock, idleSince, initialClock, noteStateChange, wantsFrame, type LoopClock } from './looplogic.ts'
import { fieldCss } from './painter.ts'
import { registerSurfaces } from './surfaces.ts'
import { applyEnv, applyFeed, applySettings, initialView, type CfEnv, type CfView } from './view.ts'

const FALLBACK_GROUND = '#141416'
const REDUCE_QUERY = '(prefers-reduced-motion: reduce)'
const LOOP_FPS = 8

type Holder = { el: HTMLStyleElement | null; css: string }

/** Everything the paint/teardown helpers need, in one bundle. */
interface Attached {
  v: CfView
  clock: LoopClock
  loop: BudgetedLoop
  holder: Holder
}

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

/** One animation frame: advance the clock, repaint the field CSS in place. */
function draw(a: Attached, now: number): void {
  a.v.tMs = now
  a.v.sinceChangeMs = drawClock(a.clock, now)
  paintField(a)
}

function paintField(a: Attached): void {
  a.holder.css = fieldCss(a.v)
  if (a.holder.el !== null) a.holder.el.textContent = a.holder.css
}

function paintRoot(v: CfView): void {
  const el = document.documentElement
  el.setAttribute('data-cf-state', v.focusedState)
  if (v.focusedStored === null) el.removeAttribute('data-cf-session')
  else el.setAttribute('data-cf-session', v.focusedStored)
}

function paint(a: Attached): void {
  paintField(a)
  paintRoot(a.v)
}

/**
 * Create the ONE owned <style> inside the host's head. Called by the title-bar
 * mount's effect (A4: a host that never mounts us paints nothing); the cleanup
 * removes the element again. Every paint keeps `holder.css` current so whatever
 * moment the element appears, the skin is already whole.
 */
function mountStyle(a: Attached): () => void {
  const el = document.createElement('style')
  document.head.appendChild(el)
  el.textContent = a.holder.css
  a.holder.el = el
  return () => {
    el.remove()
    if (a.holder.el === el) a.holder.el = null
  }
}

/** A state change is PENDING until the first frame anchors it: bloom survives long parks. */
function armBloom(a: Attached): void {
  noteStateChange(a.clock)
  a.v.sinceChangeMs = 0
  a.loop.wake()
}

function applyInput(a: Attached, input: FeedInput): void {
  if (applyFeed(a.v, input)) armBloom(a)
  paint(a)
}

/** C5: a config maps to settings via the domain resolver; only a real change blooms. */
function configSettings(config: unknown): Settings {
  return resolveSettings(isRec(config) ? config.settings : undefined).settings
}

function applyConfig(a: Attached, config: unknown): void {
  if (applySettings(a.v, configSettings(config))) armBloom(a)
  paint(a)
}

/** The host feed: state atoms (first sight included) and every gateway event that is ours. */
function wireFeed(ctx: PluginContext, atoms: StateAtoms, onInput: (input: FeedInput) => void): () => void {
  const offs = Object.values(atoms).map(atom => atom.listen(() => onInput(stateSnapshot(atoms, Date.now()))))
  offs.push(ctx.onEvent('*', event => {
    const input = eventToFeed(event, Date.now())
    if (input !== null) onInput(input)
  }))
  return () => { for (const off of offs) off() }
}

/** C3: the OS reduced-motion switch is honoured live. */
function wireReduce(v: CfView, repaint: () => void): () => void {
  const media = matchMedia(REDUCE_QUERY)
  const onChange = (event: { matches: boolean }): void => {
    applyEnv(v, { reducedMotion: event.matches })
    repaint()
  }
  media.addEventListener('change', onChange)
  return () => media.removeEventListener('change', onChange)
}

/** Undo everything: reverse the registrations, drop the style, clear the root attributes. */
function teardown(a: Attached, offs: (() => void)[]): void {
  a.loop.dispose()
  for (const off of offs.reverse()) off()
  if (a.holder.el !== null) a.holder.el.remove()
  a.holder.el = null
  const el = document.documentElement
  el.removeAttribute('data-cf-state')
  el.removeAttribute('data-cf-session')
}

/** Wire the plugin. Idempotent per ctx; every registration flows through ctx so unload cleans up. */
export function attach(ctx: PluginContext): void {
  const env: CfEnv = { ...viewportOf(), ground: sampleGround(), reducedMotion: matchMedia(REDUCE_QUERY).matches }
  const v: CfView = initialView(env)
  const clock = initialClock()
  const holder: Holder = { el: null, css: '' }
  const loop = createBudgetedLoop(
    now => draw({ v, clock, loop, holder }, now),
    { fps: LOOP_FPS, idleWhen: () => !wantsFrame(v, idleSince(clock)) },
  )
  const a: Attached = { v, clock, loop, holder }
  const offs: (() => void)[] = []

  const atoms: StateAtoms = {
    activeSessionId: host.state.activeSessionId,
    busy: host.state.busy,
    busyBySession: host.state.busyBySession,
    focusedSessionId: host.state.focusedSessionId,
    focusedStoredSessionId: host.state.focusedStoredSessionId,
    gateway: host.state.gateway,
  }
  offs.push(wireFeed(ctx, atoms, input => applyInput(a, input)))
  offs.push(host.state.viewport.listen(vp => {
    applyEnv(v, vp)
    paint(a)
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
    { onFeed: input => applyInput(a, input), onSettings: config => applyConfig(a, config), pollWanted: () => pollPlan(v.feed, 0).pollActiveList },
  ))

  offs.push(wireReduce(v, () => paint(a)))
  offs.push(registerSurfaces(ctx, v, () => mountStyle(a)))
  applyInput(a, stateSnapshot(atoms, Date.now()))

  ctx.onDispose(() => teardown(a, offs))
}
