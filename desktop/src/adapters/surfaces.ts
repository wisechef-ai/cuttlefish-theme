/// <reference path="./sdk.d.ts" />
// The three surfaces (C1/C6): every sidebar row's swatch, the status-bar strip
// and the composer rim — the same language at three scales, all reading the ONE
// view. Every surface is a pull-based live component: it subscribes through the
// view's version (useSyncExternalStore) and re-reads on render, so a render is
// always pure observation and never wakes the loop (P3.2b). The titlebar mount
// is the plugin's permanent style owner; it renders nothing itself.
import { useEffect, useSyncExternalStore } from 'react'
import { jsx } from 'react/jsx-runtime'
import {
  COMPOSER_AREAS, SESSION_ROW_AREAS, STATUSBAR_AREAS, TITLEBAR_AREAS,
  type PluginContribution, type PluginContext, type SessionRowSlotProps,
} from '@hermes/plugin-sdk'
import { allocate, renderStrip, renderSwatch, signalsOf, stateFor } from '../domain/index.ts'
import { rimElement } from './rim.ts'
import { svgElement } from './svg.ts'
import { safePattern, seedOfStored, type CfView } from './view.ts'

/** The composer rim's height in px (brief: a 4–6 px band; the top of that range, so the cues read). */
const RIM_HEIGHT = 6

/** Re-render when — and only when — this surface's own derived key changes (React compares the snapshot by value). */
function useLive(v: CfView, key: () => string): void {
  useSyncExternalStore((cb: () => void) => v.listen(cb), key)
}

/** A row swatch's whole input: its own state and how things look. Another session's change leaves it alone. */
export function swatchKey(v: CfView, sessionId: string): string {
  return `${stateFor(v.settings, signalsOf(v.feed, sessionId))}|${v.styleKey}`
}

/** The strip's and the rim's whole input: the focused state, who is focused, how things look. */
export function chromeKey(v: CfView): string {
  return `${v.focusedState}|${v.focusedStored ?? ''}|${v.styleKey}`
}

/** The sidebar row swatch: the session's OWN state and identity, never the focused one's. */
function SwatchView({ v, sessionId }: { v: CfView } & SessionRowSlotProps): unknown {
  useLive(v, () => swatchKey(v, sessionId))
  const state = stateFor(v.settings, signalsOf(v.feed, sessionId))
  const out = renderSwatch({
    seed: sessionId,
    hueDeg: allocate(sessionId, []).hue_deg,
    ground: v.ground,
    pattern: safePattern(v.settings, state),
    intensity: v.settings.intensity,
  })
  return svgElement(jsx, out, { 'data-cf-session': sessionId, 'data-cf-state': state }, out.dots)
}

/** The focused state's words; when its label is empty (resting's locked default) or the settings do not name it, the
 *  state's own name — the strip always says where the session stands, and never throws. */
function labelOf(v: CfView, state: string): string {
  const found = v.settings.states[state]?.label
  return found !== undefined && found !== '' ? found : state.replaceAll('_', ' ')
}

/** The focused state's strip dots (the status strip's and the rim's one source). */
function focusedStrip(v: CfView): { strip: ReturnType<typeof renderStrip>; state: string } {
  const state = v.focusedState
  const strip = renderStrip({
    seed: seedOfStored(v.focusedStored),
    hueDeg: v.hueDeg,
    ground: v.ground,
    pattern: safePattern(v.settings, state),
    intensity: v.settings.intensity,
  })
  return { strip, state }
}

/** The status strip: the focused state's dots and its words. */
function StripView({ v }: { v: CfView }): unknown {
  useLive(v, () => chromeKey(v))
  const { strip, state } = focusedStrip(v)
  return jsx('div', {
    'data-cf-state': state,
    'data-cf-strip': 'cuttlefish',
    // one nowrap row: the label must sit BESIDE the glyph — stacked below it, the status bar's fixed height clipped it
    style: { display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap', lineHeight: 1, flexShrink: 0 },
    children: [svgElement(jsx, strip, { style: { display: 'block', flexShrink: 0 } }, strip.dots), labelOf(v, state)],
  })
}

/** The composer rim: one clean 6 px band echoing the state's glyph, no words, static. */
function RimView({ v }: { v: CfView }): unknown {
  useLive(v, () => chromeKey(v))
  const state = v.focusedState
  return jsx('div', {
    'data-cf-state': state,
    'data-cf-rim': 'cuttlefish',
    style: { width: '100%', height: RIM_HEIGHT, overflow: 'hidden', lineHeight: 0, pointerEvents: 'none' },
    children: rimElement(jsx, { base: safePattern(v.settings, state).base, hueDeg: v.hueDeg, ground: v.ground, intensity: v.settings.intensity, height: RIM_HEIGHT }),
  })
}

/**
 * The title-bar permanent mount: it owns the injected <style>. The element is
 * created by the mount's EFFECT (so a host that never mounts us paints nothing,
 * and unmount removes it), and the runtime keeps the current CSS ready for
 * whenever the element exists. Renders nothing itself.
 */
function TitleMount({ mountStyle }: { mountStyle: () => () => void }): unknown {
  useEffect(() => mountStyle(), [mountStyle])
  return null
}

/** Register the surfaces once; the returned disposer removes every contribution. */
export function registerSurfaces(ctx: PluginContext, v: CfView, mountStyle: () => () => void): () => void {
  const contributions: PluginContribution[] = [
    {
      id: 'swatch',
      area: SESSION_ROW_AREAS.leading,
      order: 0,
      data: { render: ({ sessionId }: SessionRowSlotProps) => jsx(SwatchView, { v, sessionId }) },
    },
    { id: 'strip', area: STATUSBAR_AREAS.right, order: 0, render: () => jsx(StripView, { v }) },
    { id: 'rim', area: COMPOSER_AREAS.top, order: 0, render: () => jsx(RimView, { v }) },
    { id: 'title', area: TITLEBAR_AREAS.center, order: 0, render: () => jsx(TitleMount, { mountStyle }) },
  ]
  const offs = contributions.map(c => ctx.register(c))
  return () => { for (const off of offs) off() }
}
