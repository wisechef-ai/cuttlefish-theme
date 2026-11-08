// Dev-only spike: does a READING LANE (organs left of x=lane shrink and fade) keep the locked classifier green?
// node --experimental-strip-types tools/design/field_spike.ts   (nice -n 10)
import { GROUNDS, H, PRESETS, ROOTS, W } from '../../desktop/test/acceptance/corpus.ts'
import { EXPECT, read, reading } from '../../desktop/test/acceptance/language.ts'
import { lightnessStats } from '../../desktop/test/acceptance/instruments.ts'
import { allocate, DEFAULT_SETTINGS, patternOf, renderField } from '../../desktop/src/domain/index.ts'

function run(label: string, shrink: number, fade: number, laneFrac: number) {
  let bad = 0, n = 0
  const margin: Record<string, number> = {}
  for (const root of ROOTS) for (const ground of GROUNDS) for (const p of PRESETS) {
    const dots = renderField({ seed: root, width: W, height: H, hueDeg: allocate(root, []).hue_deg, ground, pattern: patternOf(DEFAULT_SETTINGS, p),
      intensity: 1, motion: 'still', reducedMotion: false, tMs: 4200, sinceChangeMs: 99999 })
    const lane = Math.min(laneFrac * W, 760 * W / 1200)
    const out = dots.map(d => (d.role === 'organ' && d.x < lane ? { ...d, r: d.r * shrink, alpha: d.alpha * fade } : d))
    const got = reading(read(out, ground))
    n++
    if (got !== EXPECT[p]) { bad++; margin[`${p}`] = (margin[`${p}`] ?? 0) + 1 }
    void lightnessStats
  }
  console.log(label, `misreads ${bad}/${n}`, JSON.stringify(margin))
}
run('baseline', 1, 1, 0)
for (const [s, f, l] of [[0.6, 0.6, 0.5], [0.5, 0.5, 0.5], [0.45, 0.35, 0.6], [0.4, 0.3, 0.6]] as const) run(`lane shrink ${s} fade ${f} frac ${l}`, s, f, l)
