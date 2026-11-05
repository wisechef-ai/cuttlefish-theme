// ACCEPTANCE CONTRACT — a FAKE browser surface for the plugin under test (locked).
// Models exactly what catalog rule 8 lets a plugin touch: its OWN elements (createElement + head/body append),
// html[data-*] attributes and CSS variables on :root, matchMedia, getComputedStyle of its own element, the window size.
// Any query into the app's markup (querySelector*, getElementsBy*, MutationObserver) THROWS: that is the tripwire.
export const dom = {
  reducedMotion: false,
  ground: 'rgb(20, 20, 22)',
  hidden: false,
  mediaListeners: new Set(),
  created: [],
}

function element(tag) {
  const el = {
    tagName: tag.toUpperCase(), textContent: '', attributes: {}, children: [], parentNode: null, style: styleDecl(),
    setAttribute(k, v) { this.attributes[k] = String(v) },
    getAttribute(k) { return this.attributes[k] ?? null },
    removeAttribute(k) { delete this.attributes[k] },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c },
    removeChild(c) { this.children = this.children.filter(x => x !== c); c.parentNode = null; return c },
    remove() { this.parentNode?.removeChild(this) },
    addEventListener() {}, removeEventListener() {},
    get isConnected() { let p = this.parentNode; while (p) { if (p === documentNode) return true; p = p.parentNode } return false },
  }
  dom.created.push(el)
  return el
}
function styleDecl() {
  const props = {}
  return {
    setProperty(k, v) { props[k] = String(v) },
    removeProperty(k) { delete props[k] },
    getPropertyValue(k) { return props[k] ?? '' },
    get _props() { return { ...props } },
  }
}
const trip = name => () => { throw new Error(`rule 8 tripwire: the plugin called ${name} on the app's DOM`) }

const documentNode = { nodeName: '#document' }
const html = element('html'); html.parentNode = documentNode
const head = element('head'); html.appendChild(head)
const body = element('body'); html.appendChild(body)
dom.created.length = 0

export const document = {
  documentElement: html, head, body,
  get hidden() { return dom.hidden }, get visibilityState() { return dom.hidden ? 'hidden' : 'visible' },
  createElement: tag => element(tag),
  createElementNS: (_ns, tag) => element(tag),
  querySelector: trip('document.querySelector'), querySelectorAll: trip('document.querySelectorAll'),
  getElementById: trip('document.getElementById'), getElementsByClassName: trip('document.getElementsByClassName'),
  getElementsByTagName: trip('document.getElementsByTagName'),
  addEventListener() {}, removeEventListener() {},
}

export const window = {
  document,
  innerWidth: 1200, innerHeight: 800, devicePixelRatio: 1,
  matchMedia(query) {
    const isReduce = /prefers-reduced-motion:\s*reduce/.test(query)
    return {
      media: query,
      get matches() { return isReduce ? dom.reducedMotion : false },
      addEventListener: (_t, fn) => dom.mediaListeners.add(fn),
      removeEventListener: (_t, fn) => dom.mediaListeners.delete(fn),
      addListener: fn => dom.mediaListeners.add(fn), removeListener: fn => dom.mediaListeners.delete(fn),
    }
  },
  getComputedStyle: () => ({
    getPropertyValue: () => dom.ground,
    backgroundColor: dom.ground, color: 'rgb(230, 230, 230)',
  }),
  addEventListener() {}, removeEventListener() {},
  MutationObserver: function () { throw new Error('rule 8 tripwire: MutationObserver') },
  setInterval: trip('window.setInterval (use ctx.setInterval)'), setTimeout: trip('window.setTimeout (use ctx.setTimeout)'),
  requestAnimationFrame: trip('requestAnimationFrame (use createBudgetedLoop)'),
  localStorage: { getItem: trip('localStorage'), setItem: trip('localStorage') },
  eval: trip('eval'),
}

/** Install the fakes as globals for the plugin module. */
export function install() {
  globalThis.window = window
  globalThis.document = document
  globalThis.matchMedia = window.matchMedia
  globalThis.getComputedStyle = window.getComputedStyle
  globalThis.MutationObserver = window.MutationObserver
  globalThis.requestAnimationFrame = window.requestAnimationFrame
  globalThis.localStorage = window.localStorage
}

/** Fire a prefers-reduced-motion change. */
export function setReducedMotion(on) {
  dom.reducedMotion = on
  for (const fn of [...dom.mediaListeners]) fn({ matches: on, media: '(prefers-reduced-motion: reduce)' })
}
