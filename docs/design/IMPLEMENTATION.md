# v2.1 implementation spec (for the coder)

Everything below is exact. Reference renders: `contact-marks.png`, `contact-light.png`, `contact-dark.png`, `sheet-rim-strip.png` in this folder; the reference geometry as executable code is `tools/design/model.mjs` (dev-only; the product re-implements it in `desktop/src`). The measuring script is `tools/design/measure.mjs`; its output is `contrast-table.md`. **Do not edit** `contract/`, `tests/acceptance/`, `desktop/test/acceptance/` (`git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` must stay empty). The v2.1 field changes were run against the whole locked suite in a scratch copy: **116/116 green** (`field-f1-f2.patch`).

## 0. What changes, in one table

| surface | v2.0 | v2.1 |
|---|---|---|
| sidebar mark | 28×14 dot glyphs, low ink (ΔL ≤ 0.30), error = faint beads, eye-spot = pale blob | **24×16** chip, ink picked for ≥ 3.6:1 on the row (floor 3.0:1, WCAG 1.4.11), five distinct silhouettes, error = grey/hollow/washed, eye = solid iris + big dark pupil |
| status strip | glyph + label, clipped | same mark at ×0.875 (21×14) + label, one nowrap row, verified not clipped |
| composer rim | 6 px, thin | **10 px**, bold: stripes / lobe train / wash + broken outline / eye |
| field | big dots everywhere, eye-spot mid-page and pale | organs left of ½ the width are drawn at **½ radius** (same ink); eye-spot = one big **dark** disc in the right gutter |
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
             blanch: ink(hue, 0.012),          // error: near-achromatic (meanChroma ≤ 0.03), the hue is "bleached out"
             spot:   oklchToHex(dir>0 ? 0.07 : 0.17, 0.03, hue),   // the pupil: near-black on both grounds
             wash:   palette.blanch }          // used only at alpha 0.30, as a plate
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

error            pigment blanch   (eight r=1.9 beads on an oval, centre (12,8), rx 9.6 ry 5.6, phase 22.5°: clear gaps = "broken")
  [20.87,10.14] [15.67,13.17] [8.33,13.17] [3.13,10.14] [3.13,5.86] [8.33,2.83] [15.67,2.83] [20.87,5.86]     (r = 1.9)
  extras   <ellipse cx=12 cy=8 rx=9.2 ry=5.6 fill=blanch fill-opacity=.30/>    (the pale wash chip; drawn FIRST, under the beads)

finished_unseen  (sixteen chroma beads r=1.3 on a circle of radius 6.6 at (12,8), then ONE pupil)
  beads    [18.6,8] [18.1,10.53] [16.67,12.67] [14.53,14.1] [12,14.6] [9.47,14.1] [7.33,12.67] [5.9,10.53] [5.4,8] [5.9,5.47] [7.33,3.33] [9.47,1.9] [12,1.4] [14.53,1.9] [16.67,3.33] [18.1,5.47]
  pupil    [12,8, r=3.6] pigment spot, role 'eyespot'      (LAST entry; the only 'eyespot' dot)
  extras   <ellipse cx=12 cy=8 rx=6.6 ry=6.6 fill=chroma/>    (the iris disc, drawn FIRST; an <ellipse>, never a <circle>)
```
Draw order in the SVG: extras first, then dots (the order of the arrays). `svgElement` gets an optional `extras` argument (adapters/svg.ts) and renders `rect`/`ellipse` nodes through the same `jsx` factory with the raw numbers.

Domain API (unchanged signatures): `glyphOf(base)` keeps returning `GlyphDot[]` (`{x,y,r,pigment:'chroma'|'blanch'|'spot'}`; drop the `ink` field); add `glyphExtras(base): GlyphExtra[]` (`{k:'rect'|'ellipse', …, pigment:'chroma'|'blanch', alpha?}`) and export `GLYPH_W=24, GLYPH_H=16, STRIP_K=0.875`. `renderSwatch`/`renderStrip` still return `{dots,width,height}` (strip: ×K); add `extras` to the returned object (`{dots, width, height, extras}`); `renderSmall` no longer calls `alphaFor/effectiveDl`.

**Layout.** The mark is `width:24px;height:16px;flex:none`. It replaces a 28×14 box: **+4 px of title room at every sidebar width**; nothing else in the row moves. Row height (27 px) leaves 5.5 px above and below.

**Strip.** Root: `display:inline-flex; align-items:center; gap:6px; white-space:nowrap; line-height:1; flex-shrink:0; font-weight:600` (label) next to the 21×14 SVG. Label text = state label (resting's empty label falls back to the state name, as today).

## 3. Composer rim

`RIM_HEIGHT = 10` (surfaces.ts). `rimNodes(i)` returns, per `base` (`c`=chroma, `b`=blanch, `s`=spot pigments of §1 for `i.ground`; `h=10`; widths are `100%` of the composer, as today):
* **mottle** (resting): `rect x0 y9 w100% h1 fill c`.
* **clouds** (working): `rect x0 y4.25 w100% h1.5 c opacity .45` (track) + lobe trains: `circle`s with `cy=5, fill=c`; a train = radii `r_i`, centres at `x0 + Σ 1.15·r_j` (j<i); trains `[3.2,4.6,3.6] [3.8,5,4,2.8] [3,4.2] [3.6,5,4] [3,4.4,3.2]` repeated; first train at x=18 px, next train starts `Σ(1.15·r) + 40 + (k·37 mod 70)` px after the previous start, k = train counter from 1; stop when x ≥ width−40. (Static: the rim never animates.) Use `x` in px (the rim measures its own width with `width='100%'` → draw in a `viewBox` of the composer width, or render with a fixed 1600 px tile and `preserveAspectRatio="xMinYMid slice"`; the coder picks one, the markup differs by state either way).
* **zebra** (needs you): `pattern id=cf-rim-stripes width=12 height=10 patternUnits=userSpaceOnUse patternTransform="skewX(-45)"` containing `rect w6 h10 fill c`; `rect w100% h10 fill url(#cf-rim-stripes)`. (45°, 6 on / 6 off.)
* **blanch** (error): `rect x0 y0 w100% h10 fill b opacity .16` + `rect x1 y1 w(100%−2) h8 rx2 fill none stroke b stroke-width 2 stroke-dasharray "9 6"`.
* **eyespot** (finished): hairline as mottle + `circle cx20 cy5 r4.8 fill c` + `circle cx20 cy5 r3 fill s`.
The `--dt-composer-ring` variable stays the identity hue's pigment (not state): unchanged.

## 4. The field (focused chat): two changes, both proven against the locked suite

Apply `docs/design/field-f1-f2.patch` (it is a diff of `domain/organs.ts`, `domain/pattern.ts`, `domain/field.ts` only):
* **F1 eye-spot**: `eyeSpotAt` → `x = w·(0.74 + 0.16·u)`, `y = h·(0.50 + 0.20·u')` (right gutter, lower half, away from the text column). `planGround.spot = oklchToHex(clamp(gl − 0.62, .03, .97), 0.09, hue)` (near-black on light grounds, black on dark). The dot's ΔL target is `min(spotMaxDl, 0.50·intensity·bloom)` (was 0.156, capped 0.30). Radius unchanged (`5.4 × median organ radius`, ≈ 30 px).
* **F2 reading lane**: in `renderField`, every `role:'organ'` dot with `x < 0.5·width` has its **radius × 0.5** (ink/alpha unchanged, because the locked blanch/loudness tests are per-dot ΔL). Text lives on the left; the stripes/blobs/clouds read in the open right half.
`tools/design/field_spike.ts` shows the classifier at 0/300 misreads for this shrink.

No other field constant changes. (Why not more: the stripes are a scatter of ≤ 190 fixed-position organs by contract; they can only ever read as bands of big dots. The rim and the sidebar carry the unmistakable stripes.)

## 5. Files that change in `desktop/src`

| file | change |
|---|---|
| `domain/ink.ts` (new) | `contrast`, `inkFor`, `palette` (§1) |
| `domain/glyph.ts` | §2 geometry; `GLYPH_W/H`, `STRIP_K`; `glyphExtras`; drop `ink` |
| `domain/field.ts` | `renderSmall`: opaque dots from `palette`, extras; F2 lane in `renderField`; eye dot ΔL (F1) |
| `domain/organs.ts`, `domain/pattern.ts` | F1 (patch) |
| `domain/index.ts` | export `inkFor`, `palette`, `contrast`, `glyphExtras`, `STRIP_K` |
| `adapters/svg.ts` | `svgElement(…, dots, extras?)`: extras first |
| `adapters/surfaces.ts` | `RIM_HEIGHT=10`; SwatchView/StripView pass `out.extras`; strip label weight; strip svg is the ×K mark |
| `adapters/rim.ts` | §3 nodes; `RimInput` gets nothing new |
| `desktop/plugin.js` | rebuilt by `node desktop/build.mjs` (`--check` must pass) |
| `docs/LANGUAGE.md`, `README.md` | already updated in this lane |

## 6. Failing tests to write FIRST (`desktop/test/unit/…`; each must fail on v2.0 code)

1. `glyph.test.ts › every dot of every state lies inside the 24×16 box (±0.5), the strip inside 21×14` — loop `PATTERN_KINDS`, `glyphOf`, `renderSwatch`, `renderStrip`.
2. `glyph.test.ts › five silhouettes: pairwise IoU ≤ 0.55` — rasterise each state's circles + extras on a 96×64 grid (a ~20-line scanline test helper: pixel in if inside any circle or extra ellipse/rect-stroke, ×4 scale; mask = ink pixels, not the 0.30 wash), assert `IoU(a,b) ≤ 0.55` for all 10 pairs. Reference values from the pixel measurement: worst pair working/finished 0.53; the others ≤ 0.36.
3. `glyph.test.ts › WCAG 1.4.11: every pigment ≥ 3.3:1 on the row` — for ground ∈ {`#fefefe`,`#141416`,`#2e3440`}, hue ∈ {100,150,205,260,310,350}, row ∈ {unselected, selected} using the design rows `light {#f6f8fa, #d8e1f0}`, `dark {#17181c, #2a3142}`, `nord {#2e3440, #434c5e}`: `contrast(palette(hue, ground)[p], row) ≥ 3.3` for `p ∈ {chroma, blanch}`, and `contrast(palette.spot, palette.chroma) ≥ 3.0` (pupil vs iris). Measured minimum from pixels: 3.33 (dark selected).
4. `glyph.test.ts › error is the only grey mark` — `meanChroma(error dots) ≤ 0.03`; every other state's organ dots within 10° of the identity hue (measured worst case over hues 0–357° × 4 grounds: 5.1°; if a coder's colour maths drifts more, lower C for that hue by bisection, keep the hue exact); `error` extras use `blanch`.
5. `glyph.test.ts › finished-unseen has exactly one eyespot-role dot, r ≥ 2.5 × the median organ radius, and a solid iris extra of radius 6.6`.
6. `glyph.test.ts › the swatch is opaque and intensity 0 switches it off` (alpha 1 / alpha 0), `the strip is the swatch × 0.875`.
7. `glyph.test.ts › extras are never circles` — every `glyphExtras(*)` entry has `k ∈ {'rect','ellipse'}`; and a surface test that the SwatchView tree has exactly `renderSwatch().dots.length` `<circle>` elements (oA_part4's guard).
8. `rim.test.ts › rim nodes per state` — height 10; mottle: one rect h1; clouds: ≥ 12 circles and a track rect; zebra: pattern width 12, `skewX(-45)`, stripe rect width 6; blanch: wash rect + dashed rect (`'9 6'`, stroke-width 2); eyespot: iris r 4.8 + pupil r 3; the five markups pairwise different.
9. `field.test.ts › eye-spot sits in the right gutter, dark, bold` — over the 20 corpus roots × 3 grounds: `x ∈ [0.74,0.90]·W`, `y ∈ [0.50,0.70]·H`; on light grounds the dot's `dotDeltaL ≥ 0.45`; radius ≥ 5 × median.
10. `field.test.ts › reading lane` — organs with `x < W/2` have `r` exactly half of the same organ's unlaned radius (`renderField` vs a copy with `LANE_SHRINK=1` via the constellation), alpha unchanged.
11. `surfaces.test.ts › the strip is one nowrap row and cannot clip` — the StripView root style is `{display:'inline-flex', alignItems:'center', whiteSpace:'nowrap', flexShrink:0, lineHeight:1}`; children are `[svg(height ≤ 16), label]`; and `svg.height + 2 ≤ 20` (the status bar's content height). **Layout check on the real Desktop** (the evidence DOM dump, `tools/desktop/pagecode.ts` strip section): `strip.scrollWidth ≤ strip.clientWidth`, `strip.getBoundingClientRect().right ≤ statusbar.getBoundingClientRect().right`, label `getBoundingClientRect().height > 0` and inside the status bar's rect, for all five states at 1600×1000 and 1280×800.
12. `surfaces.test.ts › the sidebar mark never costs title room` — `GLYPH_W ≤ 28`.

## 7. Acceptance numbers

* Unit tests above: green. Locked suites: `make contract` green; `git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` empty; `node desktop/build.mjs --check` exit 0.
* Objective (re-run on the built product's own rendering by pointing `measure.mjs` at the new geometry, or equivalently against `tools/design/model.mjs`): **min non-text contrast ≥ 3.3:1** over 3 grounds × selected/unselected × 6 hues × 1×/2× (bar 3.0:1); **worst silhouette IoU ≤ 0.55**.
* On the real Desktop evidence (`make evidence`): strip not clipped (all states, both window sizes); idle ≤ +1 pp; working ≤ +6.0 pp at ≥ 4 field updates/s — **see `D3.md`: not met by any contract-legal technique tried; the numbers are written down there.**
* Independent vision critique on the new stills: the three questions (readable at a glance, five states distinguishable, not distracting at rest).

## 8. Pairwise silhouettes (what makes each pair differ by shape, not hue)

| pair | difference |
|---|---|
| resting ↔ working | three tiny specks vs one solid 20×11 cloud |
| resting ↔ needs you | specks vs an outlined, striped plate |
| resting ↔ error | specks vs a pale grey plate with a ring of beads |
| resting ↔ finished | specks vs a toothed solid disc with a black pupil |
| working ↔ needs you | bumpy solid blob vs rectangular plate with diagonal gaps |
| working ↔ error | solid vs hollow |
| working ↔ finished | wide flat-bottomed blob vs round disc ⌀ 14.6 (IoU 0.53 — the closest pair; the pupil and the toothed rim separate them further) |
| needs you ↔ error | striped fill vs hollow ring; outline is rectangular vs oval |
| needs you ↔ finished | rectangle vs disc; stripes vs solid |
| error ↔ finished | hollow dashed oval, grey, vs solid round hue disc, dark pupil |
