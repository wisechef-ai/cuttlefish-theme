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
import { svgElement } from './svg.ts'
import { NO_FOCUS_SEED, safePattern, type CfView } from './view.ts'

function useLive(v: CfView): void {
  useSyncExternalStore((cb: () => void) => v.listen(cb), () => v.version)
}

/** The sidebar row swatch: the session's OWN state and identity, never the focused one's. */
function SwatchView({ v, sessionId }: { v: CfView } & SessionRowSlotProps): unknown {
  useLive(v)
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

/** The focused state's words + dots, shared by the status strip and the composer rim. */
function stateChip(v: CfView, attrs: Record<string, unknown>): unknown {
  const state = v.focusedState
  const label = v.settings.states[state]?.label ?? ''
  const out = renderStrip({
    seed: v.focusedStored ?? NO_FOCUS_SEED,
    hueDeg: v.hueDeg,
    ground: v.ground,
    pattern: safePattern(v.settings, state),
    intensity: v.settings.intensity,
  })
  return jsx('div', { 'data-cf-state': state, ...attrs, children: [svgElement(jsx, out, {}, out.dots), label] })
}

function StripView({ v }: { v: CfView }): unknown {
  useLive(v)
  return stateChip(v, { 'data-cf-strip': 'cuttlefish' })
}

function RimView({ v }: { v: CfView }): unknown {
  useLive(v)
  return stateChip(v, { 'data-cf-rim': 'cuttlefish' })
}

/**
 * The title-bar permanent mount: it owns the injected <style>. The element is
 * created by the mount's EFFECT (so a host that never mounts us paints nothing,
 * and unmount removes it), and the runtime keeps the current CSS ready for
 * whenever the element exists. Renders nothing itself.
 */
function TitleMount({ v, mountStyle }: { v: CfView; mountStyle: () => () => void }): unknown {
  useLive(v)
  useEffect(() => mountStyle())
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
    { id: 'title', area: TITLEBAR_AREAS.center, order: 0, render: () => jsx(TitleMount, { v, mountStyle }) },
  ]
  const offs = contributions.map(c => ctx.register(c))
  return () => { for (const off of offs) off() }
}
