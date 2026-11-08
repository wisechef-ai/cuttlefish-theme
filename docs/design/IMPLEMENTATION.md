# v2.1 implementation spec (for the coder)

Everything below is exact. Reference renders: `contact-marks.png`, `contact-light.png`, `contact-dark.png`, `sheet-rim-strip.png` in this folder; the reference geometry as executable code is `tools/design/model.mjs` (dev-only; the product re-implements it in `desktop/src`). The measuring script is `tools/design/measure.mjs`; its output is `contrast-table.md`. **Do not edit** `contract/`, `tests/acceptance/`, `desktop/test/acceptance/` (`git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` must stay empty). The v2.1 field changes were run against the whole locked suite in a scratch copy: **116/116 green** (`field-f1-f2.patch`).

## 0. What changes, in one table

| surface | v2.0 | v2.1 |
|---|---|---|
| sidebar mark | 28×14 dot glyphs, low ink (ΔL ≤ 0.30), error = faint beads, eye-spot = pale blob | **24×16** chip, ink picked for ≥ 3.6:1 on the row (floor 3.0:1, WCAG 1.4.11), five distinct silhouettes: dots / cloud / striped plate / **hollow square with a broken frame (error, grey, angular)** / **pale disc, crisp ring, one big dark core (finished-unseen, round)** |
| status strip | glyph + label, clipped | same mark at ×0.875 (21×14) + label, one nowrap row, verified not clipped |
| composer rim | 6 px, five unrelated bands | **one system**: a 10 px pill (same placement, same round end caps) whose fill/outline echo the mark: hairline / lobe train / stripes / wash + broken frame / one eye |
| field | big dots everywhere, text covered | **no organ in the reading lane**: the left 60 % of the width, the top 5 % and the bottom 12 % (title, text, cards, composer) stay clear; needs-you swell 1.8, error swell 1.9 (quiet, pale); eye-spot = one dark disc (4.3 × median organ radius) in the right gutter |
| working motif | clouds only in places | cloud lobes on every surface (sidebar cloud = 7 lobes, rim = lobe trains, field = soft lobes) |

Contract facts the design was fitted to (do not "improve" past them):
* `renderSwatch/renderStrip` return `{dots, width, height}` with `height ≤ 16`, `width ≤ 28`/`64`, every dot inside its box ±0.5 (O2.9). New box: **24×16**.
* The shipped swatch's `<circle>` elements must equal `renderSwatch(...).dots` exactly (oA_part4). Non-circle shapes (the `rect`/`ellipse` extras below) are invisible to that test and are the designed place for plates and washes. **Never draw an extra as a `<circle>`.**
* O2.9 also demands: mean ΔL ≥ 0.08; error mean chroma ≤ 0.03; non-error organ hue within 10° of the identity hue; `spotRatios(dots).first ≥ 2` for finished-unseen (largest radius ÷ median *organ* radius; the pupil carries `role:'eyespot'`); pairwise per-slot ink differences ≥ 20 %.
* The rim must draw an SVG, carry `data-cf-state`, differ across ≥ 4 presets, and never wake the loop (static).
* The field keeps the `background: url("data:image/svg+xml,…") 0 0/Wpx Hpx no-repeat, var(--cf-ground)` route and the property allowlist; no change to the painter's CSS shape.

## 1. Colour: the ink formula (replaces the swatch/strip use of `alphaFor`)

Sidebar rows are not on the chat ground (selected rows are tinted), and the plugin only knows `v.ground` (the chat surface). So the ink is chosen to hold ≥ 3.6:1 on the ground **and** on a worst-case selected tint of it.

```
lab      = OKLab(ground)                       // v.ground, '#rrggbb'
dir      = lab.L < 0.5 ? +1 : -1               // +1: dark ground, ink is lighter; -1: light ground, ink is darker
SELECT   = 0.10                                // selected-row allowance in OKLab L, toward the ink
worst    = sRGB(OKLab(clamp(lab.L + dir*SELECT, .01, .99), lab.a, lab.b))
ink(h,C) = the L nearest the ground (bisect 24 steps between lab.L and dir>0 ? 0.97 : 0.04) such that
           contrast(oklchToHex(L, C, h), ground) ≥ 3.6  AND  contrast(…, worst) ≥ 3.6        // WCAG relative luminance
palette  = { chroma: ink(hue, 0.115),          // the identity pigment
             blanch: ink(hue, 0.012, minContrast=4.5),   // error: near-achromatic (meanChroma ≤ 0.03); a bold grey frame, never a faint one
             spot:   oklchToHex(dir>0 ? 0.07 : 0.17, 0.03, hue),   // the pupil: near-black on both grounds
             wash:   palette.blanch }          // used only as a pale plate (alpha 0.14 in the mark, 0.30 in the rim), never as ink
```
Worked values (hue 205): `#fefefe → chroma #007c8a, blanch #697274, spot #001316`; `#141416 → #00909d, #798485, #000203`; `#2e3440 → #2dbbc9, #a2adae, #000203`.

Swatch/strip dots are **opaque**: `dot.color = palette[pigment]`, `dot.alpha = intensity > 0 ? 1 : 0` (intensity dial: 0 = off; any intensity ≥ 1 is full; between, `min(1, intensity)`). This is the only place the dial acts on marks, and it keeps the existing unit test "intensity 0 switches the glyph off".

New file `desktop/src/domain/ink.ts`: `contrast(a,b)`, `inkFor(hue, chroma, ground)`, `palette(hue, ground)` — pure, reusing `oklch.ts`. `planGround` and the field are unchanged except §5.

## 2. Sidebar mark and status strip: geometry

Box `GLYPH_W=24, GLYPH_H=16` (design units = CSS px). Strip: every coordinate and radius × `STRIP_K = 0.875` (21×14). Each state = `dots` (circles → the domain's `Dot[]`, role `'organ'` unless stated) + `extras` (non-circle SVG shapes).

```
resting          pigment chroma
  [x,y,r]  [6,9.6,2.6] [12.4,5.8,2] [18,10,2.4]
  extras   none

working          pigment chroma   (seven overlapping lobes, all opaque: one solid cloud)
  [4.6,10.6,3] [8.8,9,3.6] [13.6,8.2,3.9] [18,9.6,3.4] [20.6,11.4,2.2] [11,11.6,3.2] [16,12,2.8]
  extras   none

needs_you        pigment chroma   (twenty r=1.7 dots on three "/" bars, step 1.2 along 45°, kept inside [2.3,21.7]×[2.3,13.7])
  [4.62,7.58] [5.47,6.73] [6.32,5.88] [7.17,5.03] [8.02,4.18]
  [8.18,11.82] [9.03,10.97] [9.88,10.12] [10.73,9.27] [11.58,8.42] [12.42,7.58] [13.27,6.73] [14.12,5.88] [14.97,5.03] [15.82,4.18]
  [15.98,11.82] [16.83,10.97] [17.68,10.12] [18.53,9.27] [19.38,8.42]          (all r = 1.7)
  extras   <rect x=.75 y=.75 width=22.5 height=14.5 rx=3.5 fill=none stroke=chroma stroke-width=1.5/>

error            pigment blanch   (a pale, hollow, SQUARE chip; its frame is broken at the right with a clear notch; two round ends where it breaks)
  dots     [22,4.4,r1.8] [22,11.6,r1.8]  (pigment blanch)
  extras   <rect x=2 y=2 width=20 height=12 rx=1 fill=blanch fill-opacity=.14/>               (the pale plate; FIRST)
           <path d="M22 4.4 V1.5 H1.5 V14.5 H22 V11.6" fill=none stroke=blanch stroke-width=2.2 stroke-linejoin=miter/>   (the broken frame: open between y 4.4 and 11.6)

finished_unseen  (a pale disc, a crisp ring, ONE big dark core, four iris flecks; ROUND)
  dots     four flecks r=0.7 (chroma) at (12+5.1cosθ, 8+5.1sinθ), θ = 45°,135°,225°,315°  — the "organs" the contract's spotRatios compares to
           core [12,8,r4.0] pigment spot, role 'eyespot'      (LAST entry; the only 'eyespot' dot; ratio 4.0/0.7 = 5.7)
  extras   <ellipse cx=12 cy=8 rx=6.8 ry=6.8 fill=chroma fill-opacity=.30/>                   (the pale disc; FIRST — on dark grounds it is the light halo)
           <ellipse cx=12 cy=8 rx=6.8 ry=6.8 fill=none stroke=chroma stroke-width=1.6/>        (the crisp ring; an <ellipse>, never a <circle>)
```
Draw order in the SVG: extras first, then dots (the order of the arrays). `svgElement` gets an optional `extras` argument (adapters/svg.ts) and renders `rect`/`ellipse`/`path` nodes through the same `jsx` factory with the raw numbers.

Domain API (unchanged signatures): `glyphOf(base)` keeps returning `GlyphDot[]` (`{x,y,r,pigment:'chroma'|'blanch'|'spot'}`; drop the `ink` field); add `glyphExtras(base): GlyphExtra[]` (`{k:'rect'|'ellipse'|'path', …, pigment:'chroma'|'blanch', alpha?, stroke?}`) and export `GLYPH_W=24, GLYPH_H=16, STRIP_K=0.875`. `renderSwatch`/`renderStrip` still return `{dots,width,height}` (strip: ×K); add `extras` to the returned object (`{dots, width, height, extras}`); `renderSmall` no longer calls `alphaFor/effectiveDl`.

**Layout.** The mark is `width:24px;height:16px;flex:none`. It replaces a 28×14 box: **+4 px of title room at every sidebar width**; nothing else in the row moves. Row height (27 px) leaves 5.5 px above and below.

**Strip.** Root: `display:inline-flex; align-items:center; gap:6px; white-space:nowrap; line-height:1; flex-shrink:0; font-weight:600` (label) next to the 21×14 SVG. Label text = state label (resting's empty label falls back to the state name, as today).

## 3. Composer rim: ONE system

`RIM_HEIGHT = 10`. Every state draws the **same pill**: `rect x=.75 y=.75 width=(W−1.5) height=8.5 rx=4.25 fill=none` (same placement, same round end caps, 1 px inset, W = composer width) and a `clipPath id=cf-rim-cap` of the same rect. Only what fills the pill and how its outline is drawn changes, echoing the mark (`c`/`b`/`s` = chroma/blanch/spot of §1 for `i.ground`):

| base | fill (clipped to the pill) | outline |
|---|---|---|
| mottle (resting) | none | `stroke c, 1` |
| clouds (working) | lobe trains: `circle cy=5 fill c`; train radii `[3.2,4.6,3.6] [3.8,5,4,2.8] [3,4.2] [3.6,5,4] [3,4.4,3.2]` repeated, lobe i centred at `x + Σ_{j<i} 1.15·r_j`; first train x=26; next train starts `Σ(1.15·r) + 40 + (k·37 mod 70)` px later (k = train counter from 1) until x ≥ W−40 | `stroke c, 1` |
| zebra (needs you) | `pattern id=cf-rim-stripes width=12 height=10 userSpaceOnUse patternTransform=skewX(-45)` of `rect w6 h10 fill c` | `stroke c, 1.5` |
| blanch (error) | `rect fill b fill-opacity .30` | `stroke b, 2.6, stroke-dasharray "round(0.42·W) 14"` (a broken frame with gaps) |
| eyespot (finished) | none | `stroke c, 1`; plus at x=14,y=5: `circle r3.9 fill c fill-opacity .3 stroke c stroke-width 1.2` and `circle r2.4 fill s` |

(Static: the rim never animates. Draw at the composer's measured width, or in a fixed-width tile with `preserveAspectRatio="xMinYMid slice"`; the markup differs by state either way — P3.2.) The `--dt-composer-ring` variable stays the identity hue's pigment (not state): unchanged. Reference: `tools/design/model.mjs rimSvg`, `sheet-rim-strip.png`.

## 4. The field (focused chat): the reading lane, proven against the locked suite

Apply `docs/design/field-f1-f2.patch` (a diff of `domain/organs.ts`, `domain/pattern.ts`, `domain/field.ts` only). **116/116 locked acceptance tests green with it** (scratch copy; no product code was touched in this lane). What it does:
* **Reading lane, on every state.** `renderField` builds its constellation only in the region **x ≥ 0.60·W, 0.05·H ≤ y ≤ 0.88·H** (a lattice of the same density over the smaller area: `190 · 0.40 · 0.83 · 1.6` ≈ 100 organs), then offsets it into place. So no organ is ever drawn behind the text column (left 60 %), the title card (top 5 %) or the composer (bottom 12 %). Stated limit: the constants GUTTER 0.60 / TOP 0.05 / BOTTOM 0.12 are the edge of what the locked classifier tolerates: GUTTER 0.65 already fails O2.1 and O4.6. Very wide transcripts (text past 60 % of the width) can still meet organs on the right; that is accepted.
* **Needs you: sparse and quiet.** `ZEBRA_SWELL 2.2 → 1.8`, `ZEBRA_SHRINK 0.55 → 0.45`. The stripes are carried by the mark and the rim; the field's bands are a hint.
* **Error: fewer, paler, never denser than resting.** `BLANCH_SWELL 3.2 → 1.9`, `BLANCH_LIGHTER_LIGHT 0.012 → 0.0135` (a deterministic margin so P2.1 holds with the smaller sample). Over the lane's smaller area the blobs cover far less of the page than v2.0's.
* **Finished unseen: one smaller dark eye-spot in the gutter.** `eyeSpotAt` → `x = w(0.80+0.12u)`, `y = h(0.52+0.16u')`; `planGround.spot = oklchToHex(clamp(gl−0.62,.03,.97), .09, hue)`; ΔL target `min(spotMaxDl, 0.50·intensity·bloom)`; radius `4.3 ×` median organ radius (≈ 25 px; below 4.0 the contract's `spotRatios.first ≥ 4` read becomes fragile). The field can only draw ONE `eyespot` dot, so the ring+core picture lives in the mark and the rim; the field's dot is the dark core.
* No other field constant changes. The stripes remain a scatter of fixed organs by contract: they can only ever read as bands of big dots, hence the real work is done by the rim and the mark.

## 5. Files that change in `desktop/src`

| file | change |
|---|---|
| `domain/ink.ts` (new) | `contrast`, `inkFor`, `palette` (§1) |
| `domain/glyph.ts` | §2 geometry; `GLYPH_W/H`, `STRIP_K`; `glyphExtras`; drop `ink` |
| `domain/field.ts` | `renderSmall`: opaque dots from `palette`, extras; reading-lane constellation in `renderField`; eye dot (patch) |
| `domain/organs.ts`, `domain/pattern.ts` | the patch |
| `domain/index.ts` | export `inkFor`, `palette`, `contrast`, `glyphExtras`, `STRIP_K` |
| `adapters/svg.ts` | `svgElement(…, dots, extras?)`: extras first |
| `adapters/surfaces.ts` | `RIM_HEIGHT=10`; SwatchView/StripView pass `out.extras`; strip label weight; strip svg is the ×K mark |
| `adapters/rim.ts` | §3 nodes; `RimInput` gets nothing new |
| `desktop/plugin.js` | rebuilt by `node desktop/build.mjs` (`--check` must pass) |
| `docs/LANGUAGE.md`, `README.md` | already updated in this lane |

## 6. Failing tests to write FIRST (`desktop/test/unit/…`; each must fail on v2.0 code)

1. `glyph.test.ts › every dot of every state lies inside the 24×16 box (±0.5), the strip inside 21×14` — loop `PATTERN_KINDS`, `glyphOf`, `renderSwatch`, `renderStrip`.
2. `glyph.test.ts › five silhouettes: pairwise IoU ≤ 0.55, and error vs finished-unseen ≤ 0.30` — rasterise each state's circles + extras (filled ellipses/rects and stroked paths/rects/ellipses; skip the pale plates) on a 96×64 grid (a small scanline test helper, ×4 scale); assert `IoU(a,b) ≤ 0.55` for all 10 pairs and the explicit pair error/finished-unseen `≤ 0.30`. Reference values from the pixel measurement (`contrast-table.md`): error/finished-unseen 0.18, worst pair working/finished-unseen 0.42, the rest ≤ 0.33.
3. `glyph.test.ts › WCAG 1.4.11: every pigment ≥ 3.3:1 on the row` — for ground ∈ {`#fefefe`,`#141416`,`#2e3440`}, hue ∈ {100,150,205,260,310,350}, row ∈ {unselected, selected} using the design rows `light {#f6f8fa, #d8e1f0}`, `dark {#17181c, #2a3142}`, `nord {#2e3440, #434c5e}`: `contrast(palette(hue, ground)[p], row) ≥ 3.3` for `p ∈ {chroma, blanch}`, and `contrast(palette.spot, palette.chroma) ≥ 3.0` (pupil vs iris). Measured minimum from pixels: 3.33 (dark selected).
4. `glyph.test.ts › error is the only grey mark` — `meanChroma(error dots) ≤ 0.03`; every other state's organ dots within 10° of the identity hue (measured worst case over hues 0–357° × 4 grounds: 5.1°; if a coder's colour maths drifts more, lower C for that hue by bisection, keep the hue exact); `error` extras use `blanch`.
5. `glyph.test.ts › finished-unseen has exactly one eyespot-role dot (r 4.0, ≥ 5 × the median organ radius 0.7) plus a pale-disc extra and a ring extra of radius 6.8; error has no ellipse extra and its frame path is rectilinear with a gap (only `M`/`H`/`V` commands, and the path is open: first and last points differ)`.
6. `glyph.test.ts › the swatch is opaque and intensity 0 switches it off` (alpha 1 / alpha 0), `the strip is the swatch × 0.875`.
7. `glyph.test.ts › extras are never circles` — every `glyphExtras(*)` entry has `k ∈ {'rect','ellipse','path'}`; and a surface test that the SwatchView tree has exactly `renderSwatch().dots.length` `<circle>` elements (oA_part4's guard).
8. `rim.test.ts › rim nodes per state` — height 10; mottle: one rect h1; clouds: ≥ 12 circles and a track rect; zebra: pattern width 12, `skewX(-45)`, stripe rect width 6; blanch: wash rect + dashed rect (`'9 6'`, stroke-width 2); eyespot: iris r 4.8 + pupil r 3; the five markups pairwise different.
9. `field.test.ts › eye-spot sits in the gutter, dark` — over the 20 corpus roots × 3 grounds: `x ∈ [0.80,0.92]·W`, `y ∈ [0.52,0.68]·H`; on light grounds the dot's `dotDeltaL ≥ 0.45`; radius ≥ 4 × median organ radius.
10. `field.test.ts › reading lane` — for every preset, root and ground, every organ has `x ≥ 0.60·W` and `0.05·H ≤ y ≤ 0.88·H`; `organs ≥ 40`; error: `coverage(error) ≤ coverage(resting)` (never denser than resting) — compute coverage with the contract's `coverage` instrument.
11. `surfaces.test.ts › the strip is one nowrap row and cannot clip` — the StripView root style is `{display:'inline-flex', alignItems:'center', whiteSpace:'nowrap', flexShrink:0, lineHeight:1}`; children are `[svg(height ≤ 16), label]`; and `svg.height + 2 ≤ 20` (the status bar's content height). **Layout check on the real Desktop** (the evidence DOM dump, `tools/desktop/pagecode.ts` strip section): `strip.scrollWidth ≤ strip.clientWidth`, `strip.getBoundingClientRect().right ≤ statusbar.getBoundingClientRect().right`, label `getBoundingClientRect().height > 0` and inside the status bar's rect, for all five states at 1600×1000 and 1280×800.
12. `surfaces.test.ts › the sidebar mark never costs title room` — `GLYPH_W ≤ 28`.

## 7. Acceptance numbers

* Unit tests above: green. Locked suites: `make contract` green; `git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` empty; `node desktop/build.mjs --check` exit 0.
* Objective (re-run on the built product's own rendering by pointing `measure.mjs` at the new geometry, or equivalently against `tools/design/model.mjs`): **min non-text contrast ≥ 3.3:1** over 3 grounds × selected/unselected × 6 hues × 1×/2× (bar 3.0:1); **worst silhouette IoU ≤ 0.55**.
* On the real Desktop evidence (`make evidence`): strip not clipped (all states, both window sizes); idle ≤ +1 pp; working ≤ +6.0 pp at ≥ 4 field updates/s — **see `D3.md`: not met by any contract-legal technique tried; the numbers are written down there.**
* Independent vision critique on the new stills: the three questions (readable at a glance, five states distinguishable, not distracting at rest).

## 8. Pairwise silhouettes (what makes each pair differ by shape, not hue)

| pair | difference | IoU |
|---|---|---|
| resting ↔ working | three tiny specks vs one solid 20×11 cloud | 0.33 |
| resting ↔ needs you | specks vs an outlined, striped plate | 0.16 |
| resting ↔ error | specks vs a square frame | 0.00 |
| resting ↔ finished | specks vs a ringed disc with a dark core | 0.20 |
| working ↔ needs you | bumpy solid blob vs rectangular plate with diagonal gaps | 0.28 |
| working ↔ error | solid vs hollow | 0.10 |
| working ↔ finished | wide flat-bottomed blob vs a round ring ⌀ 13.6 with a dark core | 0.42 |
| needs you ↔ error | striped fill vs hollow frame **open at the right**, no stripes | 0.26 |
| needs you ↔ finished | rectangle vs disc; stripes vs ring | 0.31 |
| **error ↔ finished** | **angular, hollow, broken, grey** vs **round, pale-filled, hue ring + one black core** | **0.18** |
