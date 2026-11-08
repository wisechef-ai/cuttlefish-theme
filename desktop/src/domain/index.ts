// The cuttlefish desktop domain's one public door (contract/README.md "API the domain must export").
// Everything the adapter lane may use is re-exported here, and nothing under desktop/src/domain
// is reachable except through it (test_S2). The domain is PURE: no SDK, no DOM, no clock, no
// randomness — time arrives as tMs/nowMs, entropy only from seeded blake2b.
export {
  blake2b, seededStream, utf8,
} from './blake2b.ts'
export {
  allocate, ARC_END, ARC_START, hueDistance, hueOfSlot, preferredSlot, SLOTS, type Allocation,
} from './identity.ts'
export {
  blanchDl, CLOUD_TRAVEL_MS, hashUnit, inkTargets, MAX_DL, planGround, REST_HI, REST_LO, REST_MEAN,
  twinkleFactor, type GroundPlan, type InkOptions,
} from './pattern.ts'
export {
  alphaFor, renderField, renderStrip, renderSwatch, toSvg,
} from './field.ts'
export { constellation, eyeSpotAt, type Constellation, type Organ } from './organs.ts'
export {
  BLOOM_MS, bloomFactor, motionPlan,
} from './motion.ts'
export {
  DEFAULT_SETTINGS, patternOf, resolveSettings, stateFor,
} from './settings.ts'
export {
  initialFeed, knownSessions, POLL_INTERVAL_MS, pollPlan, reduceFeed, signalsOf,
  type FeedInput, type FeedModel, type SessionRec,
} from './feed.ts'
export {
  configPlan, initialConfigWatch, type ConfigWatch,
} from './configwatch.ts'
export {
  hexToRgb, oklchToHex, rgbToHex, rgbToOklab, type Lab, type Lch, type Rgb,
} from './oklch.ts'
export type {
  Dot, FieldInput, Motion, PatternKind, PatternSpec, Settings, Signal, StateSpec, SwatchInput, Warning,
} from './types.ts'
export { PATTERN_KINDS, SIGNALS } from './types.ts'
