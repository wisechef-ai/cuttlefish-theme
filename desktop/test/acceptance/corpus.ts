// ACCEPTANCE CONTRACT — shared corpus (locked).
// 20 lineage roots shaped like real stored ids, 3 grounds a user actually runs (Hermes dark, a Nord-like
// dim dark, Hermes light), and one surface size. Every rate is asserted over the WHOLE corpus.
export const W = 1200
export const H = 800

export const ROOTS: readonly string[] = Array.from({ length: 20 }, (_, i) =>
  `20261105_${String(90000 + i * 1373).padStart(6, '0')}_${(0x1f3a5c + i * 0x9e37).toString(16).slice(-6)}`)

export const GROUNDS: readonly string[] = ['#141416', '#2e3440', '#fbfbfa']

export const PRESETS = ['resting', 'working', 'needs_you', 'error', 'finished_unseen'] as const
export type Preset = (typeof PRESETS)[number]

/** "Settled" = long after the last state change (any bloom is over). */
export const SETTLED_MS = 6000
