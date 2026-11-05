// ACCEPTANCE CONTRACT — the language, written down as a fixed classifier (locked).
// Bands and stripes are read along the four canonical orientations (0/45/90/135°): an implementation must lay its
// clouds and zebra stripes along one of them.
import { H, type Preset, W } from './corpus.ts'
import { banding, type Dot, lightnessStats, meanChroma, spotRatios } from './instruments.ts'

export interface Read { stripes: boolean; clouds: boolean; blanch: boolean; spot: boolean; calm: boolean }

export function read(dots: Dot[], ground: string, width = W, height = H): Read {
  const b = banding(dots, ground, width, height)
  const sp = spotRatios(dots)
  const lit = lightnessStats(dots.filter(d => d.role === 'organ'), ground)
  const stripes = b.highK >= 0.6 && b.highK >= b.lowK
  const clouds = b.lowK >= 0.55 && b.highK <= 0.6 * b.lowK
  const blanch = meanChroma(dots) <= 0.03
  const spot = sp.first >= 4 && sp.second <= 2
  const calm = !stripes && !clouds && !blanch && !spot && lit.p95 <= 0.05
  return { stripes, clouds, blanch, spot, calm }
}

export const EXPECT: Record<Preset, keyof Read> = {
  resting: 'calm', working: 'clouds', needs_you: 'stripes', error: 'blanch', finished_unseen: 'spot',
}

/** The single reading that is on, or a list of what was on when it is not exactly one. */
export function reading(r: Read): string {
  const on = (Object.keys(r) as (keyof Read)[]).filter(k => r[k])
  return on.length === 1 ? on[0] : `[${on.join(',')}]`
}
