// Ambient declarations for the three specifiers a disk plugin may import
// (@hermes/plugin-sdk, react, react/jsx-runtime — modelled after Hermes
// v0.22.7). Types only — never shipped, never imported. The browser globals the
// code touches (document, matchMedia, getComputedStyle) come from the default
// DOM lib; this file is a GLOBAL script on purpose: with a top-level import it
// would become a module and its `declare module` blocks would augment (not
// declare) — invisible.

// ---- react (the two doors the surfaces use) ---------------------------------------------------------

declare module 'react' {
  export function useSyncExternalStore<T>(
    subscribe: (onStoreChange: () => void) => () => void,
    getSnapshot: () => T,
  ): T
  export function useEffect(effect: () => void | (() => void), deps?: readonly unknown[]): void
}

declare module 'react/jsx-runtime' {
  export function jsx(type: unknown, props: Record<string, unknown> | null | undefined, key?: unknown): unknown
  export const Fragment: unknown
}

// ---- @hermes/plugin-sdk (v0.22.7, the doors the contract models) ------------------------------------

declare module '@hermes/plugin-sdk' {
  export interface ReadableAtom<T> {
    get(): T
    listen(fn: (value: T) => void): () => void
    subscribe(fn: (value: T) => void): () => void
  }

  export interface GatewayEvent {
    type: string
    session_id?: string | null
    payload?: unknown
  }

  export interface SessionRowSlotProps {
    /** The STORED (durable) session id — the lineage root, not the live id. */
    sessionId: string
  }

  export interface HermesHost {
    state: {
      activeSessionId: ReadableAtom<string | null>
      busy: ReadableAtom<boolean>
      busyBySession: ReadableAtom<Record<string, boolean>>
      focusedSessionId: ReadableAtom<string | null>
      focusedStoredSessionId: ReadableAtom<string | null>
      gateway: ReadableAtom<string>
      viewport: ReadableAtom<{ width: number; height: number }>
    }
    onEvent(type: string, listener: (event: GatewayEvent) => void): () => void
    request<T = unknown>(method: string, params?: unknown): Promise<T>
  }

  export const host: HermesHost

  export interface BudgetedLoop {
    dispose(): void
    isDormant(): boolean
    wake(): void
  }

  export interface BudgetedLoopOptions {
    fps?: number
    idleWhen?: () => boolean
    pauseWhenUnfocused?: boolean
  }

  export function createBudgetedLoop(draw: (now: number) => void, opts?: BudgetedLoopOptions): BudgetedLoop

  export const SESSION_ROW_AREAS: { readonly leading: 'sessionRow.leading'; readonly trailing: 'sessionRow.trailing' }
  export const STATUSBAR_AREAS: { readonly left: 'statusBar.left'; readonly right: 'statusBar.right' }
  export const TITLEBAR_AREAS: { readonly center: 'titleBar.center'; readonly left: 'titleBar.left'; readonly right: 'titleBar.right' }
  export const COMPOSER_AREAS: { readonly top: 'composer.top' } & Record<string, string>

  export interface PluginContribution {
    id: string
    area: string
    title?: string
    order?: number
    when?: () => boolean
    enabled?: boolean
    render?: () => unknown
    data?: unknown
  }

  export interface PluginContext {
    readonly source: string
    register(contribution: PluginContribution): () => void
    registerMany(contributions: PluginContribution[]): () => void
    onDispose(fn: () => void): void
    onEvent(type: string, listener: (event: GatewayEvent) => void): () => void
    setTimeout(fn: () => void, ms: number): () => void
    setInterval(fn: () => void, ms: number): () => void
    rest<T = unknown>(path: string, opts?: unknown): Promise<T>
  }
}
