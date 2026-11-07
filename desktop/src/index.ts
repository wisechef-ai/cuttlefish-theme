// The shipped plugin entry (A1): one default export — id, name, register — and
// nothing else. register wires the whole skin through the adapters' attach(),
// which owns every side effect and every disposer.
import { attach } from './adapters/runtime.ts'
import type { PluginContext } from '@hermes/plugin-sdk'

const plugin = {
  id: 'cuttlefish-theme',
  name: 'Cuttlefish',
  description: 'Every session wears its state as a skin: a sparse organ field, row swatches, a status strip and a composer rim.',
  register: (ctx: PluginContext): void => attach(ctx),
}

export type CfPlugin = typeof plugin

export default plugin
