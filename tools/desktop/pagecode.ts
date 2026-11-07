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

export interface Geometry { surface: [number, number, number, number] | null; boxes: { x: number; y: number; w: number; h: number }[]; messageBoxes: { x: number; y: number; w: number; h: number }[]; offset: [number, number] }

/** The chat surface and the boxes that are NOT the field: transcript text, approval cards, composer, timeline, buttons. */
export const readGeometry = (): Geometry => {
  const rect = (e: Element) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } }
  const surface = document.querySelector('[data-chat-surface]')
  const sels = [
    '[data-slot="aui_user-message-root"]', '[data-slot="aui_assistant-message-root"]', '[data-slot="tool-approval-stack"]',
    '[data-slot="card-stack"]', '[data-slot="thread-timeline"]', '[data-slot="composer-dock"]', '[data-slot="composer-fade"]',
    '[data-slot="status-drawer-toggle"]', '[data-slot="chat-drop-overlay"]',
  ]
  const boxes = sels.flatMap(s => [...document.querySelectorAll(s)].map(rect))
  for (const b of [...document.querySelectorAll('button')]) if ((b.textContent || '').includes('Scroll to bottom')) boxes.push(rect(b))
  const s = surface ? surface.getBoundingClientRect() : null
  return {
    surface: s ? [Math.round(s.x), Math.round(s.y), Math.round(s.width), Math.round(s.height)] : null,
    boxes,
    messageBoxes: [...document.querySelectorAll('[data-slot="aui_user-message-root"], [data-slot="aui_assistant-message-root"]')].map(rect),
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
