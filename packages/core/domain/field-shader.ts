// Direction D "dots", XL scale, as ONE self-contained WebGL2 fragment shader (plan §13.2): no library,
// no runtime deps, no texture reads. The CPU pattern (domain/pattern.ts, paint scale 'XL') is the oracle;
// test/shader/ proves GPU == CPU in headless Chromium. This file is pure: GLSL source strings plus
// `uniformsFor`, which precomputes every colour from the domain so the shader never derives OKLCh.
//
// Paint at a LOW internal size (<= tokens.scales.XL.internal_max_px, e.g. 320x180) and let the compositor
// upscale with smoothing. Only `working` animates: every other look is a function of (look, hue, size)
// alone, so a host renders ONE frame and stops. Pixel (0,0) is the TOP-left, like paint().
import { oklch, type RGB } from './oklch.ts';
import { BLANCH, GREY } from './pattern.ts';
import { TOKENS as T } from './tokens.ts';

export const FIELD_LOOKS = ['idle', 'working', 'review', 'needs-you', 'fault', 'unknown'] as const;

export const FIELD_VERTEX_SOURCE = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

export const FIELD_FRAGMENT_SOURCE = `#version 300 es
precision highp float;
precision highp int;

uniform int uLook;        // 0 idle 1 working 2 review 3 needs-you 4 fault 5 unknown (degraded paints as unknown)
uniform int uSeed;        // round(hue * 10), or 1 when degraded
uniform int uStep;        // working frame index; 0 for every other look
uniform vec2 uSize;       // w, h in logical px
uniform vec2 uGrid;       // dot lattice cols, rows
uniform vec3 uLattice;    // pitch, row pitch, dot radius (px)
uniform float uLevels;    // coverage steps (3 = 4 coverage levels)
uniform vec3 uDots[3];    // identity dot colours, 0..255
uniform vec3 uBlanch;
uniform vec3 uGrey;
uniform vec3 uRed;
uniform vec3 uAmber;
uniform vec3 uGround;

out vec4 fragColor;

// JS: n = (i*374761393 + j*668265263 + k*2147483647) | 0 ; n = imul(n ^ (n >>> 13), 1274126177) ;
// ((n ^ (n >>> 16)) >>> 0) / 2^32.  uint arithmetic wraps mod 2^32, exactly like imul / |0 / >>>.
uint hashU(int i, int j, int k) {
  uint n = uint(i) * 374761393u + uint(j) * 668265263u + uint(k) * 2147483647u;
  n = (n ^ (n >> 13u)) * 1274126177u;
  return n ^ (n >> 16u);
}
float hash(int i, int j, int k) { return float(hashU(i, j, k)) / 4294967296.0; }

float vnoise(float x, float y, int seed) {
  float xi = floor(x), yi = floor(y), fx = x - xi, fy = y - yi;
  float sx = fx * fx * (3.0 - 2.0 * fx), sy = fy * fy * (3.0 - 2.0 * fy);
  int ix = int(xi), iy = int(yi);
  float a = hash(ix, iy, seed), b = hash(ix + 1, iy, seed), c = hash(ix, iy + 1, seed), d = hash(ix + 1, iy + 1, seed);
  return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
}

// One dot's look: returns openness (0 closed, 0.5 half, 1 open); tone is the dot colour.
float dotLook(int c, int r, out vec3 tone) {
  float j = hash(c, r, uSeed);
  tone = uDots[min(int(j * 3.0), 2)];
  float cf = float(c), rf = float(r);
  if (uLook == 0) {                                              // idle: ~18 % closed
    return j < 0.18 ? 0.0 : 1.0;
  } else if (uLook == 1) {                                       // working: a closed band drifts one dot per frame
    const float period = 14.0, halfBand = 3.0;
    float pos = mod(cf + floor(rf * 0.5) - float(uStep), period);
    float d = min(pos, period - pos);
    if (d <= halfBand) return d == halfBand ? 0.5 : 0.0;
    return j < 0.1 ? 0.0 : 1.0;
  } else if (uLook == 2) {                                       // review: value-noise mottle
    float n = vnoise(cf / 5.0, rf / 5.0, uSeed + 7);
    if (n < 0.38) return 0.0;
    tone = n > 0.66 ? uDots[2] : uDots[0];
    return n < 0.5 ? 0.5 : 1.0;
  } else if (uLook == 3) {                                       // needs-you: zebra bands
    float band = floor((cf + float(r & 1) * 0.5 + rf * 0.5) / 2.0);
    if (mod(band, 2.0) == 0.0) { tone = uDots[2]; return 1.0; }
    return 0.0;
  } else if (uLook == 4) {                                       // fault: blanch + red margin
    bool onEdge = c < 2 || cf >= uGrid.x - 2.0 || r < 2 || rf >= uGrid.y - 2.0;
    if (onEdge) { tone = uRed; return 1.0; }
    tone = uBlanch;
    return j < 0.06 ? 0.5 : 1.0;
  }
  tone = uGrey;                                                  // unknown / degraded: sparse diagonal
  return mod(cf + rf, 3.0) == 0.0 ? 1.0 : 0.0;
}

void main() {
  // gl_FragCoord is bottom-up, pixel centres at +0.5; the CPU oracle is top-down on integer pixels.
  float x = floor(gl_FragCoord.x);
  float y = uSize.y - 1.0 - floor(gl_FragCoord.y);
  float P = uLattice.x, RP = uLattice.y, R = uLattice.z;
  vec3 col = uGround;
  float best = 0.0;
  int r0 = int(floor(y / uLattice.y + 0.5));
  for (int r = r0 - 1; r <= r0 + 1; r++) {
    float off = (r & 1) == 1 ? P * 0.5 : 0.0;
    int c0 = int(floor((x - off) / P + 0.5));
    for (int c = c0 - 1; c <= c0 + 1; c++) {
      vec3 tone;
      float open = dotLook(c, r, tone);
      if (open <= 0.0) continue;
      float rad = open >= 1.0 ? R : R * 0.55;
      float dist = length(vec2(x - (float(c) * P + off), y - float(r) * RP));
      float cov = floor(clamp(rad - dist + 0.5, 0.0, 1.0) * uLevels + 0.5) / uLevels;
      if (cov > best) { best = cov; col = uGround + (tone - uGround) * cov; }
    }
  }
  if (uLook == 3) {                                              // two amber eyespots with a ground pupil
    float er = max(4.0, min(uSize.x, uSize.y) * 0.09);
    for (int s = 0; s < 2; s++) {
      float d = length(vec2(x - uSize.x * (s == 0 ? 0.3 : 0.7), y - uSize.y * 0.5));
      if (d < er * 0.35) col = uGround;
      else if (d < er) col = uAmber;
    }
  }
  fragColor = vec4(floor(col + 0.5) / 255.0, 1.0);
}
`;

/** Uniform name -> binder type: i = int, f = float, 2f/3f = vecN, 3fv = vec3[]. A host binds with this table. */
export const FIELD_UNIFORM_TYPES: Readonly<Record<string, string>> = Object.freeze({
  uLook: 'i', uSeed: 'i', uStep: 'i', uSize: '2f', uGrid: '2f', uLattice: '3f', uLevels: 'f',
  uDots: '3fv', uBlanch: '3f', uGrey: '3f', uRed: '3f', uAmber: '3f', uGround: '3f',
});

export interface FieldShaderArgs {
  look: string;
  /** Identity hue in degrees, or null/undefined when there is no binding (degraded paints as unknown). */
  hueDeg: number | null | undefined;
  /** Working-cloud frame index = floor(t * 4); the caller owns time. */
  step: number;
  w: number;
  h: number;
  reducedMotion?: boolean;
}
export type FieldUniforms = Record<string, number | number[]>;

const flat = (c: RGB): number[] => [c[0], c[1], c[2]];

/** Every uniform the fragment shader needs, mirroring the colour/seed/step derivation in pattern.ts `paint`. */
export function uniformsFor(a: FieldShaderArgs): FieldUniforms {
  const degraded = a.hueDeg == null;
  const look = degraded ? 'unknown' : a.look;
  const hue = degraded ? 0 : (a.hueDeg as number);
  const li = (FIELD_LOOKS as readonly string[]).indexOf(look);
  const moving = look === 'working' && !a.reducedMotion;
  const sc = T.scales.XL;
  const P = sc.pitch_px, RP = P * 0.866;
  return {
    uLook: li < 0 ? 5 : li,                                    // an unrecognised look paints as unknown, like paint()
    uSeed: degraded ? 1 : Math.round(hue * 10),
    uStep: moving ? a.step : 0,
    uSize: [a.w, a.h],
    uGrid: [Math.ceil(a.w / P) + 1, Math.ceil(a.h / RP) + 1],
    uLattice: [P, RP, P * sc.dot_radius_ratio],
    uLevels: sc.coverage_levels - 1,
    uDots: T.identity.dot_lightness.flatMap(L => flat(oklch(L, T.identity.dot_chroma, hue))),
    uBlanch: flat(oklch(BLANCH.L, BLANCH.C, hue)),
    uGrey: flat(oklch(GREY.L, GREY.C, 0)),
    uRed: [...T.alarm.red.rgb],
    uAmber: [...T.alarm.amber.rgb],
    uGround: [...T.ground.rgb],
  };
}
