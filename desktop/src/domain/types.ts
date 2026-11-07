// The vocabulary types of the contract (contract/README.md "API the domain must export").
// Kept in one leaf module so every other domain module speaks the same words.

export type Motion = 'still' | 'alive' | 'off'
export type Signal =
  | 'idle' | 'busy' | 'tool' | 'needs_input' | 'failed'
  | 'unseen' | 'compacting' | 'subagents' | 'offline'
export type PatternKind = 'mottle' | 'clouds' | 'zebra' | 'blanch' | 'eyespot'

export const SIGNALS: readonly Signal[] = [
  'idle', 'busy', 'tool', 'needs_input', 'failed', 'unseen', 'compacting', 'subagents', 'offline',
]
export const PATTERN_KINDS: readonly PatternKind[] = ['mottle', 'clouds', 'zebra', 'blanch', 'eyespot']
export const MOTIONS: readonly Motion[] = ['still', 'alive', 'off']

export interface PatternSpec { base: PatternKind; density: number; contrast: number; scale: number }
export interface StateSpec { when: Signal; pattern: string; priority: number; label: string }
export interface Settings {
  intensity: number
  motion: Motion
  states: Record<string, StateSpec>
  patterns: Record<string, PatternSpec>
}
export interface Warning { code: string; path: string; message: string }

export interface Dot {
  x: number; y: number; r: number
  color: string        // '#rrggbb' — the organ's own pigment colour, before compositing
  alpha: number        // 0..1, composited over the ground
  role: 'organ' | 'eyespot'
}

export interface FieldInput {
  seed: string
  width: number; height: number
  hueDeg: number
  ground: string       // '#rrggbb'
  pattern: PatternSpec
  intensity: number
  motion: Motion
  reducedMotion: boolean
  tMs: number
  sinceChangeMs: number
}

export interface SwatchInput {
  seed: string
  hueDeg: number
  ground: string
  pattern: PatternSpec
  intensity: number
}
