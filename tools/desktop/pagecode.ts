/**
 * Functions that run INSIDE the Desktop renderer (Playwright serialises them with toString, so each one is
 * self-contained: no imports, no closures). Dev only. They read the DOM the way a user's screen shows it; they never
 * write to it. The harness may query core's markup: the "no [data-slot] / querySelector" rule binds the plugin, not this.
 */

export interface RowInfo { title: string; 'data-cf-session': string | null; 'data-cf-state': string | null; swatch_circles: number }

/** Every sidebar session row, in DOM order, with its swatch (null / 0 when the row has none). */
export const readRows = (): RowInfo[] =>
  [...document.querySelectorAll('[data-sessions-mode] [data-slot="context-menu-trigger"]')].map(row => {
    const sw = row.querySelector('[data-cf-session]')
    return {
      title: ((row as HTMLElement).innerText || '').split('\n')[0].trim(),
      'data-cf-session': sw ? sw.getAttribute('data-cf-session') : null,
      'data-cf-state': sw ? sw.getAttribute('data-cf-state') : null,
      swatch_circles: sw ? sw.querySelectorAll('circle').length : 0,
    }
  })

/** The data-cf-* attributes of <html>. */
export const readHtmlAttrs = (): Record<string, string> => {
  const out: Record<string, string> = {}
  for (const a of [...document.documentElement.attributes]) if (a.name.startsWith('data-cf-')) out[a.name] = a.value
  return out
}

/** sha256 of the plugin's owned <style> text ('' hashed when the plugin is off). */
export const cssHash = async (): Promise<string> => {
  const el = [...document.querySelectorAll('style')].find(s => (s.textContent || '').includes('--cf-ground'))
  const text = el ? el.textContent || '' : ''
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map(b => b.toString(16).padStart(2, '0')).join('')
}

export interface Box { x: number; y: number; w: number; h: number }
export interface Geometry { surface: [number, number, number, number] | null; composerTop: number | null; boxes: Box[]; messages: Box[][]; offset: [number, number]; sidebar: Box[] }

/**
 * The chat surface and what on it is NOT the field. Transcript text is excluded as tightly as the text itself: one box per
 * text line (Range rects) plus every painted element (background, border, shadow, image, control) inside a message / approval card,
 * so a wide message root does not swallow the field around a short line. `messages` keeps the parts per message root.
 */
export const readGeometry = (): Geometry => {
  const rect = (r: DOMRect | DOMRectReadOnly) => ({ x: r.x, y: r.y, w: r.width, h: r.height })
  const partsOf = (root: Element): Box[] => {
    const out: Box[] = []
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT)
    for (let n: Node | null = walker.currentNode; n; n = walker.nextNode()) {
      if (n.nodeType === 3) {
        if (!(n.textContent || '').trim()) continue
        const range = document.createRange()
        range.selectNodeContents(n)
        for (const r of range.getClientRects()) out.push(rect(r))
        continue
      }
      const e = n as Element
      const cs = getComputedStyle(e)
      const paintedBg = cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent'
      const paintedBorder = ['Top', 'Right', 'Bottom', 'Left'].some(s => parseFloat(cs.getPropertyValue(`border-${s.toLowerCase()}-width`)) > 0 && cs.getPropertyValue(`border-${s.toLowerCase()}-style`) !== 'none')
      const replaced = ['IMG', 'svg', 'SVG', 'CANVAS', 'VIDEO', 'BUTTON', 'INPUT'].includes(e.tagName)
      if (paintedBg || paintedBorder || replaced || cs.backgroundImage !== 'none' || cs.boxShadow !== 'none') out.push(rect(e.getBoundingClientRect()))
    }
    return out
  }
  const messages = [...document.querySelectorAll('[data-slot="aui_user-message-root"], [data-slot="aui_assistant-message-root"]')].map(partsOf)
  const others = ['[data-slot="tool-approval-stack"]', '[data-slot="thread-timeline"]', '[data-slot="status-drawer-toggle"]']
    .flatMap(s => [...document.querySelectorAll(s)].flatMap(partsOf))
  for (const b of [...document.querySelectorAll('button')]) if ((b.textContent || '').includes('Scroll to bottom')) others.push(rect(b.getBoundingClientRect()))
  const s = document.querySelector('[data-chat-surface]')
  const dock = document.querySelector('[data-slot="composer-dock"]')
  const sr = s ? s.getBoundingClientRect() : null
  // every sidebar row's box (window coordinates): the sidebar crops are cut from these
  const sidebar = [...document.querySelectorAll('[data-sessions-mode] [data-slot="context-menu-trigger"]')].map(r => rect(r.getBoundingClientRect()))
  return {
    sidebar,
    surface: sr ? [Math.round(sr.x), Math.round(sr.y), Math.round(sr.width), Math.round(sr.height)] : null,
    composerTop: dock ? Math.floor(dock.getBoundingClientRect().y) : null,
    boxes: [...messages.flat(), ...others],
    messages,
    // the window's offset on the screen: x11grab pixel = client pixel + this (frameless window, no WM: expected [0, 0])
    offset: [window.screenX + (window.outerWidth - window.innerWidth), window.screenY + (window.outerHeight - window.innerHeight)],
  }
}

/** The status strip's words, the composer rim's root + svg hash, the identity ring variable. */
export const readChrome = async (): Promise<{ strip: string; rim: { 'data-cf-state': string; svg_sha256: string } | null; ring: string }> => {
  const strip = document.querySelector('[data-cf-strip]')
  const rim = document.querySelector('[data-cf-rim]')
  const svg = rim ? rim.querySelector('svg') : null
  const surface = document.querySelector('[data-chat-surface]')
  const h = async (t: string) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(t)))].map(b => b.toString(16).padStart(2, '0')).join('')
  return {
    strip: strip ? (strip.textContent || '').trim() : '',
    rim: rim && svg ? { 'data-cf-state': rim.getAttribute('data-cf-state') || '', svg_sha256: await h(new XMLSerializer().serializeToString(svg)) } : null,
    ring: surface ? getComputedStyle(surface).getPropertyValue('--dt-composer-ring').trim() : '',
  }
}

/** Open the Capabilities ▸ Plugins card of the plugin and set its switch; resolves the switch state afterwards. */
export const switchState = (): string | null => {
  const sw = document.querySelector('[role="switch"][aria-label="Cuttlefish"]')
  return sw ? sw.getAttribute('aria-checked') : null
}

/** The status strip's DOM box, the viewport, and whether any element in it scrolls wider than its box (its text is cut). */
export const readStrip = (): { box: Box | null; viewport: { w: number; h: number }; truncated: boolean; textOverflow: string } => {
  const viewport = { w: window.innerWidth, h: window.innerHeight }
  const el = document.querySelector('[data-cf-strip]') as HTMLElement | null
  if (!el) return { box: null, viewport, truncated: false, textOverflow: '' }
  const r = el.getBoundingClientRect()
  const els = [el, ...Array.from(el.querySelectorAll('*'))] as HTMLElement[]
  const truncated = els.some(e => e.scrollWidth > e.clientWidth)
  const kinds = [...new Set(els.map(e => getComputedStyle(e).textOverflow))].sort()
  return { box: { x: r.x, y: r.y, w: r.width, h: r.height }, viewport, truncated, textOverflow: kinds.join(',') }
}
