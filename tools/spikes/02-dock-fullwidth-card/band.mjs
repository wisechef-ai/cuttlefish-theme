// Spike 02: full-width dock-top card. Width = ctx.cols - 2 (AmbientDock paddingRight=2). Rows via BAND_ROWS file.
import fs from 'node:fs'
import path from 'node:path'

export default function register(sdk) {
  const { Box, Text, defineWidgetApp, openWidget, h } = sdk
  const rowsFile = path.join(process.env.HERMES_HOME, 'band-rows')
  const rows = () => { try { return Math.max(1, Math.min(2, parseInt(fs.readFileSync(rowsFile, 'utf8'), 10) || 2)) } catch { return 2 } }
  const app = defineWidgetApp({
    id: 'band', help: 'spike 02: full-width band', mode: 'ambient', zone: 'dock-top',
    init: () => ({}), reduce: s => s,
    render: ({ cols }) => {
      const w = cols - 2, n = rows()
      const line = (i) => {
        // gradient of truecolor half-blocks: colour varies with x so we can prove every column painted
        const cells = []
        for (let x = 0; x < w; x++) {
          const r = Math.round(255 * x / Math.max(1, w - 1)), b = 255 - r
          cells.push(h(Text, { key: x, color: `#${r.toString(16).padStart(2, '0')}80${b.toString(16).padStart(2, '0')}` }, i === 0 ? '█' : '▄'))
        }
        return h(Box, { key: i, width: w, height: 1 }, ...cells)
      }
      return h(Box, { flexDirection: 'column', width: w }, ...Array.from({ length: n }, (_, i) => line(i)))
    }
  })
  openWidget(app, app.init(''))
}
