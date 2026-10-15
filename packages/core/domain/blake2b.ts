// Pure, dependency-free BLAKE2b (RFC 7693), variable digest length 1..64, unkeyed.
// The desktop renderer has no node:crypto, so the identity hash lives here. 64-bit words are
// held as (hi, lo) uint32 pairs: no BigInt, no float arithmetic on the hot path.

const IV_HI = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
const IV_LO = [0xf3bcc908, 0x84caa73b, 0xfe94f82b, 0x5f1d36f1, 0xade682d1, 0x2b3e6c1f, 0xfb41bd6b, 0x137e2179];

const SIGMA = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
  [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
  [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
  [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
  [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
  [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
  [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
  [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
  [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
];

/** UTF-8 bytes of a string (the identity hash input). */
export function utf8(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

// Working state: v[0..15] as hi/lo, message m[0..15] as hi/lo.
const vh = new Uint32Array(16), vl = new Uint32Array(16), mh = new Uint32Array(16), ml = new Uint32Array(16);

function G(a: number, b: number, c: number, d: number, xh: number, xl: number, yh: number, yl: number): void {
  let lo: number, hi: number;
  // v[a] = v[a] + v[b] + x
  lo = (vl[a] + vl[b]) >>> 0; hi = (vh[a] + vh[b] + (lo < vl[a] ? 1 : 0)) >>> 0;
  let lo2 = (lo + xl) >>> 0; hi = (hi + xh + (lo2 < lo ? 1 : 0)) >>> 0; vl[a] = lo2; vh[a] = hi;
  // v[d] = rotr64(v[d] ^ v[a], 32)
  let th = vh[d] ^ vh[a], tl = vl[d] ^ vl[a]; vh[d] = tl; vl[d] = th;
  // v[c] = v[c] + v[d]
  lo = (vl[c] + vl[d]) >>> 0; hi = (vh[c] + vh[d] + (lo < vl[c] ? 1 : 0)) >>> 0; vl[c] = lo; vh[c] = hi;
  // v[b] = rotr64(v[b] ^ v[c], 24)
  th = vh[b] ^ vh[c]; tl = vl[b] ^ vl[c];
  vh[b] = ((th >>> 24) | (tl << 8)) >>> 0; vl[b] = ((tl >>> 24) | (th << 8)) >>> 0;
  // v[a] = v[a] + v[b] + y
  lo = (vl[a] + vl[b]) >>> 0; hi = (vh[a] + vh[b] + (lo < vl[a] ? 1 : 0)) >>> 0;
  lo2 = (lo + yl) >>> 0; hi = (hi + yh + (lo2 < lo ? 1 : 0)) >>> 0; vl[a] = lo2; vh[a] = hi;
  // v[d] = rotr64(v[d] ^ v[a], 16)
  th = vh[d] ^ vh[a]; tl = vl[d] ^ vl[a];
  vh[d] = ((th >>> 16) | (tl << 16)) >>> 0; vl[d] = ((tl >>> 16) | (th << 16)) >>> 0;
  // v[c] = v[c] + v[d]
  lo = (vl[c] + vl[d]) >>> 0; hi = (vh[c] + vh[d] + (lo < vl[c] ? 1 : 0)) >>> 0; vl[c] = lo; vh[c] = hi;
  // v[b] = rotr64(v[b] ^ v[c], 63)  == rotl64(.., 1)
  th = vh[b] ^ vh[c]; tl = vl[b] ^ vl[c];
  vh[b] = ((th << 1) | (tl >>> 31)) >>> 0; vl[b] = ((tl << 1) | (th >>> 31)) >>> 0;
}

/** BLAKE2b of `input` with a `digestSize`-byte output (1..64). Returns a fresh Uint8Array. */
export function blake2b(input: Uint8Array, digestSize = 32): Uint8Array {
  if (!Number.isInteger(digestSize) || digestSize < 1 || digestSize > 64) throw new RangeError('blake2b digestSize must be 1..64');
  const hh = new Uint32Array(IV_HI), hl = new Uint32Array(IV_LO);
  hl[0] ^= 0x01010000 ^ digestSize;   // param block: digest length, key length 0, fanout 1, depth 1

  const block = new Uint8Array(128);
  let t = 0;                           // total bytes compressed so far (inputs here are far below 2^53)
  const compress = (last: boolean, bytesSoFar: number): void => {
    for (let i = 0; i < 16; i++) {
      const o = i * 8;
      ml[i] = (block[o] | (block[o + 1] << 8) | (block[o + 2] << 16) | (block[o + 3] << 24)) >>> 0;
      mh[i] = (block[o + 4] | (block[o + 5] << 8) | (block[o + 6] << 16) | (block[o + 7] << 24)) >>> 0;
    }
    for (let i = 0; i < 8; i++) { vh[i] = hh[i]; vl[i] = hl[i]; vh[i + 8] = IV_HI[i]; vl[i + 8] = IV_LO[i]; }
    vl[12] ^= bytesSoFar >>> 0; vh[12] ^= Math.floor(bytesSoFar / 4294967296) >>> 0;
    if (last) { vh[14] = ~vh[14] >>> 0; vl[14] = ~vl[14] >>> 0; }
    for (let r = 0; r < 12; r++) {
      const s = SIGMA[r % 10];
      G(0, 4, 8, 12, mh[s[0]], ml[s[0]], mh[s[1]], ml[s[1]]);
      G(1, 5, 9, 13, mh[s[2]], ml[s[2]], mh[s[3]], ml[s[3]]);
      G(2, 6, 10, 14, mh[s[4]], ml[s[4]], mh[s[5]], ml[s[5]]);
      G(3, 7, 11, 15, mh[s[6]], ml[s[6]], mh[s[7]], ml[s[7]]);
      G(0, 5, 10, 15, mh[s[8]], ml[s[8]], mh[s[9]], ml[s[9]]);
      G(1, 6, 11, 12, mh[s[10]], ml[s[10]], mh[s[11]], ml[s[11]]);
      G(2, 7, 8, 13, mh[s[12]], ml[s[12]], mh[s[13]], ml[s[13]]);
      G(3, 4, 9, 14, mh[s[14]], ml[s[14]], mh[s[15]], ml[s[15]]);
    }
    for (let i = 0; i < 8; i++) { hh[i] ^= vh[i] ^ vh[i + 8]; hl[i] ^= vl[i] ^ vl[i + 8]; }
  };

  // All full blocks except the last one (the final block, even when full, carries the last-flag).
  let off = 0;
  while (input.length - off > 128) {
    block.set(input.subarray(off, off + 128));
    off += 128; t += 128;
    compress(false, t);
  }
  block.fill(0);
  block.set(input.subarray(off));
  t += input.length - off;
  compress(true, t);

  const out = new Uint8Array(64);
  for (let i = 0; i < 8; i++) {
    for (let k = 0; k < 4; k++) { out[i * 8 + k] = (hl[i] >>> (8 * k)) & 255; out[i * 8 + 4 + k] = (hh[i] >>> (8 * k)) & 255; }
  }
  return out.slice(0, digestSize);
}
