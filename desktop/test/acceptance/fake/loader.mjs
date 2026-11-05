// ACCEPTANCE CONTRACT — resolve the three specifiers a disk plugin may import to the fakes (locked).
// Any other bare specifier fails, exactly like the real loader's import allowlist.
const here = new URL('./', import.meta.url)
const MAP = {
  '@hermes/plugin-sdk': new URL('sdk.mjs', here).href,
  react: new URL('react.mjs', here).href,
  'react/jsx-runtime': new URL('react.mjs', here).href,
}
export async function resolve(specifier, context, next) {
  if (specifier in MAP) return { url: MAP[specifier], shortCircuit: true }
  const fromPlugin = context.parentURL && /\/desktop\/plugin\.js(\?|$)/.test(context.parentURL)
  if (fromPlugin && !specifier.startsWith('.') && !specifier.startsWith('/') && !specifier.startsWith('file:')) {
    throw new Error(`unsupported import "${specifier}" (a disk plugin may import only @hermes/plugin-sdk, react, react/jsx-runtime)`)
  }
  if (fromPlugin) throw new Error(`unsupported import "${specifier}" (the shipped plugin.js must be ONE self-contained file)`)
  return next(specifier, context)
}
