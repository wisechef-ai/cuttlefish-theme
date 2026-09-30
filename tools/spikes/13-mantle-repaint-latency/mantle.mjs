// Spike 13: 2-row truecolor half-block "mantle", full width. MODE (file $HERMES_HOME/mantle-mode): anim|static|off.
// anim = slow passing cloud at FPS (default 6) — every cell's fg+bg change every frame (worst case for the differ).
import fs from 'node:fs'
import path from 'node:path'

export default function register(sdk) {
  const { Box, Text, defineWidgetApp, openWidget, React, h } = sdk
  const home = process.env.HERMES_HOME
  const mode = () => { try { return fs.readFileSync(path.join(home, 'mantle-mode'), 'utf8').trim() } catch { return 'anim' } }
  const FPS = Number(process.env.CF_FPS || 6)
  const Q = Number(process.env.CF_QUANT || 0)   // >0: quantise each channel to Q-wide buckets so most cells are byte-identical frame to frame
  const hex = (r, g, b) => '#' + [r, g, b].map(v => (Q ? Math.round(v / Q) * Q : v)).map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')
  // 4 sub-rows per 2 terminal rows via ▀ (fg = upper pixel, bg = lower pixel). Hue: teal/violet cuttlefish-ish.
  const px = (x, y, tt) => {
    const cloud = 0.5 + 0.5 * Math.sin(x * 0.13 - tt * 0.9 + Math.sin(y * 1.7 + tt * 0.3) * 1.3)
    return hex(30 + 90 * cloud, 60 + 110 * cloud, 110 + 120 * cloud * (0.6 + 0.4 * Math.sin(x * 0.05 + y)))
  }
  const Mantle = ({ w, m }) => {
    const [frame, setFrame] = React.useState(0)
    React.useEffect(() => {
      if (m !== 'anim') return
      const id = setInterval(() => setFrame(f => f + 1), Math.round(1000 / FPS))
      return () => clearInterval(id)
    }, [m])
    const tt = m === 'anim' ? frame / FPS : 0
    const rows = [0, 1].map(r => h(Box, { key: r, width: w, height: 1 },
      ...Array.from({ length: w }, (_, x) => h(Text, { key: x, color: px(x, r * 2, tt), backgroundColor: px(x, r * 2 + 1, tt) }, '▀'))))
    return h(Box, { flexDirection: 'column', width: w }, ...rows)
  }
  const app = defineWidgetApp({
    id: 'mantle13', help: 'spike 13', mode: 'ambient', zone: 'dock-top', init: () => ({}), reduce: s => s,
    render: ({ cols }) => mode() === 'off' ? h(Text, null, '') : h(Mantle, { w: cols - 2, m: mode() })
  })
  openWidget(app, {})
}
