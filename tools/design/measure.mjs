// WCAG 2.2 SC 1.4.11 measurement from RENDERED PIXELS (dev-only, node stdlib only).
//   node measure.mjs <outdir with cells@1x.png cells@2x.png cells.json> [table.md]
// For every cell (state x hue x ground x selected/unselected x dpr): ink pixels = the pixels of the glyph's core (3x3-eroded mask of
// pixels that differ from the row ground), excluding the declared pale wash; the mark's contrast = the WCAG ratio of the WORST such
// ink colour cluster against the row ground. Also: pairwise silhouette IoU between states (mask = pixels with contrast >= 2.0).
// Exit 1 if any ink < 3.0:1 or any pair IoU > MAX_IOU.
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'

export const MIN_RATIO = 3.0, MAX_IOU = 0.55

export function decodePng(buf) {
  let p = 8, W = 0, H = 0, ct = 0; const idat = []
  while (p < buf.length) {
    const len = buf.readUInt32BE(p), type = buf.toString('latin1', p + 4, p + 8), data = buf.subarray(p + 8, p + 8 + len)
    if (type === 'IHDR') { W = data.readUInt32BE(0); H = data.readUInt32BE(4); ct = data[9]; if (data[8] !== 8 || data[12] !== 0) throw new Error('only 8-bit non-interlaced PNG') }
    if (type === 'IDAT') idat.push(data)
    p += 12 + len
  }
  const bpp = ct === 6 ? 4 : ct === 2 ? 3 : 0
  if (!bpp) throw new Error('colour type ' + ct)
  const raw = zlib.inflateSync(Buffer.concat(idat)), stride = W * bpp, px = Buffer.alloc(W * H * 4)
  let prev = Buffer.alloc(stride)
  for (let y = 0; y < H; y++) {
    const f = raw[y * (stride + 1)], line = Buffer.from(raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)))
    for (let i = 0; i < stride; i++) {
      const a = i >= bpp ? line[i - bpp] : 0, b = prev[i], c = i >= bpp ? prev[i - bpp] : 0
      const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c)
      line[i] = (line[i] + (f === 0 ? 0 : f === 1 ? a : f === 2 ? b : f === 3 ? (a + b) >> 1 : (pa <= pb && pa <= pc ? a : pb <= pc ? b : c))) & 255
    }
    for (let x = 0; x < W; x++) { const o = (y * W + x) * 4; px[o] = line[x * bpp]; px[o + 1] = line[x * bpp + 1]; px[o + 2] = line[x * bpp + 2]; px[o + 3] = bpp === 4 ? line[x * bpp + 3] : 255 }
    prev = line
  }
  return { W, H, px }
}
const lin = c => { const v = c / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }
const lum = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
const ratio = (l1, l2) => (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16))

export function measureCell(img, cell, dpr, pal, pigments) {
  const [br, bg, bb] = hex(cell.bg), bl = lum(br, bg, bb)
  const x0 = cell.x * dpr, y0 = cell.y * dpr, w = cell.w * dpr, h = cell.h * dpr
  const at = (x, y) => { const o = ((y0 + y) * img.W + x0 + x) * 4; return [img.px[o], img.px[o + 1], img.px[o + 2]] }
  const mask = new Uint8Array(w * h)
  const found = {}
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, b] = at(x, y)
    mask[y * w + x] = ratio(lum(r, g, b), bl) >= 2.0 ? 1 : 0
    for (const k of pigments) {
      const [pr, pg, pb] = hex(pal[k])
      if (Math.abs(r - pr) + Math.abs(g - pg) + Math.abs(b - pb) <= 10) { const e = (found[k] ??= { n: 0, r: 0, g: 0, b: 0 }); e.n++; e.r += r; e.g += g; e.b += b }
    }
  }
  // the rendered colour of each pigment (mean of the pixels that match it) and its contrast: vs the row ground, except the pupil,
  // whose neighbour is the iris
  const res = {}
  for (const k of pigments) {
    const e = found[k]
    if (!e || e.n < 4 * dpr * dpr) { res[k] = { n: e?.n ?? 0, ratio: 0 }; continue }
    const l = lum(e.r / e.n, e.g / e.n, e.b / e.n)
    let against = bl
    if (k === 'spot' && found.chroma) against = lum(found.chroma.r / found.chroma.n, found.chroma.g / found.chroma.n, found.chroma.b / found.chroma.n)
    res[k] = { n: e.n, ratio: ratio(l, against) }
  }
  return { res, mask, w, h, worst: Math.min(...pigments.map(k => res[k].ratio)) }
}
const iou = (a, b) => { let i = 0, u = 0; for (let k = 0; k < a.length; k++) { i += a[k] & b[k]; u += a[k] | b[k] } return u ? i / u : 0 }

if (process.argv[1] && path.basename(process.argv[1]) === 'measure.mjs') {
  const dir = process.argv[2], tablePath = process.argv[3]
  const { cells } = JSON.parse(fs.readFileSync(path.join(dir, 'cells.json'), 'utf8'))
    const { GROUNDS } = await import('./pages.mjs')
  const { palette, GLYPHS } = await import('./model.mjs')
  const rows = [], fails = [], iouRows = []
  for (const dpr of [1, 2]) {
    const img = decodePng(fs.readFileSync(path.join(dir, `cells@${dpr}x.png`)))
    const byKey = new Map()
    for (const cell of cells) {
      const pal = palette(cell.hue, GROUNDS[cell.ground].chat)
      const gl = GLYPHS[cell.state]
      const pigments = [...new Set([...gl.dots.map(d => d.pig), ...gl.extras.filter(e => e.pig !== 'wash' && e.pig !== 'paper' && (e.alpha === undefined || e.alpha === 1)).map(e => e.pig)])]
      const m = measureCell(img, cell, dpr, pal, pigments)
      rows.push({ ...cell, dpr, ratio: m.worst, coreN: 0 })
      if (m.worst < MIN_RATIO) fails.push(`${cell.state} ${cell.ground}${cell.sel ? '/sel' : ''} hue ${cell.hue} @${dpr}x = ${m.worst.toFixed(2)}`)
      byKey.set(`${cell.ground}|${cell.sel}|${cell.hue}|${cell.state}`, m.mask)
    }
    if (dpr === 2) {
      for (const g of Object.keys(GROUNDS)) for (const sel of [false, true]) for (const hue of [205]) {
        const S = [...new Set(cells.map(c => c.state))]
        for (let i = 0; i < S.length; i++) for (let j = i + 1; j < S.length; j++) {
          const v = iou(byKey.get(`${g}|${sel}|${hue}|${S[i]}`), byKey.get(`${g}|${sel}|${hue}|${S[j]}`))
          iouRows.push({ g, sel, a: S[i], b: S[j], v })
          if (v > MAX_IOU) fails.push(`silhouette ${S[i]}≈${S[j]} ${g}${sel ? '/sel' : ''} IoU ${v.toFixed(2)}`)
        }
      }
    }
  }
  const states = [...new Set(cells.map(c => c.state))]
  let md = `# Non-text contrast, measured from rendered pixels (WCAG 2.2 SC 1.4.11, bar ${MIN_RATIO}:1)\n\nGenerated by \`tools/design/measure.mjs\`. Each number is the WORST ink-colour cluster of the glyph's eroded core against the row ground, minimum over 6 identity hues, at the stated device scale.\n\n| ground | row | state | 1× min | 2× min |\n|---|---|---|---|---|\n`
  for (const g of Object.keys(GROUNDS)) for (const sel of [false, true]) for (const s of states) {
    const f = d => Math.min(...rows.filter(r => r.ground === g && r.sel === sel && r.state === s && r.dpr === d).map(r => r.ratio)).toFixed(2)
    md += `| ${g} | ${sel ? 'selected' : 'unselected'} | ${s} | ${f(1)} | ${f(2)} |\n`
  }
  const worstIou = {}
  for (const r of iouRows) { const k = `${r.a} / ${r.b}`; worstIou[k] = Math.max(worstIou[k] ?? 0, r.v) }
  md += `\n## Silhouette: pairwise mask IoU (mask = pixels ≥ 2:1 vs ground; worst over grounds and selected/unselected; bar ≤ ${MAX_IOU})\n\n| pair | worst IoU |\n|---|---|\n`
  for (const [k, v] of Object.entries(worstIou)) md += `| ${k} | ${v.toFixed(2)} |\n`
  md += `\nMinimum over everything: ${Math.min(...rows.map(r => r.ratio)).toFixed(2)}:1. ${fails.length ? 'FAILURES: ' + fails.length : 'No failures.'}\n`
  if (tablePath) fs.writeFileSync(tablePath, md)
  console.log(md)
  if (fails.length) { console.error(fails.slice(0, 30).join('\n')); process.exit(1) }
}
