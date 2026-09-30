import fs from 'node:fs'
import path from 'node:path'

export default function register(sdk) {
  const { Box, Text, defineWidgetApp, openWidget, updateWidget, h } = sdk
  const file = path.join(process.env.HERMES_HOME, 'cf-value.json')
  const read = () => { try { return JSON.parse(fs.readFileSync(file, 'utf8')).value } catch (e) { return 'ERR:' + e.code } }

  const app = defineWidgetApp({
    id: 'fsprobe', help: 'spike 01: node:fs read + watch', mode: 'ambient', zone: 'dock-top',
    init: () => ({ v: read(), n: 0 }),
    reduce: s => s,
    render: ({ state, t }) => h(sdk.Dialog, { width: 40 }, h(Text, { color: t.color.label }, `FSVALUE=${state.v} reloads=${state.n}`))
  })
  // watch the DIRECTORY (atomic-rename safe); re-read on any change of the file
  const w = fs.watch(path.dirname(file), (_e, name) => {
    if (name === 'cf-value.json') updateWidget(app, s => ({ v: read(), n: s.n + 1 }))
  })
  w.unref?.()
  openWidget(app, app.init(''))
}
