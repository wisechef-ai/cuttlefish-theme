// cf2909 spike 12 test widget: a STATIC 2-row mantle docked at `dock-top`.
//
// Why it looks like this (so the spike-12 matrix cells are comparable):
// - Static and deterministic: no timers, no randomness. The same terminal size gives the same
//   bytes, so any pixel difference between cells is the terminal's doing, not the widget's.
// - Colour-depth invariant. Every colour is one that the TUI's own 256-colour downsample
//   (chalk rgbToAnsi256: greys -> 232+round((v-8)/247*24), else 16+36*round(r/51)+...)
//   maps to an xterm palette entry with the SAME rgb:
//     * greys 8+10k for k = 0..17 (8, 18, ..., 178) -> the grey ramp, exactly;
//     * channels restricted to {0, 255} -> the corners of the 6x6x6 cube, exactly.
//   So a truecolor terminal (38;2;r;g;b) and a COLORTERM-less one (38;5;n) paint identical rgb.
//   (xterm cube levels like 95 do NOT round-trip: chalk sends 95 as level 2 = 135.)
// - Half blocks (▀: fg = upper pixel, bg = lower pixel) give 4 pixel rows in 2 terminal rows.
// - Width is ctx.cols - 2 (AmbientDock has paddingRight=2; see spike 02).
// - Horizontal runs of identical (fg, bg) are merged into one <Text> (spike 13: node count).
// - Auto-docks at load, so a capture needs no keystrokes.
export default function register(sdk) {
  const { Box, Text, defineWidgetApp, openWidget, h } = sdk

  const grey = k => { const v = (8 + 10 * k).toString(16).padStart(2, '0'); return `#${v}${v}${v}` }
  const ACCENTS = ['#00ffff', '#0000ff', '#ff00ff']
  // Pixel (x, y) in a 4-pixel-high band. A slow grey swell (k 1..12) with a sparse accent
  // "chromatophore" every 11 columns, offset per pixel row so the half-block split is visible.
  const pixel = (x, y) => {
    if ((x + 3 * y) % 11 === 0) return ACCENTS[((x / 11) | 0) % ACCENTS.length]
    const phase = (x + 2 * y) % 24
    return grey(1 + (phase < 12 ? phase : 23 - phase))
  }

  const row = (r, w) => {
    const runs = []
    for (let x = 0; x < w; x++) {
      const f = pixel(x, r * 2), b = pixel(x, r * 2 + 1)
      const last = runs[runs.length - 1]
      if (last && last.f === f && last.b === b) last.n++
      else runs.push({ f, b, n: 1 })
    }
    return h(Box, { key: r, width: w, height: 1 },
      ...runs.map((u, i) => h(Text, { key: i, color: u.f, backgroundColor: u.b }, '▀'.repeat(u.n))))
  }

  const app = defineWidgetApp({
    id: 'cfmantle',
    help: 'cf2909 spike 12: static 2-row test mantle',
    mode: 'ambient',
    zone: 'dock-top',
    init: () => ({}),
    reduce: s => s,
    render: ({ cols }) => {
      const w = Math.max(1, cols - 2)
      return h(Box, { flexDirection: 'column', width: w }, row(0, w), row(1, w))
    }
  })
  openWidget(app, app.init(''))
}
