// Spike 04: a widget with side effects (fs.watch + setInterval). MODE file decides whether it disposes.
import fs from 'node:fs'
import path from 'node:path'

export default function register(sdk) {
  const { Text, defineWidgetApp, openWidget, h } = sdk
  const home = process.env.HERMES_HOME
  const DISPOSE = Symbol.for('cuttlefish.dispose')
  if (fs.existsSync(path.join(home, 'mode-dispose'))) {
    // the candidate fix: previous eval's disposer runs FIRST, at the top of module eval
    try { globalThis[DISPOSE]?.() } catch {}
  }
  const eid = Math.random().toString(36).slice(2, 8)
  // one fs.watch handle per eval; each fires => appends its eid, so live handles are countable from outside
  const watcher = fs.watch(path.join(home, 'watched'), () => fs.appendFileSync(path.join(home, 'watch-fired.log'), eid + '\n'))
  // second watcher on a per-eval-unique path => also visible as a kernel inotify watch descriptor
  fs.mkdirSync(path.join(home, 'uniq-' + eid)); const watcher2 = fs.watch(path.join(home, 'uniq-' + eid), () => {})
  const counter = path.join(home, 'ticks.log')
  const timer = setInterval(() => fs.appendFileSync(counter, eid + '\n'), 200)   // one live timer per eval
  // NOTE: deliberately NOT unref'd for the timer? host unrefs its own; we mimic a naive widget author.
  globalThis[DISPOSE] = () => { watcher.close(); watcher2.close(); clearInterval(timer); globalThis[DISPOSE] = undefined }
  const app = defineWidgetApp({
    id: 'leaky', help: 'spike 04', mode: 'ambient', zone: 'dock-top', init: () => ({}), reduce: s => s,
    render: ({ t }) => h(sdk.Dialog, { width: 20 }, h(Text, { color: t.color.label }, 'LEAKY ' + eid))
  })
  openWidget(app, {})
}
