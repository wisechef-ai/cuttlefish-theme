# v2.1 implementation spec (for the coder)

Everything below is exact. Reference renders: `contact-marks.png`, `contact-light.png`, `contact-dark.png`, `sheet-rim-strip.png` in this folder; the reference geometry as executable code is `tools/design/model.mjs` (dev-only; the product re-implements it in `desktop/src`). The measuring script is `tools/design/measure.mjs`; its output is `contrast-table.md`. **Do not edit** `contract/`, `tests/acceptance/`, `desktop/test/acceptance/` (`git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` must stay empty). The v2.1 field changes were run against the whole locked suite in a scratch copy: **116/116 green** (`field-f1-f2.patch`).

## 0. What changes, in one table

| surface | v2.0 | v2.1 |
|---|---|---|
| sidebar mark | 28×14 dot glyphs, low ink (ΔL ≤ 0.30), error = faint beads, eye-spot = pale blob | **24×16** chip, ink picked for ≥ 3.6:1 on the row (floor 3.0:1, WCAG 1.4.11), five categorically different marks at 1×: **one small soft oval** / **a large solid flat-bottomed cloud** / **a FILLED chip with 3 bold bars (loudest)** / **a HOLLOW pale grey square with a missing corner** / **a ringed round eye with a big dark core** |
| status strip | glyph + label, clipped | same mark at ×0.875 (21×14) + label, one nowrap row, verified not clipped |
| composer rim | 6 px, five unrelated bands | **one system**: a 10 px pill (same placement, same round end caps) whose fill/outline echo the mark: hairline / lobe train / stripes / wash + broken frame / one eye |
| field | big dots everywhere, text covered | **no organ in the reading lane**, placed from the measured real layout: x ≥ max(0.6·W, 704 px), y from 64 px to 88 % of H (header, cards, composer stay clear); needs-you swell 1.8, error swell 1.9 (quiet, pale); eye-spot = one dark disc (4.3 × median organ radius), anchored at (0.90·W, 0.30·H) for every session |
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
             soft:   ink(hue, 0.115, minContrast=3.5),   // resting: the quietest ink, still ≥ 3:1 on every row tint
             blanch: ink(hue, 0.012, minContrast=4.5),   // error: near-achromatic (meanChroma ≤ 0.03); a bold grey frame, never a faint one
             spot:   oklchToHex(dir>0 ? 0.07 : 0.17, 0.03, hue),   // the pupil: near-black on both grounds
             paper:  ground,                         // bars/flecks drawn "out of" a filled mark: the chat ground itself (never a new hue)
             wash:   palette.blanch }          // used only as a pale plate (alpha 0.14 in the mark, 0.30 in the rim), never as ink
```
`paper` is not an organ pigment: it appears only in `extras` (never in `dots`, so the contract's hue-drift test never sees it). contrast(paper, chroma) = contrast(ground, chroma) ≥ 3.6 by construction.
Worked values (hue 205): `#fefefe → chroma #007c8a, blanch #697274, spot #001316`; `#141416 → #00909d, #798485, #000203`; `#2e3440 → #2dbbc9, #a2adae, #000203`.

Swatch/strip dots are **opaque**: `dot.color = palette[pigment]`, `dot.alpha = intensity > 0 ? 1 : 0` (intensity dial: 0 = off; any intensity ≥ 1 is full; between, `min(1, intensity)`). This is the only place the dial acts on marks, and it keeps the existing unit test "intensity 0 switches the glyph off".

New file `desktop/src/domain/ink.ts`: `contrast(a,b)`, `inkFor(hue, chroma, ground)`, `palette(hue, ground)` — pure, reusing `oklch.ts`. `planGround` and the field are unchanged except §5.

## 2. Sidebar mark and status strip: geometry

Box `GLYPH_W=24, GLYPH_H=16` (design units = CSS px). Strip: every coordinate and radius × `STRIP_K = 0.875` (21×14). Each state = `dots` (circles → the domain's `Dot[]`, role `'organ'` unless stated) + `extras` (non-circle SVG shapes).

```
Coarse features first (read at 1×, next to core's grey 7 px bullet): resting = ONE small quiet oval · working = a LARGE solid flat-bottomed cloud ·
needs you = a FILLED chip with 3 bold bars (loudest) · error = a HOLLOW pale grey square with a big missing corner · finished = a round ringed eye.

resting          pigment soft   (one soft oval blob, 12×6 — never separate dots, so it cannot read as an ellipsis next to core's bullet)
  dots     [8.4,8.4,r2.9] [12,8,r3.3] [15.6,8.4,r2.9]                     (soft)
  extras   (ABOVE the dots) <ellipse cx=10.6 cy=7.2 rx=.8 ry=.8 fill=paper fill-opacity=.45/>  <ellipse cx=14.2 cy=9.2 rx=.7 ry=.7 fill=paper fill-opacity=.45/>   (the mottle)

working          pigment chroma   (a large solid cloud: three lobes on a flat base, ≈ 20×13)
  dots     [6.4,8.9,r4.4] [12.6,6.6,r5.6] [18.2,9.2,r4.0]
  extras   (BELOW) <rect x=2.4 y=9 width=19.8 height=4.9 rx=2.4 fill=chroma/>   (the flat bottom)

needs_you        pigment chroma   (a FILLED chip, saturated, with three bold paper-coloured diagonal bars: the loudest mark)
  dots     r=3 at [5,5] [12,5] [19,5] [5,11] [12,11] [19,11]               (chroma; they carry the contract's ink and sit under the plate's colour)
  extras   (BELOW)  <rect x=.75 y=.75 width=22.5 height=14.5 rx=3.5 fill=chroma/>
           (ABOVE)  <path d="M2.5 11.5 L11.5 2.5" stroke=paper stroke-width=2.4/>  <path d="M6.5 13.5 L17.5 2.5" …/>  <path d="M12.5 13.5 L21.5 4.5" …/>   (butt caps; same paper, width 2.4)

error            pigment blanch   (a HOLLOW pale chip, never filled; the top-right corner is MISSING; two round ends where the frame breaks)
  dots     [13.4,1.5,r1.6] [22.5,9.9,r1.6]                                  (blanch)
  extras   (BELOW)  <rect x=2 y=2 width=20 height=12 rx=1 fill=blanch fill-opacity=.14/>     (the pale plate)
           (BELOW)  <path d="M13.2 1.5 H1.5 V14.5 H22.5 V9.9" fill=none stroke=blanch stroke-width=2.4 stroke-linejoin=miter/>   (open: no top-right corner)

finished_unseen  (a pale disc, a crisp ring, ONE big dark core, four iris flecks; ROUND, 15.6 across)
  dots     four flecks r=0.6 (chroma) at (12+5.5cosθ, 8+5.5sinθ), θ = 45°,135°,225°,315°   (the small "organs" spotRatios compares to)
           core [12,8,r4.5] pigment spot, role 'eyespot'      (LAST dot; the only 'eyespot' dot; ratio 4.5/0.6 = 7.5)
  extras   (BELOW)  <ellipse cx=12 cy=8 rx=7 ry=7 fill=chroma fill-opacity=.30/>              (the pale disc; on dark grounds it is the light halo)
           (BELOW)  <ellipse cx=12 cy=8 rx=7 ry=7 fill=none stroke=chroma stroke-width=1.6/>  (the crisp ring: an <ellipse>, never a <circle>)
```
Draw order in the SVG: extras marked BELOW, then the dots (array order), then extras marked ABOVE (`above: true`). `svgElement` gets an optional `extras` argument (adapters/svg.ts) and renders `rect`/`ellipse`/`path` nodes through the same `jsx` factory with the raw numbers.

Domain API (unchanged signatures): `glyphOf(base)` keeps returning `GlyphDot[]` (`{x,y,r,pigment:'chroma'|'soft'|'blanch'|'spot'}`; drop the `ink` field); add `glyphExtras(base): GlyphExtra[]` (`{k:'rect'|'ellipse'|'path', …, pigment:'chroma'|'blanch'|'paper'|'wash', alpha?, stroke?, above?}`) and export `GLYPH_W=24, GLYPH_H=16, STRIP_K=0.875`. `renderSwatch`/`renderStrip` still return `{dots,width,height}` (strip: ×K); add `extras` to the returned object (`{dots, width, height, extras}`); `renderSmall` no longer calls `alphaFor/effectiveDl`.

**Layout.** The mark is `width:24px;height:16px;flex:none`. It replaces a 28×14 box: **+4 px of title room at every sidebar width**; nothing else in the row moves. Row height (27 px) leaves 5.5 px above and below.

**Strip.** Root: `display:inline-flex; align-items:center; gap:6px; white-space:nowrap; line-height:1; flex-shrink:0; font-weight:600` (label) next to the 21×14 SVG. Label text = state label (resting's empty label falls back to the state name, as today).

## 3. Composer rim: ONE system

`RIM_HEIGHT = 10`. Every state draws the **same pill**: `rect x=.75 y=.75 width=(W−1.5) height=8.5 rx=4.25 fill=none` (same placement, same round end caps, 1 px inset, W = composer width) and a `clipPath id=cf-rim-cap` of the same rect. Only what fills the pill and how its outline is drawn changes, echoing the mark (`c`/`b`/`s` = chroma/blanch/spot of §1 for `i.ground`):

| base | fill (clipped to the pill) | outline |
|---|---|---|
| mottle (resting) | none | `stroke c, 1` |
| clouds (working) | lobe trains: `circle cy=5 fill c`; train radii `[3.2,4.6,3.6] [3.8,5,4,2.8] [3,4.2] [3.6,5,4] [3,4.4,3.2]` repeated, lobe i centred at `x + Σ_{j<i} 1.15·r_j`; first train x=26; next train starts `Σ(1.15·r) + 40 + (k·37 mod 70)` px later (k = train counter from 1) until x ≥ W−40 | `stroke c, 1` |
| zebra (needs you) | `pattern id=cf-rim-stripes width=12 height=10 userSpaceOnUse patternTransform=skewX(-45)` of `rect w6 h10 fill c` | `stroke c, 1.5` |
| blanch (error) | `rect fill b fill-opacity .38` | `stroke b, 3, stroke-dasharray "round(0.42·W) 14"` (a firmer broken frame with gaps; still pale-wash, grey) |
| eyespot (finished) | none | `stroke c, 1`; plus at x=14,y=5: `circle r3.9 fill c fill-opacity .3 stroke c stroke-width 1.2` and `circle r2.4 fill s` |

**Placement:** the rim element sits 5 px above the composer box (`margin-bottom: 5px` on the rim root, i.e. a clear gap so it can never read as a doubled border). (Static: the rim never animates. Draw at the composer's measured width, or in a fixed-width tile with `preserveAspectRatio="xMinYMid slice"`; the markup differs by state either way — P3.2.) The `--dt-composer-ring` variable stays the identity hue's pigment (not state): unchanged. Reference: `tools/design/model.mjs rimSvg`, `sheet-rim-strip.png`.

## 4. The field (focused chat): the reading lane, placed from the REAL layout, proven against the locked suite

**Measured on the real Desktop** (evidence stills' exclusion boxes, `evidence/v2` at 1600×1000 and `evidence/v2-1280x800`; chat surface x from 260, y from 34; all numbers below are px from the surface's left/top edge): the header box spans y 5–50 and the full width (right-hand icons y 11–42); message cards/commands start at x 21 and end at **x 603 (command card) / 679 (error card)**; y 50–200 holds the first message; message-action icon rows sit right-aligned at the right edge, one per assistant message; the composer starts ≈ 886 px down at 1600×1000. The prose column's right edge cannot be read from these short stills (the header box proves the column spans the whole width), so a very long paragraph can still reach the right.

Apply `docs/design/field-f1-f2.patch` (a diff of `domain/organs.ts`, `domain/pattern.ts`, `domain/field.ts` only). **116/116 locked acceptance tests green with it** (scratch copy; no product code was touched in this lane). What it does:
* **Reading lane, on every state.** `renderField` places organs only in the open region: **x ≥ `lane`**, `lane = W · min(0.70, max(0.60, 704 / W))` (so ≥ 704 px at any width: 25 px clear of the widest measured card; = 0.6·W at 1339 and 1200), **y ≥ top**, `top = clamp(64 px, 5 %·H, 12 %·H)` (below the header), **y ≤ 88 % of H** (above the composer). A lattice of the same density over that region (`190 · regionArea / surfaceArea · 1.6` organs ≈ 100 at 1339×879), offset into place. Measured organ extent over the whole corpus at 1339×879: x ≥ 805, y ∈ [64, 758].
* **Cloud travel stays inside the region** (`fieldCloudInk` in region coordinates; the band centre keeps 0.9σ from each edge), so no phase of the cycle has the cloud half outside the organs. Stripes/blanch/mottle keep whole-surface coordinates (the locked classifier reads them against the whole surface; region-relative coordinates fail 54/300 needs-you).
* **Classifier at the real sizes** (script: `tools/design/field_spike.ts` style, 20 roots × 3 grounds × 5 presets, 8 time phases): **0/300 misreads at 1339×879 and 1200×800 at every phase.** At 1280×800 (surface 1020×680, region only 316 px wide) `working` misreads in 2–6 % of renders at some phases (needs-you/error/rest/finished: 0). That window size is report-only in the evidence; if the coder sees it, do not widen the lane (it clears the cards); say so in the report. More organs make it worse (density 2.0: 4–6 %).
* **Needs you: sparse and quiet.** `ZEBRA_SWELL 2.2 → 1.8`, `ZEBRA_SHRINK 0.55 → 0.45`. Not quieter than that: the locked O7_5 needs real-pixel `needs_you` highK ≥ 0.6 and mean ΔL ≥ 2× resting; the domain suite (O2.3: mean ΔL ≥ 0.06 and ≥ 2× resting) passes. **Risk to check on the real stills:** the real-pixel highK/mean ΔL have not been measured with this patch.
* **Error: fewer, paler, never denser than resting.** `BLANCH_LIGHTER_LIGHT 0.012 → 0.0135`; and (round 4) `BLANCH_SWELL 1.0` with 40 % of organs at zero ink — see §4b. (The earlier swell 1.9 is withdrawn.)
* **Finished unseen: one deliberate eye-spot.** The contract requires the field to carry exactly one outlier dot (O2.1 reads `spot` from `spotRatios`: largest radius ≥ 4× the median organ radius, runner-up ≤ 2×), so it cannot be removed; it can only be one dot (no ring). It is now **anchored, the same for every session**: `eyeSpotAt = (0.90·W, 0.30·H)` (right gutter, a third of the way down, under the header icons), no jitter; pigment `planGround.spot = oklchToHex(clamp(gl−0.62,.03,.97), .09, hue)` (the mark's dark core colour), ΔL target `min(spotMaxDl, 0.50·intensity·bloom)`; radius `4.3 ×` median organ radius (≈ 23 px here; below 4.0 the `first ≥ 4` read is fragile). It is the dark core of the mark seen at field scale; the ring+pale disc live in the mark, the rim and the strip.
* No other field constant changes. The stripes remain a scatter of fixed organs by contract: they can only ever read as bands of big dots, so the real work is done by the rim and the mark.

## 4b. Round 4 (after the first real-Desktop capture): three fixes, measured on real pixels

Patch: `docs/design/field-fix.patch` (a diff against c2cae11: `adapters/painter.ts`, `domain/field.ts`, `domain/pattern.ts`; rebuild `plugin.js`). Locked domain suite on the patched domain: **116/116**.

**F-A. The 48-circle budget is for the clouds only (this is the O7_5 failure).** The painter's `layerCircles` kept the 48 highest-alpha circles for EVERY state; for needs-you that deletes exactly the dim off-band organs the stripe read depends on (the locked instrument fills empty bins with the mean, so a field of only bright organs is flat). Reproduced on real pixels with the locked instruments (`tools/design/field_pixels.mjs` + `field_pixels.py`: the product's field drawn by Chromium at the Desktop's place, measured over the real sidecar regions and exclusions):

| field layer | canvas | needs_you highK | mean ΔL ÷ resting | resting organs / p95 |
|---|---|---|---|---|
| 48-circle budget (c2cae11) | 1600×1000 | **0.031** (real run: 0.284) FAIL | 4.8 | 25 / 0.039 |
| 48-circle budget | 1339×944 | **0.028** FAIL | 4.5 | 48 / 0.039 |
| **every organ (the fix)** | 1600×1000 (what the plugin paints) | **0.753** OK | 3.7 | 57 / 0.036 |
| every organ | 1339×944 (the surface itself) | **0.789** OK | 3.4 | 98 / 0.039 |

New painter function: `layerFor(base, dots)` = `base === 'clouds' ? layerCircles(dots) : dots.filter(alpha > 0 && r > 0)`; `buildCss` calls it. Rationale: only the working state repaints several times a second, so only it pays for circles; a static field is painted once. (The D3 budget is unaffected: +4.76 pp is a working-window number; the static states are checked by the idle window; re-measure it with the capture below.) Stripe count unchanged: FIELD_CYCLES 4 is best on real pixels (needs_you highK 0.79 / 0.75 at 4, 0.71 / 0.73 at 5, 0.63 / 0.75 at 6, canvas 1339×944 / 1600×1000). Margin over the 0.6 floor: 0.15–0.19. To gain more margin, make the canvas the surface's size (`width = viewport.width − 260`, `height = viewport.height − 56`): +0.036; optional, not required.

**Confirmed on the real Desktop** (full capture of c2cae11 + `field-fix.patch`, v0.22.7, 1600×1000, `docs/design/real-capture-fix.json`): needs_you **highK 0.783** (floor 0.6; was 0.284), mean ΔL 0.0759 = **3.26 × resting** (floor 2×); resting p95 0.040 (≤ 0.05), 56 organs (≥ 20); working 31 organs, lowK 0.25; working window 4.0 field updates/s, working on − off = −3.7 pp and idle on − off = −3.2 pp (both inside the +6.0 / +1.0 budgets; the negative sign is run-to-run noise of the shared host, so quote only "within budget"). Organs vs text, from the real needs_you still (locked detector, exclusions applied): 58 organs detected, **57 of them at x ≥ 900** (lane 960 minus radius), the 58th is a near-white #fbfcfd component at x = 0 (the sidebar edge, not the field); y from 79 to 853 (header bottom 50, composer top ≈ 886); widest text/card box right edge 603 (needs_you) / 734 (resting). From geometry: the plugin paints a 1600×1000 canvas, lane = 960 px, so every organ has x ≥ 960 against a widest card edge at 679 (281 px clear) and y ≥ 64 against the header box bottom at 50 and the composer top at ≈ 886 (organs end at 880). Note: the error still's field_pixels (p95 0.102, lowK 0.77) is dominated by the pink error card, which the exclusion boxes do not fully cover; the locked test does not read the error row.

**F-B. Error is FEWER, paler organs at resting size, never denser.** The contradiction (§6#10 vs swell 1.9, coverage 3.6× resting) is resolved by removing the swell: `BLANCH_SWELL 1.9 → 1.0` and a new `BLANCH_HIDDEN = 0.4`: in `organDots`, for the blanch pattern an organ whose `hashUnit(seed, 'blanch-hide:' + i) < 0.4` gets `alpha 0` (positions unchanged, so O2.6's organKey is unaffected; `toSvg` already skips alpha-0 dots). The locked pale-error tests (P2.1/P2.2: lighter than resting by ≥ 0.01 L, achromatic, ≥ 40 organs, mean ΔL ≥ 0.012) pass unchanged. Measured over 3 grounds × 20 roots at 1600×1000: **coverage(error) / coverage(resting) ≤ 0.714 (worst)**, visible error organs ≥ 47. Test 10 in §6 becomes: `coverage(error) ≤ coverage(resting)` and `visible organs ≥ 40`.

**F-C. O1 (security scan).** The design helpers contain no recursive delete any more (`find … -mindepth 1 -delete` inside their own scratch dirs), and the demo card text in the mock pages no longer prints a destructive command. The regex of `skills_guard.destructive_home_rm` finds nothing in any tracked file.

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
3. `glyph.test.ts › WCAG 1.4.11: every pigment ≥ 3.3:1 on the row` — for ground ∈ {`#fefefe`,`#141416`,`#2e3440`}, hue ∈ {100,150,205,260,310,350}, row ∈ {unselected, selected} using the design rows `light {#f6f8fa, #d8e1f0}`, `dark {#17181c, #2a3142}`, `nord {#2e3440, #434c5e}`: `contrast(palette(hue, ground)[p], row) ≥ 3.2` for `p ∈ {chroma, soft, blanch}`, and `contrast(paper, chroma) ≥ 3.5`, and `contrast(palette.spot, palette.chroma) ≥ 3.0` (pupil vs iris). Measured minimum from pixels: 3.25 (resting's soft ink on the dark selected row).
4. `glyph.test.ts › error is the only grey mark` — `meanChroma(error dots) ≤ 0.03`; every other state's organ dots within 10° of the identity hue (measured worst case over hues 0–357° × 4 grounds: 5.1°; if a coder's colour maths drifts more, lower C for that hue by bisection, keep the hue exact); `error` extras use `blanch`.
5. `glyph.test.ts › finished-unseen: exactly one eyespot-role dot (core r 4.5, ≥ 7 × the median organ radius 0.6), a pale-disc extra and a ring extra of radius 7, drawn BELOW; error: no ellipse extra, a plate rect (fill-opacity .14) and a frame path using only `M H V` commands that is open (first point ≠ last point) and whose bounding box leaves the top-right corner empty (no path vertex with x > 13.2 and y < 9.9)`.
6. `glyph.test.ts › the swatch is opaque and intensity 0 switches it off` (alpha 1 / alpha 0), `the strip is the swatch × 0.875`.
7. `glyph.test.ts › extras are never circles` — every `glyphExtras(*)` entry has `k ∈ {'rect','ellipse','path'}`; and a surface test that the SwatchView tree has exactly `renderSwatch().dots.length` `<circle>` elements (oA_part4's guard).
8. `rim.test.ts › rim nodes per state` — height 10; mottle: one rect h1; clouds: ≥ 12 circles and a track rect; zebra: pattern width 12, `skewX(-45)`, stripe rect width 6; blanch: wash rect + dashed rect (`'9 6'`, stroke-width 2); eyespot: iris r 4.8 + pupil r 3; the five markups pairwise different.
9. `field.test.ts › eye-spot is anchored in the gutter, dark` — over the 20 corpus roots × 3 grounds the dot is at exactly `(0.90·W, 0.30·H)` (same for every root); on light grounds the dot's `dotDeltaL ≥ 0.45`; radius ≥ 4 × median organ radius.
10. `field.test.ts › reading lane` (and see §4b F-B for the error coverage rule) — at (W,H) ∈ {1339×879, 1020×680, 1200×800} for every preset, root and ground, every non-eyespot dot has `x − r ≥ 0.95·lane`-ish i.e. `x ≥ 704` (or 0.6·W when larger) and `64 ≤ y` and `y ≤ 0.88·H`; also at every time phase for working (cloud centre within the region); `organs ≥ 40`; 
11. `surfaces.test.ts › the strip is one nowrap row and cannot clip` — the StripView root style is `{display:'inline-flex', alignItems:'center', whiteSpace:'nowrap', flexShrink:0, lineHeight:1}`; children are `[svg(height ≤ 16), label]`; and `svg.height + 2 ≤ 20` (the status bar's content height). **Layout check on the real Desktop** (the evidence DOM dump, `tools/desktop/pagecode.ts` strip section): `strip.scrollWidth ≤ strip.clientWidth`, `strip.getBoundingClientRect().right ≤ statusbar.getBoundingClientRect().right`, label `getBoundingClientRect().height > 0` and inside the status bar's rect, for all five states at 1600×1000 and 1280×800.
13. `glyph.test.ts › coarse features at 1×` — resting: all three dots overlap pairwise-adjacent (centre distance < sum of radii) and the union's bounding box ≤ 13×7 (one blob, smaller than working's ≥ 19×11); working: has a flat-bottom `rect` extra BELOW and ≥ 3 dots with r ≥ 4; needs_you: a FILLED plate `rect` (no stroke, alpha 1) BELOW and exactly three `path` extras with `pigment 'paper'` ABOVE; error: no filled chroma/plate with alpha 1 anywhere (hollow); every extra with `above:true` is rendered AFTER the dots.
14. `painter.test.ts › the circle budget is for the clouds only` — `layerFor('clouds', dots)` has ≤ 48 + eye circles; `layerFor('zebra'|'mottle'|'blanch'|'eyespot', dots)` returns EVERY dot with `alpha > 0 && r > 0` (for needs_you at 1600×1000: ≥ 90 circles, of which ≥ 30 have ΔL < 0.03 — the dim off-band organs).
15. `field.test.ts › error is fewer, same size` — for the error pattern, `r` equals the resting pattern's `r` for the same organ index (no swell), 35–45 % of the organs have `alpha 0`, the positions of all organs equal resting's (`organKey`), and `coverage(error) ≤ coverage(resting)` on every corpus root/ground.
16. Real-pixel gate (not a unit test; run before declaring done): `tools/design/field_pixels.mjs` + `field_pixels.py` (needs the remote render helper) must print needs_you highK ≥ 0.70 and mean ΔL ÷ resting ≥ 2.5, resting p95 ≤ 0.05 with ≥ 20 organs; the real `make evidence` field_pixels must show highK ≥ 0.6 (locked O7_5).
12. `surfaces.test.ts › the sidebar mark never costs title room` — `GLYPH_W ≤ 28`.

## 7. Acceptance numbers

* Unit tests above: green. Locked suites: `make contract` green; `git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` empty; `node desktop/build.mjs --check` exit 0.
* Objective (re-run on the built product's own rendering by pointing `measure.mjs` at the new geometry, or equivalently against `tools/design/model.mjs`): **min non-text contrast ≥ 3.2:1** over 3 grounds × selected/unselected × 6 hues × 1×/2× (bar 3.0:1); **worst silhouette IoU ≤ 0.55**.
* On the real Desktop evidence (`make evidence`): strip not clipped (all states, both window sizes); idle ≤ +1 pp; working ≤ +6.0 pp at ≥ 4 field updates/s — **see `D3.md`: not met by any contract-legal technique tried; the numbers are written down there.**
* Independent vision critique on the new stills: the three questions (readable at a glance, five states distinguishable, not distracting at rest).

## 8. Pairwise silhouettes (what makes each pair differ by shape, not hue) — measured at 2× from rendered pixels, worst case over grounds

| pair | coarse difference (visible at 1×) | IoU |
|---|---|---|
| resting ↔ working | one small quiet oval vs a large solid flat-bottomed cloud | 0.34 |
| resting ↔ needs you | small oval vs a filled, striped square | 0.10 |
| resting ↔ error | oval vs hollow square | 0.00 |
| resting ↔ finished | oval vs a round ringed eye with a black core | 0.32 |
| working ↔ needs you | cloud vs rectangle | 0.36 |
| working ↔ error | solid vs hollow | 0.12 |
| working ↔ finished | flat-bottomed cloud vs round ringed disc | 0.51 (closest pair; ≤ 0.55 bar) |
| needs you ↔ error | **filled + loud + striped** vs **hollow + pale + grey with a missing corner** | 0.40 |
| needs you ↔ finished | rectangle vs disc | 0.29 |
| **error ↔ finished** | angular hollow grey frame vs round ringed disc with a black core | **0.16** |
