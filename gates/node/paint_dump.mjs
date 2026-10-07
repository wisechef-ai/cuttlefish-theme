// Gate helper: runs a direction module (pure ESM, no imports) and dumps what the Python gates need.
//   stdin : {"direction_dir": "...", "fixture": "/abs/stub-sessions.json", "authored": true,
//            "requests": [{scale,w,h,state,session_idx|null,degraded,t,depth,pixels:bool}]}
//   stdout: {"meta": {...}, "authored_pairs": [...]|null, "results": [{"text": [...], "pixels_b64"?: "..."}]}
// Only the direction + the public stub fixture are read. Nothing else leaves the machine.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const req = JSON.parse(readFileSync(0, 'utf8'));
const mod = await import(pathToFileURL(resolve(req.direction_dir, 'direction.mjs')).href);
const fx = JSON.parse(readFileSync(req.fixture, 'utf8'));
const out = { meta: mod.meta ?? null, authored_pairs: null, results: [] };
if (req.authored) out.authored_pairs = typeof mod.authoredPairs === 'function' ? mod.authoredPairs() : [];
for (const r of req.requests || []) {
  const session = r.degraded ? fx.degraded : fx.sessions[r.session_idx];
  const res = mod.paint({ scale: r.scale, w: r.w, h: r.h, state: r.state, session, t: r.t, opts: { reducedMotion: false, depth: r.depth || 'truecolor' } });
  const item = { text: res.text || [] };
  if (r.pixels) item.pixels_b64 = Buffer.from(res.pixels.buffer, res.pixels.byteOffset, res.pixels.byteLength).toString('base64');
  out.results.push(item);
}
process.stdout.write(JSON.stringify(out));
