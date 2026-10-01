#!/usr/bin/env node
// DEV PREVIEW ONLY. This is NOT gate evidence (premortem #1: only real-host captures count).
// It rasterises a direction's paint() output to PNG so a direction lane can iterate before the
// real-host harness (lane H) lands. Nearest-neighbour upscale to the true cell aspect: a TUI half
// rung pixel is 10×11 screen px, a bg rung pixel is 10×22.
//
// usage: node tools/p1/preview.mjs design/directions/<id> out.png [--rung half|bg] [--cols 120]
import { writeFileSync, readFileSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import { resolve, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const [dirArg, outArg] = args;
if (!dirArg || !outArg) { console.error('usage: preview.mjs <direction-dir> <out.png> [--rung half|bg] [--cols N]'); process.exit(1); }
const rung = opt('--rung', 'half');
const cols = Number(opt('--cols', '120'));
const dir = await import(pathToFileURL(resolve(dirArg, 'direction.mjs')).href);
const fx = JSON.parse(readFileSync(resolve(here, 'stub-sessions.json'), 'utf8'));

const crcT = new Uint32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
const crc = b => { let c = 0xffffffff; for (const x of b) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
function png(w, h, rgba) {
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 4 + 1)] = 0; Buffer.from(rgba.buffer, rgba.byteOffset + y * w * 4, w * 4).copy(raw, y * (w * 4 + 1) + 1); }
  const ih = Buffer.alloc(13); ih.writeUInt32BE(w, 0); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 6;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ih), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

// Layout: one M strip per state (+ degraded), stacked, each with a gap.
const rows = [...fx.states.map(s => [s, fx.sessions.find(x => x.state === s)]), ['unknown', fx.degraded]];
const pw = cols - 2, ph = rung === 'half' ? 4 : 2, sx = 10, sy = rung === 'half' ? 11 : 22, gap = 12;
const W = pw * sx, H = rows.length * (ph * sy + gap);
const out = new Uint8ClampedArray(W * H * 4);
rows.forEach(([state, session], r) => {
  const { pixels } = dir.paint({ scale: 'M', w: pw, h: ph, state, session, t: 0, opts: { reducedMotion: false, depth: 'truecolor' } });
  for (let y = 0; y < ph * sy; y++) for (let x = 0; x < W; x++) {
    const si = ((Math.floor(y / sy)) * pw + Math.floor(x / sx)) * 4, di = ((r * (ph * sy + gap) + y) * W + x) * 4;
    out[di] = pixels[si]; out[di + 1] = pixels[si + 1]; out[di + 2] = pixels[si + 2]; out[di + 3] = 255;
  }
});
writeFileSync(outArg, png(W, H, out));
console.log(`preview (NOT gate evidence) → ${outArg} ${W}x${H} rung=${rung} rows=${rows.map(r => r[0]).join(',')}`);
