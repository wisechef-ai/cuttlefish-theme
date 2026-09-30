// Diagnostic: timestamped log of eval / register / mount / unmount / render for an auto-docked ambient widget.
import fs from 'node:fs'
import path from 'node:path'
export default function register(sdk) {
  const { Text, defineWidgetApp, openWidget, React, h } = sdk
  const log = m => fs.appendFileSync(path.join(process.env.HERMES_HOME, 'lifecycle.log'), `${(performance.now() / 1000).toFixed(2)} ${m}\n`)
  log('module eval / register()')
  const Card = ({ t }) => {
    React.useEffect(() => { log('MOUNT'); return () => log('UNMOUNT') }, [])
    return h(sdk.Dialog, { width: 30 }, h(Text, { color: t.color.label }, 'LIFECYCLE-CARD'))
  }
  const app = defineWidgetApp({ id: 'lc', mode: 'ambient', zone: 'dock-top', init: () => ({}), reduce: s => s, render: ({ t }) => h(Card, { t }) })
  openWidget(app, {})
  log('openWidget() returned')
}
