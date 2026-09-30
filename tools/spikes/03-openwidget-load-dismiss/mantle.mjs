// Spike 03: auto-dock at module load + persisted dismissal.
// State file is widget-owned: $HERMES_HOME/plugins/cuttlefish/state.json
import fs from 'node:fs'
import path from 'node:path'

export default function register(sdk) {
  const { Text, defineWidgetApp, openWidget, React, h } = sdk
  const dir = path.join(process.env.HERMES_HOME, 'plugins', 'cuttlefish')
  const file = path.join(dir, 'state.json')
  const load = () => { try { return JSON.parse(fs.readFileSync(file, 'utf8')) } catch { return {} } }
  const save = patch => { fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(file, JSON.stringify({ ...load(), ...patch })) }
  const G = globalThis[Symbol.for('cf.spike03')] ??= { teardown: false }
  G.teardown = false   // this eval is live

  // Card: its UNMOUNT is the only signal the host gives us that the user toggled the dock away.
  const Card = ({ label, t }) => {
    React.useEffect(() => () => {
      // Unmount also fires on process exit and on hot reload. Defer: a dismissal is an unmount that the
      // process SURVIVES (timer unref'd => never fires if the process is exiting) and that isn't a re-dock.
      if (process.env.CF_SPIKE_EAGER) return save({ mantle: 'dismissed-by-unmount' })
      const tm = setTimeout(() => { if (!G.teardown && !G.mounted) save({ mantle: 'dismissed-by-unmount' }) }, 400)
      tm.unref?.()
    }, [])
    React.useEffect(() => { G.mounted = (G.mounted || 0) + 1; return () => { G.mounted-- } }, [])
    return h(sdk.Dialog, { width: 30 }, h(Text, { color: t.color.label }, label))
  }

  const app = defineWidgetApp({
    id: 'mantle', help: 'spike 03: toggle mantle; `/mantle off|on` persists', mode: 'ambient', zone: 'dock-top',
    usage: 'mantle: saved',
    init: arg => {
      const a = arg.trim()
      if (a === 'off') { save({ mantle: 'off' }); return null }      // null => host prints usage; nothing docked
      save({ mantle: 'on' })                                            // any (re)launch = re-enable
      return { label: 'MANTLE-DOCKED' }
    },
    reduce: s => s,
    render: ({ state, t }) => h(Card, { label: state.label, t })
  })
  if (load().mantle !== 'off' && load().mantle !== 'dismissed-by-unmount') openWidget(app, { label: 'MANTLE-DOCKED' })
}
