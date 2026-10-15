// Identity allocator, contract CONTRACT.md §1. Direction D fixes lightness and chroma, so identity
// is a HUE SLOT only: 20 slots on [110, 340). Pure: no clock, no randomness, no I/O.
import { blake2b, utf8 } from './blake2b.ts';

export const ARC_START = 110;            // degrees, inclusive (tokens.identity.hue_arc_deg)
export const ARC_END = 340;              // exclusive
export const SLOTS = 20;
export const STEP = (ARC_END - ARC_START) / SLOTS;   // 11.5
/** Slot distance beyond which two hues are "far enough": spacing past this is not rewarded. */
export const CAP = 3;

export interface Allocation { slot: number; hue_deg: number; crowded: boolean }

const isSlot = (k: unknown): k is number => Number.isInteger(k) && (k as number) >= 0 && (k as number) < SLOTS;

/** Hue of slot k: 115.75 ... 334.25 (exact in binary64). */
export function hueOfSlot(k: number): number {
  if (!isSlot(k)) throw new RangeError(`slot must be an integer in 0..${SLOTS - 1}, got ${k}`);
  return ARC_START + STEP * (k + 0.5);
}

function requireRoot(root: string): void {
  if (typeof root !== 'string' || root.trim() === '') throw new Error('lineage root is empty: degrade to unbound, never guess an identity');
}

/** Hash-preferred slot: first 8 bytes (big endian) of blake2b-256(utf8(root)) mod 20, in exact integer maths. */
export function preferredSlot(lineageRoot: string): number {
  requireRoot(lineageRoot);
  const d = blake2b(utf8(lineageRoot), 32);
  const hi = ((d[0] << 24) | (d[1] << 16) | (d[2] << 8) | d[3]) >>> 0;
  const lo = ((d[4] << 24) | (d[5] << 16) | (d[6] << 8) | d[7]) >>> 0;
  // (hi * 2^32 + lo) mod 20, with 2^32 mod 20 = 16: every intermediate stays far below 2^53.
  return (((hi % SLOTS) * (4294967296 % SLOTS)) + (lo % SLOTS)) % SLOTS;
}

/**
 * Pick a slot for `lineageRoot` given the slots held by OTHER live sessions of the same profile
 * (duplicates allowed, order irrelevant). Capped farthest-point over the free slots: far enough
 * first, then closest to the hash, then the lowest index. All slots taken: the hash slot repeats and
 * `crowded` is surfaced (the name label carries identity then), never hidden.
 */
export function allocate(lineageRoot: string, peers: readonly number[]): Allocation {
  const pref = preferredSlot(lineageRoot);
  for (const p of peers) if (!isSlot(p)) throw new RangeError(`peer slot must be an integer in 0..${SLOTS - 1}, got ${p}`);
  if (peers.length === 0) return { slot: pref, hue_deg: hueOfSlot(pref), crowded: false };

  const held = new Set(peers);
  let best = -1;
  let bestFar = -1, bestNear = -1;
  for (let k = 0; k < SLOTS; k++) {
    if (held.has(k)) continue;
    let far = CAP;
    for (const p of held) far = Math.min(far, Math.abs(k - p));
    const near = -Math.abs(k - pref);
    // score = (far, near, -k) lexicographic, maximised; ascending k means a tie keeps the lowest index
    if (best < 0 || far > bestFar || (far === bestFar && near > bestNear)) { best = k; bestFar = far; bestNear = near; }
  }
  if (best < 0) return { slot: pref, hue_deg: hueOfSlot(pref), crowded: true };
  return { slot: best, hue_deg: hueOfSlot(best), crowded: false };
}
