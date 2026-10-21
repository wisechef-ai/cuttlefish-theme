// Ports: interfaces only (no code, no imports from domain internals). Hosts (desktop plugin, TUI
// widget, the trace replayer) implement these; domain and app never reach past them.

/** Injected time source, in seconds. The domain never reads a clock. */
export interface Clock { now(): number }

/** A normalised stream of session events for ONE lineage root (hook bus, desktop events, a replayed trace). */
export interface EventSource {
  subscribe(onEvent: (event: unknown) => void): () => void;
}

/** Persisted identity: slot/hue by lineage root, plus the live peers of the same profile. */
export interface IdentityStore {
  get(lineageRoot: string): { slot: number; hue_deg: number } | null;
  peerSlots(excludeLineageRoot: string): readonly number[];
}

/** Somewhere organs and text plates go (a transparent canvas, a terminal strip, a test buffer). Foreground colour only. */
export interface Surface {
  readonly scale: 'XL' | 'M' | 'S';
  readonly w: number;
  readonly h: number;
  draw(frame: { cols: number; rows: number; cells: ReadonlyArray<{ x: number; y: number; glyph: string; rgb: readonly [number, number, number]; e: number }>; text: ReadonlyArray<{ x: number; y: number; str: string; fg: string; bg: string }> }): void;
}
