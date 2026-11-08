// The adapter view-model: the ONE mutable thing the surfaces and the painter read.
// It folds three inputs — the feed (host state + events + polls), the settings
// (C5 live config) and the environment (viewport, ground, reduced motion) — into
// what C1/C6 need: the focused session's STORED id, its STATE through the domain,
// its identity hue and pattern, plus the subscribe channel the React surfaces
// ride (version bumps once per apply; a surface re-reads on its next render).
// Change detection is keyed on the focused STATE NAME alone: a focus switch or a
// settings reload that lands on the same state never blooms (C7 blooms state
// CHANGES only), and the runtime arms the bloom clock from applyFeed's return.
import {
  allocate, hueOfSlot, knownSessions, DEFAULT_SETTINGS, initialFeed, patternOf, reduceFeed, signalsOf, stateFor,
  type FeedInput, type FeedModel, type Motion, type PatternSpec, type Settings,
} from '../domain/index.ts'

/** Seed used while no session is focused: the skin exists before the first focus. */
export const NO_FOCUS_SEED = 'cuttlefish'

/** The seed the focused surfaces scatter on: the stored id, or the shared one when nobody is focused. */
export function seedOfStored(stored: string | null): string {
  return stored === null ? NO_FOCUS_SEED : stored
}

export interface CfEnv {
  width: number
  height: number
  ground: string
  reducedMotion: boolean
}

export type CfEnvPatch = Partial<CfEnv>
export type ViewListener = () => void

export interface CfView extends CfEnv {
  /** Inputs. */
  feed: FeedModel
  settings: Settings
  motion: Motion
  /** Derived per apply: what the focused session looks like. */
  focusedStored: string | null
  focusedState: string
  hueDeg: number
  pattern: PatternSpec
  /** Loop-time inputs, written by the draw callback (tMs) and the bloom clock. */
  tMs: number
  sinceChangeMs: number
  /** Bumped when ANY derived output changed (a session's state, the focus, settings, environment). */
  version: number
  /** Bumped when how things LOOK changed (settings, ground, viewport, motion) — a surface's memo key. */
  styleKey: number
  listen(fn: ViewListener): () => void
}

const SUBS = new WeakMap<CfView, Set<ViewListener>>()

/** Fan out one version bump to this view's subscribers, if any. */
function notify(v: CfView): void {
  const subs = SUBS.get(v)
  if (subs !== undefined) for (const fn of subs) fn()
}

const SLOTS = new WeakMap<CfView, Map<string, number>>()

/** A session's identity hue, allocated WITH its live peers (v2.1 r4): two live sessions never share a slot and sit as far apart as the 20-slot
 *  arc allows (≥ 34.5° for up to 5 sessions, ≥ 23° for 7, ≥ 11.5° beyond). Every session the feed knows (sorted) that has no slot yet gets one in
 *  that order, so the same set of sessions always gets the same hues; a slot is held while its session is known. The old code asked
 *  `allocate(id, [])` per row (no peers): 4.8 % of session pairs shared a hue and 24 % sat < 30° apart. */
export function hueFor(v: CfView, id: string): number {
  let m = SLOTS.get(v)
  if (m === undefined) { m = new Map(); SLOTS.set(v, m) }
  const live = new Set([...knownSessions(v.feed), id])
  for (const k of [...m.keys()]) if (!live.has(k)) m.delete(k)
  for (const k of [...live].sort()) if (!m.has(k)) m.set(k, allocate(k, [...m.values()]).slot)
  return hueOfSlot(m.get(id) as number)
}

/** The pattern a state renders with, never throwing: an unknown state degrades to mottle. */
export function safePattern(settings: Settings, state: string): PatternSpec {
  const ref = settings.states[state]?.pattern
  if (ref !== undefined && settings.patterns[ref] !== undefined) return patternOf(settings, state)
  return { ...settings.patterns.mottle }
}

/** Every session's resolved state plus the focus: the whole derived output of the feed, as one string. */
function fingerprint(v: CfView): string {
  const parts = Object.keys(v.feed.sessions).sort().map(id => `${id}=${stateFor(v.settings, signalsOf(v.feed, id))}`)
  return `${v.feed.focusedStored ?? ''}|${stateFor(v.settings, signalsOf(v.feed, v.feed.focusedStored ?? ''))}|${parts.join(',')}`
}

const PRINTS = new WeakMap<CfView, string>()

/** Recompute the derived fields from feed + settings, and bump the version. */
function derive(v: CfView): boolean {
  PRINTS.set(v, fingerprint(v))
  const before = v.focusedState
  const stored = v.feed.focusedStored
  v.focusedStored = stored
  v.hueDeg = stored === null ? allocate(NO_FOCUS_SEED, []).hue_deg : hueFor(v, stored)
  v.focusedState = stateFor(v.settings, signalsOf(v.feed, stored === null ? '' : stored))
  v.pattern = safePattern(v.settings, v.focusedState)
  v.version += 1
  notify(v)
  return v.focusedState !== before
}

/** The sight the plugin starts from: resting, unblloomed, on the fallback seed. */
export function initialView(env: CfEnv): CfView {
  const v: CfView = {
    feed: initialFeed(),
    settings: structuredClone(DEFAULT_SETTINGS) as Settings,
    motion: DEFAULT_SETTINGS.motion,
    width: env.width,
    height: env.height,
    ground: env.ground,
    reducedMotion: env.reducedMotion,
    focusedStored: null,
    focusedState: 'resting',
    hueDeg: allocate(NO_FOCUS_SEED, []).hue_deg,
    pattern: { ...DEFAULT_SETTINGS.patterns.mottle },
    tMs: 0,
    sinceChangeMs: 0,
    version: 0,
    styleKey: 0,
    listen(fn) {
      const subs = SUBS.get(this)
      if (!subs) return () => {}
      subs.add(fn)
      return () => { subs.delete(fn) }
    },
  }
  SUBS.set(v, new Set())
  derive(v)
  return v
}

/** One feed input in. Returns true when the FOCUSED STATE NAME moved (arm the bloom). */
export function applyFeed(v: CfView, input: FeedInput): boolean {
  const next = reduceFeed(v.feed, input)
  if (next === v.feed) return false   // the reducer returns its model untouched when nothing changed: nothing to re-derive or repaint
  v.feed = next
  // A burst of host events that leaves every session's state and the focus as they were changes nothing anyone can see:
  // no derive, no version bump, no notification — so no surface re-renders and no paint follows.
  if (fingerprint(v) === PRINTS.get(v)) return false
  return derive(v)
}

/** New settings, in place (C5): the state may legitimately move (a user state was removed). */
export function applySettings(v: CfView, settings: Settings): boolean {
  v.settings = settings
  v.motion = settings.motion
  v.styleKey += 1
  return derive(v)
}

/** The environment moved (viewport, ground, reduced motion); the feed is untouched. */
export function applyEnv(v: CfView, patch: CfEnvPatch): void {
  if (patch.width !== undefined) v.width = patch.width
  if (patch.height !== undefined) v.height = patch.height
  if (patch.ground !== undefined) v.ground = patch.ground
  if (patch.reducedMotion !== undefined) v.reducedMotion = patch.reducedMotion
  v.styleKey += 1
  v.version += 1
  notify(v)
}
