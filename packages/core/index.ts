// Flat export list for packages/core. P2-STATE / P2-SHADER append their exports below; keep one
// `export *` per line so concurrent additions merge trivially.
export * from './domain/blake2b.ts';
export * from './domain/identity.ts';
export * from './domain/motion.ts';
export * from './domain/oklch.ts';
export * from './domain/pattern.ts';
export * from './domain/tokens.ts';
export * from './ports/index.ts';
export * from './app/resolve.ts';
export { initial as hookInitial, reduce as hookReduce, resolve as hookResolve, reduceKeyed as hookReduceKeyed, trackInit, trackStep, STATES, STALE_S, REVIEW_DWELL_S } from './domain/state-hook.ts';
export type { State, HookEvent, HookModel, HookModels, HookPayload, Tracker } from './domain/state-hook.ts';
export { initial as desktopInitial, reduce as desktopReduce, resolve as desktopResolve, storedIds as desktopStoredIds, classifyParity, CORE_DOT_LABELS } from './domain/state-desktop.ts';
export type { DesktopInput, DesktopModel, Parity } from './domain/state-desktop.ts';
export * from './app/replay.ts';
