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

## 4c. Round r4 (strict critique of the real stills at 636503a): the seven rulings, exact changes

Patch: `docs/design/r4-marks-field.patch` (a diff of `desktop/src` at 636503a → the candidate; 7 files: `domain/glyph.ts`, `domain/pattern.ts`, `domain/field.ts`, `adapters/rim.ts`, `adapters/runtime.ts`, `adapters/view.ts`, `adapters/surfaces.ts`). Apply it, rebuild `desktop/plugin.js` (`node desktop/build.mjs`: the locked oA_part4 compares the SHIPPED plugin with the domain oracle, so a stale plugin.js fails P6.2–P6.4), then update the unit tests/goldens listed under "tests". **Locked suite on the patched tree: 116/116.** Goldens: `contact-marks.png` (2×) and `contact-marks@1x.png` (1×) are the sidebar rows on light, dark and Nord, selected and not; `real-size-sidebar-*@1x/2x.png` are 260×190 crops with a core-style grey bullet; `contact-light.png`/`contact-dark.png` are the five whole-window states plus the legend; `sheet-rim-strip.png` is the rims and strips. At 1× I named every state from the mark alone before writing this: upright mottled oval = resting, solid cloud = working, striped filled chip = needs you, hollow grey square with an open corner = error, almond eye = finished unseen.

### Ruling 1: needs-you is a static warning band; the hatch survives at 1×
* Mark (`GLYPHS.zebra`): chip `rect x2.5 y2 w19 h12 rx3` filled chroma; dots `r2.8` at `[6,5.5] [12,5.5] [18,5.5] [6,10.5] [12,10.5] [18,10.5]`; **two** paper bars (was three) `path M4 12 L12 4` and `M11.5 12 L19.5 4`, `stroke-width 3.4`, ABOVE. (Bar pitch 8 px horizontally, gap 2.3 px between bars.)
* Rim (`rim.ts`, `case 'zebra'`): **two end chips**, never a full-width band: `CHIP_W = 96` px of the 12/6 skewX(−45) stripes at the left end and (mirrored with `x: '100%'` + `transform: translate(-96 0)`) at the right end, each closed by a 1.5 px vertical end bar (`x: 96` / `x: '100%'` translate(−97.5)), the 1.5 px pill outline between them. A band with two clear ends reads as a warning label, not a marching progress bar. No motion (the rim is static; unchanged).

### Ruling 2: one blanched language (pale, washed, hollow, visibly broken)
* Mark (`GLYPHS.blanch`): plate `rect x2 y1.5 w20 h13 rx1` fill wash α .16; frame `path M13 1.5 H2 V14.5 H22 V9` stroke blanch 2.2; dots `[13,1.5,r1.5] [22,9,r1.5]` (blanch). The gap is 9 px of the top edge plus 7.5 px of the right edge (≥ 3 px at 1×; was 4.4 px diagonal).
* Rim (`case 'blanch'`): wash `fill-opacity .16` (was .38) and ONE line: `stroke blanch, stroke-width 1.6, pathLength 1000, stroke-dasharray '975 25', stroke-dashoffset -80`: a single 25/1000 break (≈ 40 px at a 1300 px composer). Was a 3 px dashed double ("40 14"). Lighter than core's recovery card yet unlike resting's 1 px hue hairline: grey, washed, broken.
* The status icon is the same mark ×0.875 (nothing to change).

### Ruling 3: working says "clouds" in a static still
* Field (`pattern.ts`): `radiusFactors(spec, cons, w, h, targets?)`; for `clouds` with `targets`: `r × (1.8 + 1.6 · clamp((target − CLOUD_BASE)/CLOUD_AMP, 0, 1))` (constants `CLOUD_SWELL_BASE 1.8`, `CLOUD_SWELL_BAND 1.6`): every organ is a larger translucent blob and the band's organs are up to ×3.4, so they overlap into cloud masses. `field.ts` passes `targets` as the 5th argument. The painter's cloud budget (48 circles) and 4 updates/s are untouched; circle area grows, so D3 was re-measured (below).
* Rim (`rim.ts`): the lobe trains are replaced by **miniature clouds**, the mark's three lobes on a flat base: per cloud `circle (x+3.4, 5.4, r2.5)`, `(x+7.2, 4.1, r3.2)`, `(x+11.2, 5.5, r2.7)` and `rect x+1.2 y5.3 w13.4 h3 rx1.5` (15.8 × 8 px), first at x = 30, then every `70 + (k·41 mod 64)` px on a 480 px tile (`TRAIN_TILE`), on the 1 px outline.
* Mark (`GLYPHS.clouds`): lobes `[6.8,9.6,r3.3] [12.4,7.8,r4.4] [17.6,9.8,r3.1]`, base `rect x3.8 y9.8 w16.2 h3.9 rx1.9`.

### Ruling 4: an eye, not a bullseye
`GLYPHS.eyespot`: almond lens `path M2 8 Q12 -2 22 8 Q12 18 2 8 Z` (fill chroma α .30 BELOW, then the same path stroke chroma 1.6), iris ring `ellipse (12,8) r4.4 stroke chroma 1.5`, pupil `dot [12,8,r2.8]` pigment spot (LAST, role eyespot), two corner dots `[3,8,r0.7] [21,8,r0.7]` chroma (the "organs" `spotRatios` compares to: 2.8/0.7 = 4.0 ≥ 2), catch-light `ellipse (13.3,6.6) r0.9` fill paper ABOVE. Paths now use `M H V L Q Z` (no arcs; the scale regex already handles negatives). Rim: lens `M8 5 Q20 -2 32 5 Q20 12 8 5 Z` (fill chroma α .3, stroke 1.2) + `circle (20,5) r2.6` chroma + `circle (20,5) r1.6` spot, on the 1 px outline. **The field still carries exactly one eye-spot dot** (contract O2.1): unchanged.

### Ruling 5: identity separation, and a resting mottle you can see
* Root cause: `surfaces.ts` and `view.ts` called `allocate(id, [])` (no peers), so two sessions share a hue whenever their hashes collide. Measured on 12 000 pairs of four sessions: **4.8 % identical hue, 23.8 % closer than 30°**.
* New `hueFor(v, id)` in `view.ts`: a per-view `Map<id, slot>`; every session the feed knows plus the asked one, in sorted order, that has no slot gets `allocate(id, [...slots held]).slot`; slots of sessions no longer known are released. Used for every row swatch and for `v.hueDeg` (the focused session). A single known session still gets `allocate(id, [])` (the locked oA_part4 oracle).
* Metric (stated and measured with the locked `allocate`, 200 random session sets): minimum pairwise **hue-angle gap ≥ 34.5° for 2–5 live sessions, ≥ 23° for 6–7, ≥ 11.5° (one slot) for 8–12**; never a shared hue below 20 live sessions. (The arc is the contract's 20 slots on [110°, 340°), so beyond 6 sessions a gap ≥ 30° is impossible; the allocator maximises the minimum.)
* Mark (`GLYPHS.mottle`): one upright oval, dots `[12,4.7,r4.3] [12,8,r5.0] [12,11.3,r4.3]` (soft ink), three paper holes ABOVE `(10.6,4.6) r1.0`, `(13.2,8.4) r1.1`, `(11,11.6) r0.9` at α .9: the mottle is 2 px holes, visible at 1×, quiet (soft ink, ≥ 3.5:1).

### Ruling 6: one optical footprint (±25 %), state comes from shape
All five marks live in the 24×16 box. Ink area at 1× (pixels ≥ 2:1 on the light ground, `contrast-table.md`): resting 110, working 136, needs you 148, error 110, finished 140 px²; ratio to the mean 0.86 / 1.05 / 1.15 / 0.85 / 1.09: all within ±25 %. Silhouette IoU (bar ≤ 0.55): resting/working 0.46, resting/finished 0.46, working/needs-you 0.39, working/finished 0.48, needs-you/finished 0.42, needs-you/error 0.16, error/finished 0.10, the rest ≤ 0.29. Contrast minimum 3.25:1.

### Ruling 7: the idle field is a designed mottle in the gutter
* The canvas is the chat SURFACE, not the window (`runtime.ts viewportOf`): `width = max(480, viewport.width − 260)`, `height = max(360, viewport.height − 56)` (1340 × 944 at 1600 × 1000; measured). Painting the window overshot the surface by 260 px, so the gutter was cut off and bunched on the right edge.
* Soft falloff (`field.ts`): after the organs are drawn, `r × (0.7 + 0.3 · min(fx, fy))` with a smoothstep ramp: `fx = min(ramp(x − lane, 0.30·rw), ramp(width − x, 0.08·rw))`, `fy = min(ramp(y − top, 0.12·rh), ramp(top + rh − y, 0.12·rh))` (`FALL_X .30, FALL_RIGHT .08, FALL_Y .12, FALL_MIN .7`). Radius only: the locked tests are per-dot ink, and the lane/clearance rules are untouched. The mottle thins at the lane edge, the top, the bottom and the far right instead of ending in a hard cut.

### Measured (real Desktop v0.22.7, 1600 × 1000, the candidate = 636503a + the patch; `docs/design/real-capture-r4.json`)
* Locked O7_5 field pixels: **needs_you highK 0.883** (floor 0.6; aim 0.75), mean ΔL 0.078 = **3.7 × resting** (resting 0.021, p95 **0.036**, 99 organs); working 48 organs (the cloud budget), p95 0.147; error p95 0.096 (the card inside the region is not excluded, as before). Proxy on the same field (`field_pixels.mjs`, surface canvas 1340 × 944): needs_you 0.792, ratio 3.5, resting p95 0.039, error mean ΔL 0.013, error coverage < resting.
* D3 (working on − off, 4.0 field updates/s) over **3 pairs: +5.09, +4.83, +3.71 pp, median 4.83, mean 4.54** (budget 6.0); idle on − off −0.03 pp. The bigger cloud blobs did not move the cost: the circle count is capped at 48.
* Real still, read by eye: sidebar-all shows an upright mottled oval, a solid cloud, a striped filled chip, a hollow grey square with an open corner and an almond eye, each nameable alone; the needs-you rim is two striped end chips; the gutter mottle covers the right 40 % evenly with a soft fade, clear of the card. Residual: with 8 sessions on a 20-slot arc, two sessions can still look alike (≥ 11.5° apart); that is the arc's limit, not the allocation.

### Tests (write first; they fail on 636503a)
1. `glyph.test.ts › the r4 marks`: dot/extra lists equal the lists above (resting 3 dots + 3 paper holes ABOVE; working 3 lobes + base rect; zebra 6 dots + chip + exactly TWO paper bars ABOVE; blanch 2 dots + plate + frame whose path is `M13 1.5 H2 V14.5 H22 V9`; eyespot 3 dots (pupil last, role eyespot, r2.8) + 4 extras, pupil/fleck ratio ≥ 2, catch-light ABOVE and paper); every dot inside 24×16 ±0.5.
2. `glyph.test.ts › optical footprint`: rasterise each mark (the 96×64 helper) and assert each ink area is within ±25 % of the five-mark mean; pairwise IoU ≤ 0.55 (error/finished ≤ 0.30).
3. `rim.test.ts › r4 rims`: zebra has exactly two chip rects of width 96 (one with `transform translate(-96 0)`) and two end bars, no full-width stripe rect; clouds has `4 × n` nodes per tile (three circles + one rect per cloud) and no lozenge; blanch has ONE outline rect with `pathLength 1000`, dasharray `975 25`, stroke-width 1.6, wash opacity .16; eyespot has a lens path with `Q`.
4. `view.test.ts › hueFor`: for 200 random sets of N = 2..5 sessions the minimum pairwise hue distance ≥ 34.5°; for N = 6..7 ≥ 23°; for N ≤ 19 no two equal; a single known session equals `allocate(id, []).hue_deg`; releasing a session frees its slot.
5. `runtime.test.ts` (existing viewport tests): expected sizes become `max(480, w − 260) × max(360, h − 56)`, e.g. a 1600 × 1000 viewport paints 1340 × 944. (The F1/F7/F8/first-paint/bloom runtime tests fail only on that size and on the golden CSS; update their expectations.)
6. `field.test.ts › cloud blobs`: for `clouds` with targets, every organ radius is ≥ 1.8× its unswelled radius and the brightest ≥ 3×; `spotRatios` of the working field still reads `first < 4`.
7. `field.test.ts › falloff`: radius factor is 0.7 at the lane edge and 1 in the middle of the region; resting ink per dot unchanged by the falloff.
8. Goldens (`renderField` digests, swatch digests, golden CSS): regenerate after steps 1–7 (they pin exact numbers).

## 4d. Round r5 (targeted: the error language, the two rims, a calmer rest)

Patch: `docs/design/r5-pale-error-quiet-rest.patch` (diff of `desktop/src` at 7049668 → candidate; 3 files: `domain/ink.ts`, `domain/glyph.ts`, `adapters/rim.ts`). Rebuild `desktop/plugin.js`. **Locked suite on the patched tree: 116/116.** Nothing else changes: not the field, not the needs-you or finished-unseen marks, not core chrome (the blue focus outline and the truncated "[app…" title are core's: untouched).

### Ruling 1: error is the PALEST mark (mark + status icon)
* The r4 mark was the darkest linework of the five (frame 2.2 px at 4.5:1). New (`GLYPHS.blanch`): plate `rect x3 y2.5 w18 h11 rx1` fill **chroma α .24** (a washed fill: the identity hue mixed far toward the ground; the wash is an extra, so the dots' achromatic rule `meanChroma ≤ 0.03` is untouched), frame `path M13 2.5 H3 V13.5 H21 V9` stroke **blanch 1.6**, dots `[13,2.5,r1.1] [21,9,r1.1]` (blanch). The open corner is 8.5 px of the top edge + 7 px of the right edge.
* Contrast maths (the locked bar is 3:1 for the OUTLINE; the fill is a wash, not ink): `BLANCH_CONTRAST 4.5 → 3.35` in `ink.ts`. The design target is 3.35 because the real dark selected row is harsher than the 0.10 L allowance the formula assumes: measured from pixels the outline holds **3.10:1 minimum** over 3 grounds × selected/unselected × 6 hues × 1×/2× (`contrast-table.md`); worst cell dark/selected. Unselected rows: 4.2:1 (light), 3.9 (dark), 5.1 (Nord).
* Paleness (`contrast-table.md`, mean OKLab-L distance of the mark's visible pixels from the ground; smaller = paler): **error 0.187** vs resting 0.388, needs-you 0.403, working 0.408, finished 0.386 — error is the palest by a factor of two. The status strip draws the same mark ×0.875, so it follows.
* Footprint (ruling 6 of r4 kept): measured as the ENVELOPE (bounding box of pixels ≥ 1.3:1, so a washed fill counts): resting 192, working 184, needs-you 228, error 260, finished 264 px², ratio to the mean 0.85 / 0.81 / 1.01 / 1.15 / 1.17 (±25 %). The old "ink area ≥ 2:1" metric cannot be used for a pale mark; it is still printed for information.

### Ruling 2: the error rim is a broken border, never a scrollbar
`rim.ts case 'blanch'`: no pill, no fill, no dash gap. Four plain rects in `pal.blanch` (3.35:1): the top edge's left part `x .75 y .75 width '62%' h 1.2`, its right part `x '62%' width '38%'` with `transform translate(56 0)` (so there is ONE clear 56 px gap, then the line runs on to the end), and the two short returns `x .75 w 1.2 h 8.5` and `x '100%' w 1.2 h 8.5 translate(-1.95 0)`. It reads as the top edge of a box that is broken in one place; nothing on it can be mistaken for a thumb on a track.

### Ruling 3: the working rim: a clean outline and a few larger soft clouds
`rim.ts case 'clouds'`: the 1.2 px pill outline in the identity ink; inside it a faint tint (`fill-opacity .08`) and **five** clouds spaced evenly by an `objectBoundingBox` pattern tile (`x 0 y 0 width .2 height 1`, `patternContentUnits userSpaceOnUse`): one group (`opacity .55`, so overlaps do not darken) of lobes `(40,5.6,r3.2) (46.4,4.3,r4.2) (52.8,5.6,r3.4)` and a base `rect x37 y5.4 w19.6 h3.1 rx1.5`, repeated every 20 % of the width. Larger and fewer than the 15 px mini-clouds, soft, never crowded against a track. Static (no animation), so the CPU cost is that of one paint of the rim; the field still carries the moving clouds.

### Ruling 4: rest is calm
* Mark: the soft ink is lower in saturation: `SOFT_C = 0.07` (was 0.115, the identity hue is kept) at `SOFT_CONTRAST 3.35` (was 3.5); the oval is slightly wider so its envelope stays within ±25 % (dots `[12,5.4,r5.1] [12,8,r5.9] [12,10.6,r5.1]`, three paper holes unchanged in kind: `(10.4,5.2) r1.0`, `(13.6,8.4) r1.1`, `(10.8,11.2) r0.9`). Measured outline contrast ≥ 3.10:1 on all grounds.
* Rim: **one quiet hairline** in the soft ink: `rect x0 y9 width '100%' height 1 fill soft` (no pill, so no coloured double line). Needs-you (two striped chips) and working (clean outline + clouds) stay the loudest rims; error is the palest.

### Tests (write first; they fail on 7049668)
1. `ink.test.ts › the r5 inks`: `SOFT_C 0.07`, `SOFT_CONTRAST 3.35`, `BLANCH_CONTRAST 3.35`; for grounds `#fefefe #141416 #2e3440`, hues 100..350, rows unselected and selected (`light #f6f8fa/#d8e1f0, dark #17181c/#2a3142, nord #2e3440/#434c5e`): `contrast(soft, row) ≥ 3.05` and `contrast(blanch, row) ≥ 3.05`; `chroma(soft) < chroma(chroma ink)`.
2. `glyph.test.ts › error is the palest`: the error mark's extras are a `rect` fill chroma α .24 and a `path` stroke blanch 1.6 (path `M13 2.5 H3 V13.5 H21 V9`); no extra of the error mark has alpha 1 or a stroke wider than 1.6; the rasterised mark's mean lightness distance from the ground is lower than every other mark's (reuse the 96×64 helper with each extra's alpha applied).
3. `glyph.test.ts › resting`: the three dots are `[12,5.4,5.1] [12,8,5.9] [12,10.6,5.1]` pigment soft; and the optical envelope of all five marks stays within ±25 % of the mean (bounding boxes: resting 12×16, working ≈ 17×11, needs-you 19×12, error 18×11 plus its stroke, finished 22×10).
4. `rim.test.ts › r5 rims`: resting is exactly ONE node (a rect, `y h−1`, `height 1`, fill = soft) and no `rx`; blanch is exactly four rects, none with `rx`, `height`/`width` ≤ 1.2 for the three thin ones, exactly one has `transform translate(56 0)`, no `stroke-dasharray` anywhere, no `fill-opacity`; clouds has a `pattern` with `width 0.2` and `patternUnits objectBoundingBox`, a `g opacity .55` with 3 circles and 1 rect, a faint tint rect `fill-opacity .08`, and a 1.2 px pill outline; zebra and eyespot are unchanged (r4 tests).
5. Locked: `make contract` stays green; `git diff --exit-code 5358f8c HEAD -- contract tests/acceptance desktop/test/acceptance` stays empty.

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
