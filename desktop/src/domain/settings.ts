// Settings resolution: the whole C2/C5 vocabulary (5 presets, user states and patterns, ranges
// and the exact warning codes of contract/config-vectors.json). Every bad input is rejected with a
// NAMED warning and keeps its default; every good remap is honoured. resolveSettings never throws
// and never mutates its input — including the dangerous key names, which are skipped silently
// (own-key reads only, computed-key literals only, so nothing can reach a shared prototype).
import { MOTIONS, PATTERN_KINDS, SIGNALS, type Motion, type PatternKind, type PatternSpec, type Settings, type Signal, type StateSpec, type Warning } from './types.ts'

/** Ranges from contract/config-vectors.json "ranges". */
const RANGE = {
  intensity: [0, 2],
  density: [0.25, 4],
  contrast: [0, 2],
  scale: [0.25, 4],
  priority: [-1000, 1000],
  label_max: 24,
} as const

const PATTERNS: Record<string, PatternSpec> = {
  mottle: { base: 'mottle', density: 1, contrast: 1, scale: 1 },
  clouds: { base: 'clouds', density: 1, contrast: 1, scale: 1 },
  zebra: { base: 'zebra', density: 1, contrast: 1, scale: 1 },
  blanch: { base: 'blanch', density: 1, contrast: 1, scale: 1 },
  eyespot: { base: 'eyespot', density: 1, contrast: 1, scale: 1 },
}
const STATES: Record<string, StateSpec> = {
  resting: { when: 'idle', pattern: 'mottle', priority: 0, label: '' },
  working: { when: 'busy', pattern: 'clouds', priority: 60, label: 'working' },
  needs_you: { when: 'needs_input', pattern: 'zebra', priority: 100, label: 'needs you' },
  error: { when: 'failed', pattern: 'blanch', priority: 80, label: 'error' },
  finished_unseen: { when: 'unseen', pattern: 'eyespot', priority: 40, label: 'done' },
}

const deepFrozen = <T>(v: T): T => Object.freeze(structuredClone(v))

/** The five presets of the spec, exactly as contract/config-vectors.json "defaults" pins them. */
export const DEFAULT_SETTINGS: Settings = deepFrozen({ intensity: 1, motion: 'still', states: STATES, patterns: PATTERNS })

const isRec = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

/** Key names that can smuggle a write onto a shared prototype: never read, never emitted. */
const DANGEROUS = new Set(['__proto__', 'constructor', 'prototype'])

function ownKeys(raw: Record<string, unknown>): string[] {
  return Object.keys(raw).filter(k => !DANGEROUS.has(k))
}

function warn(warnings: Warning[], path: string, code: string, what: string): void {
  warnings.push({ code, path, message: `${what} at ${path}` })
}

/** A finite number inside its range, or the default with a named warning. */
function readNum(warnings: Warning[], path: string, v: unknown, def: number, lo: number, hi: number, what: string): number {
  if (v === undefined) return def
  if (typeof v !== 'number' || !Number.isFinite(v)) { warn(warnings, path, 'type', `${what} is not a finite number`); return def }
  if (v < lo || v > hi) { warn(warnings, path, 'range', `${what} is outside [${lo}, ${hi}]`); return def }
  return v
}

function readLabel(warnings: Warning[], path: string, v: unknown, def: string): string {
  if (v === undefined) return def
  if (typeof v !== 'string') { warn(warnings, path, 'type', 'label is not a string'); return def }
  if (v.length > RANGE.label_max) { warn(warnings, path, 'range', `label is longer than ${RANGE.label_max} characters`); return def }
  return v
}

const isSignal = (v: unknown): v is Signal => typeof v === 'string' && (SIGNALS as readonly string[]).includes(v)
const isKind = (v: unknown): v is PatternKind => typeof v === 'string' && (PATTERN_KINDS as readonly string[]).includes(v)
const isMotion = (v: unknown): v is Motion => typeof v === 'string' && (MOTIONS as readonly string[]).includes(v)

interface PatternField { key: 'density' | 'contrast' | 'scale'; lo: number; hi: number }
const PATTERN_FIELDS: readonly PatternField[] = [
  { key: 'density', lo: RANGE.density[0], hi: RANGE.density[1] },
  { key: 'contrast', lo: RANGE.contrast[0], hi: RANGE.contrast[1] },
  { key: 'scale', lo: RANGE.scale[0], hi: RANGE.scale[1] },
]

function patternNumbers(warnings: Warning[], path: string, v: Record<string, unknown>, spec: PatternSpec): PatternSpec {
  const out = { ...spec }
  for (const f of PATTERN_FIELDS) out[f.key] = readNum(warnings, `${path}.${f.key}`, v[f.key], spec[f.key], f.lo, f.hi, f.key)
  return out
}

function reportUnknownKeys(warnings: Warning[], path: string, v: Record<string, unknown>, known: readonly string[]): void {
  for (const k of ownKeys(v)) if (!known.includes(k)) warn(warnings, `${path}.${k}`, 'unknown', `unknown key ${k}`)
}

/** Patterns first: a state may point at a user pattern defined in the same input. */
function resolvePatterns(raw: unknown, warnings: Warning[]): Record<string, PatternSpec> {
  const out: Record<string, PatternSpec> = structuredClone(PATTERNS)
  if (raw === undefined) return out
  if (!isRec(raw)) { warn(warnings, 'patterns', 'type', 'patterns must be a mapping'); return out }
  for (const name of ownKeys(raw)) {
    const spec = name in PATTERNS ? tuneBuiltin(name, raw[name], out[name], warnings) : newUserPattern(name, raw[name], warnings)
    if (spec) out[name] = spec
  }
  return out
}

/** A built-in pattern is tuned, never re-based and never removed. */
function tuneBuiltin(name: string, v: unknown, def: PatternSpec, warnings: Warning[]): PatternSpec | undefined {
  const path = `patterns.${name}`
  if (v === null) { warn(warnings, path, 'required', 'a built-in pattern cannot be removed'); return undefined }
  if (!isRec(v)) { warn(warnings, path, 'type', 'a pattern must be a mapping'); return undefined }
  if (v.base !== undefined && v.base !== name) warn(warnings, `${path}.base`, 'required', 'a built-in pattern keeps its own base')
  reportUnknownKeys(warnings, path, v, PATTERN_KEYS)
  return patternNumbers(warnings, path, v, def)
}

/** A new user pattern needs a valid base; its numbers start from the defaults. */
function newUserPattern(name: string, v: unknown, warnings: Warning[]): PatternSpec | undefined {
  const path = `patterns.${name}`
  if (v === null) return undefined                    // removing a user pattern that is not there: nothing to do
  if (!isRec(v)) { warn(warnings, path, 'type', 'a pattern must be a mapping'); return undefined }
  if (v.base === undefined) { warn(warnings, `${path}.base`, 'missing', 'a new pattern needs a base'); return undefined }
  if (!isKind(v.base)) { warn(warnings, `${path}.base`, 'enum', 'base must be one of the five pattern kinds'); return undefined }
  reportUnknownKeys(warnings, path, v, PATTERN_KEYS)
  return patternNumbers(warnings, path, v, { base: v.base, density: 1, contrast: 1, scale: 1 })
}

const PATTERN_KEYS = ['base', 'density', 'contrast', 'scale']

interface StateDraft { spec: StateSpec; fatal: boolean }

/** A field's read result: the value the draft will carry, and whether a NEW state dies on it. */
interface Field<T> { value: T; fatal: boolean }

/** A field a new state did not provide: warned, and fatal for the new state. */
function missingField<T>(warnings: Warning[], path: string, field: string, what: string, fallback: T): Field<T> {
  warn(warnings, `${path}.${field}`, 'missing', what)
  return { value: fallback, fatal: true }
}

/** A field that failed validation: warned; a preset keeps its own value, a new state dies. */
function badField<T>(warnings: Warning[], path: string, field: string, code: string, what: string, fallback: T, isNew: boolean): Field<T> {
  warn(warnings, `${path}.${field}`, code, what)
  return { value: fallback, fatal: isNew }
}

function readWhen(warnings: Warning[], path: string, v: unknown, def: Signal | undefined, isNew: boolean): Field<Signal> {
  if (v === undefined) {
    return isNew ? missingField(warnings, path, 'when', 'a new state needs a when signal', 'idle')
      : { value: def ?? 'idle', fatal: false }
  }
  if (!isSignal(v)) return badField(warnings, path, 'when', 'enum', 'when must be one of the nine signals', def ?? 'idle', isNew)
  return { value: v, fatal: false }
}

function readPatternRef(warnings: Warning[], path: string, v: unknown, def: string | undefined, patterns: Record<string, PatternSpec>, isNew: boolean): Field<string> {
  if (v === undefined) {
    return isNew ? missingField(warnings, path, 'pattern', 'a new state needs a pattern', '')
      : { value: def ?? '', fatal: false }
  }
  if (typeof v !== 'string' || !(v in patterns)) {
    return badField(warnings, path, 'pattern', 'unknown', `pattern ${JSON.stringify(v)} is not defined`, def ?? '', isNew)
  }
  return { value: v, fatal: false }
}

function readPriority(warnings: Warning[], path: string, v: unknown, def: number | undefined, isNew: boolean): Field<number> {
  const n = readNum(warnings, `${path}.priority`, v, def ?? Number.NaN, RANGE.priority[0], RANGE.priority[1], 'priority')
  if (v === undefined) {
    return isNew ? missingField(warnings, path, 'priority', 'a new state needs a priority', def ?? 0)
      : { value: def ?? 0, fatal: false }
  }
  if (Number.isNaN(n)) return { value: def ?? 0, fatal: isNew }
  return { value: n, fatal: false }
}

function draftState(warnings: Warning[], name: string, v: Record<string, unknown>, def: StateSpec | undefined, patterns: Record<string, PatternSpec>): StateDraft | undefined {
  const path = `states.${name}`
  const isNew = def === undefined
  const when = readWhen(warnings, path, v.when, def?.when, isNew)
  const pattern = readPatternRef(warnings, path, v.pattern, def?.pattern, patterns, isNew)
  const priority = readPriority(warnings, path, v.priority, def?.priority, isNew)
  const label = readLabel(warnings, `${path}.label`, v.label, def?.label ?? name)
  reportUnknownKeys(warnings, path, v, ['when', 'pattern', 'priority', 'label'])
  return {
    spec: { when: when.value, pattern: pattern.value, priority: priority.value, label },
    fatal: when.fatal || pattern.fatal || priority.fatal,
  }
}

function resolveStates(raw: unknown, patterns: Record<string, PatternSpec>, warnings: Warning[]): Record<string, StateSpec> {
  const out: Record<string, StateSpec> = structuredClone(STATES)
  if (raw === undefined) return out
  if (!isRec(raw)) { warn(warnings, 'states', 'type', 'states must be a mapping'); return out }
  for (const name of ownKeys(raw)) {
    const v = raw[name]
    if (v === null) {
      if (name === 'resting') warn(warnings, `states.${name}`, 'required', 'resting cannot be removed')
      else delete out[name]
      continue
    }
    if (!isRec(v)) {
      warn(warnings, `states.${name}`, 'type', 'a state must be a mapping or null to remove it')
      continue
    }
    const draft = draftState(warnings, name, v, STATES[name], patterns)
    if (draft && !draft.fatal) out[name] = draft.spec
  }
  return out
}

/** Resolve a raw settings mapping onto the defaults. Never throws; never mutates `raw`.
 *  null is "nothing was given" (the defaults, silently); any other non-mapping is a type warning. */
export function resolveSettings(raw: unknown): { settings: Settings; warnings: Warning[] } {
  const warnings: Warning[] = []
  if (raw === null || raw === undefined) {
    return { settings: structuredClone(DEFAULT_SETTINGS) as Settings, warnings }
  }
  if (!isRec(raw)) {
    warn(warnings, 'settings', 'type', 'settings must be a mapping')
    return { settings: structuredClone(DEFAULT_SETTINGS) as Settings, warnings }
  }
  const intensity = readNum(warnings, 'intensity', raw.intensity, 1, RANGE.intensity[0], RANGE.intensity[1], 'intensity')
  let motion: Motion = 'still'
  if (raw.motion !== undefined) {
    if (isMotion(raw.motion)) motion = raw.motion
    else warn(warnings, 'motion', 'enum', 'motion must be still, alive or off')
  }
  const patterns = resolvePatterns(raw.patterns, warnings)
  const states = resolveStates(raw.states, patterns, warnings)
  for (const k of ownKeys(raw)) {
    if (!['intensity', 'motion', 'states', 'patterns'].includes(k)) warn(warnings, k, 'unknown', `unknown key ${k}`)
  }
  return { settings: { intensity, motion, states, patterns }, warnings }
}

/** The state whose signal is on with the highest priority; ties break alphabetically; none -> resting. */
export function stateFor(settings: Settings, signals: ReadonlySet<Signal>): string {
  let best: string | null = null
  let bestPriority = -Infinity
  for (const name of Object.keys(settings.states)) {
    const spec = settings.states[name]
    if (!signals.has(spec.when)) continue
    if (best === null || spec.priority > bestPriority || (spec.priority === bestPriority && name < best)) {
      best = name; bestPriority = spec.priority
    }
  }
  return best ?? 'resting'
}

/** The pattern a state renders with. Throws on an unknown state (the caller owns the name). */
export function patternOf(settings: Settings, state: string): PatternSpec {
  const spec = settings.states[state]
  if (!spec) throw new Error(`no such state: ${state}`)
  const pattern = settings.patterns[spec.pattern]
  if (!pattern) throw new Error(`state ${state} points at unknown pattern ${spec.pattern}`)
  return { ...pattern }
}
