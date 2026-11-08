/// <reference path="./sdk.d.ts" />
// The wiring (C1–C10): one attach(ctx) call owns everything the plugin keeps
// alive — the ONE view, the ONE owned <style>, the ONE budgeted loop, the host
// feed, the config watch + poll, the reduced-motion listener and the surfaces —
// and one disposer that undoes all of it. Eager side effects (style paint, root
// attributes) happen at apply time so the skin exists even while the loop is
// parked; the loop only exists to animate (working clouds, the bloom). attach
// itself stays straight-line wiring: every decision lives in a named helper.
import { createBudgetedLoop, host, type BudgetedLoop, type PluginContext } from '@hermes/plugin-sdk'
import { CLOUD_TRAVEL_MS, pollPlan, resolveSettings, type FeedInput, type Settings } from '../domain/index.ts'
import { eventToFeed, stateSnapshot, type StateAtoms } from './feedmap.ts'
import { parseGround } from './ground.ts'
import { wireWatch } from './configwatch.ts'
import { drawClock, idleSince, initialClock, noteStateChange, wantsFrame, type LoopClock } from './looplogic.ts'
import { fieldCss } from './painter.ts'
import { registerSurfaces } from './surfaces.ts'
import { applyEnv, applyFeed, applySettings, initialView, type CfEnv, type CfView } from './view.ts'

const FALLBACK_GROUND = '#141416'
const REDUCE_QUERY = '(prefers-reduced-motion: reduce)'
/** The budgeted loop's OWN budget is set high on purpose: it parks after every frame (its rAF would otherwise spin at
 *  60 Hz for as long as a session works — measured +2.2 pp of renderer CPU on the real Desktop) and a scoped timer
 *  wakes it FRAME_GAP_MS later, so the timer paces the frames (4/s, v2.1 D3) and the loop never skips one. */
const LOOP_FPS = 10
const FRAME_GAP_MS = 240
/** Frame times sit on this grid (below the loop's frame interval, so no frame is ever dropped), and — outside `alive`,
 *  where time only moves the clouds — wrap at the cloud cycle: the painted text then repeats exactly, and the engine
 *  re-uses the decoded image of a data-URI it has already seen instead of parsing a new SVG at every frame. */
const FRAME_GRID_MS = 250

type Holder = { el: HTMLStyleElement | null; css: string }

/** Everything the paint/teardown helpers need, in one bundle. */
interface Attached {
  v: CfView
  clock: LoopClock
  loop: BudgetedLoop
  holder: Holder
  /** Set by a frame, spent by the loop's own post-draw idle check: that one check says "park", every other says what the state wants. */
  restOwed: boolean
  cancelPace: (() => void) | null
  ctx: PluginContext
}

const isRec = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

/**
 * The user's own chat-surface ground, as the engine RESOLVES it on a thrown-away
 * probe of our own. The custom property itself reads back as its authored token
 * stream (core: var(--ui-bg-chrome) → color-mix(…)), which no parser should
 * guess at; a probe's background-color is the used colour.
 */
function sampleGround(): string {
  const probe = document.createElement('div')
  probe.style.setProperty('background-color', 'var(--ui-chat-surface-background)')
  document.body.appendChild(probe)
  const computed = getComputedStyle(probe).backgroundColor
  probe.remove()
  const parsed = parseGround(computed)
  return parsed !== null ? parsed : FALLBACK_GROUND
}

/** F8: a live theme switch. Re-sample on the config tick; only a CHANGED ground re-renders. */
function resampleGround(a: Attached): void {
  const ground = sampleGround()
  if (ground === a.v.ground) return
  applyEnv(a.v, { ground })
  paint(a)
}

/** The window the field paints for: the host's viewport atom, window size as the fallback. */
/** The field canvas is the chat SURFACE, not the window: the window minus the sidebar (260 px) and the title/status bars (56 px), measured on the
 *  real Desktop (surface 1340 × 944 at 1600 × 1000). Painting the whole window overshot the surface and clipped the gutter. */
export const SIDEBAR_PX = 260, CHROME_PX = 56
function viewportOf(vp: { width: number; height: number } = host.state.viewport.get()): { width: number; height: number } {
  const w = vp.width > 0 ? vp.width : 1200, h = vp.height > 0 ? vp.height : 800
  return { width: Math.max(480, w - SIDEBAR_PX), height: Math.max(360, h - CHROME_PX) }
}

/** The time a frame paints with: on the grid, and wrapped at the cloud cycle unless `alive` twinkles run on their own periods. */
export function frameTime(now: number, motion: string): number {
  const onGrid = Math.floor(now / FRAME_GRID_MS) * FRAME_GRID_MS
  return motion === 'alive' ? onGrid : onGrid % CLOUD_TRAVEL_MS
}

/** One animation frame: advance the clock, repaint the field CSS in place. */
function draw(a: Attached, now: number): void {
  a.v.tMs = frameTime(now, a.v.motion)
  a.v.sinceChangeMs = drawClock(a.clock, now)
  paintField(a)
  restUntilNextFrame(a)
}

/** The loop's idle check: right after a frame it answers "park" once (the timer wakes it), then it reports the state's wants. */
function idleNow(a: Attached): boolean {
  if (a.restOwed) {
    a.restOwed = false
    return true
  }
  return !wantsFrame(a.v, idleSince(a.clock))
}

/** Park the loop until the next frame is due; one timer at a time. */
function restUntilNextFrame(a: Attached): void {
  a.cancelPace?.()
  a.restOwed = true
  a.cancelPace = a.ctx.setTimeout(() => {
    a.cancelPace = null
    if (wantsFrame(a.v, idleSince(a.clock))) a.loop.wake()
  }, FRAME_GAP_MS)
}

/** Write the owned <style> only when its text really changed: an identical rewrite still makes the engine
 *  re-parse the sheet and re-decode the whole data-URI layer, and at rest NOTHING may re-render. */
function paintField(a: Attached): void {
  const css = fieldCss(a.v)
  const stale = css !== a.holder.css
  a.holder.css = css
  if (a.holder.el !== null && (stale || a.holder.el.textContent !== css)) a.holder.el.textContent = css
}

function paintRoot(v: CfView): void {
  const el = document.documentElement
  el.setAttribute('data-cf-state', v.focusedState)
  if (v.focusedStored === null) el.removeAttribute('data-cf-session')
  else el.setAttribute('data-cf-session', v.focusedStored)
}

/** Whatever just changed (settings, reduced motion, feed): a parked loop that is wanted again runs again. */
function wakeIfWanted(a: Attached): void {
  if (wantsFrame(a.v, idleSince(a.clock))) a.loop.wake()
}

function paint(a: Attached): void {
  paintField(a)
  paintRoot(a.v)
  wakeIfWanted(a)
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
  const before = a.v.version
  if (applyFeed(a.v, input)) armBloom(a)
  if (a.v.version !== before) paint(a)
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
    if (input === null) return
    onInput(input)
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
  a.cancelPace?.()
  a.cancelPace = null
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
  const a = { v, clock, holder, restOwed: false, cancelPace: null, ctx } as unknown as Attached
  a.loop = createBudgetedLoop(
    now => draw(a, now),
    { fps: LOOP_FPS, idleWhen: () => idleNow(a) },
  )
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
    applyEnv(v, viewportOf(vp))
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
    { onFeed: input => applyInput(a, input), onSettings: config => applyConfig(a, config), onTick: () => resampleGround(a), pollWanted: () => pollPlan(v.feed, Date.now()).pollActiveList },
  ))

  offs.push(wireReduce(v, () => paint(a)))
  offs.push(registerSurfaces(ctx, v, () => mountStyle(a)))
  applyInput(a, stateSnapshot(atoms, Date.now()))
  paint(a) // the first sight always paints, even when it changes nothing

  ctx.onDispose(() => teardown(a, offs))
}
