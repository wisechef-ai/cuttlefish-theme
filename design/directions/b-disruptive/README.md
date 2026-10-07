# Direction B: b-disruptive — "Metasepia flamboyant" (round 2)

**The idea, in five lines.**
1. The skin of a flamboyant cuttlefish, read boldly: a saturated identity-hue dermis that owns every tile, with high-contrast, soft-edged organic shapes on top.
2. One state grammar, drawn at two resolutions. At XL the dermis is layered: dense granules, broad soft mottle, pale leucophore streaks, a gently lit relief, and chromatophore sacs in three size classes whose expansion follows a domain-warped field.
3. At M and S (1–4 px tall) the same grammar is posterised into five flat identity tones (light, ground, mid, deep, ink). Shapes are crisp, sizes vary and the rhythm is hashed. Structure, not shading, carries the state, so it survives the bg rung, 256 colours and the CVD sims.
4. Hue = identity (OKLCh at `session.hue_deg`; the ground sits at the lightness where that hue holds the most chroma). Amber and red appear only on the two alarm states. No rectangles, straight stripes or regular grids: every motif is hashed or domain-warped.
5. The module is pure and deterministic: the seed is `lineage_id` and the clock is `t`. There is no `Math.random` and no `Date.now`. Only `working` moves (≤ 4 fps, ≤ 40 colours a frame); `reducedMotion` makes it static.

| state | pattern (XL / M·S) | biology | bg rung (1×2 px per tall cell) / 256 | CVD (deutan/protan/tritan) |
|---|---|---|---|---|
| idle | Chromatophore stipple: sacs in three sizes over the granular dermis. M/S: dark spots of three sizes at hashed spacing and height on the vivid ground. | Resting stipple: retracted vs expanded sacs, three size classes | Isolated dark dots on a flat identity strip. Flat tones, so there are no gradient steps to band at 256. | Dark dots on a mid-light ground. This is lightness structure, so it does not depend on hue. |
| working | A passing cloud: a soft, ragged dark wave of expanded sacs drifting across (wraps, 4 fps). M/S: a mid fringe and a deep core moving 5 px/s; the 4×2 swatch moves 1 px per frame. | Passing cloud (dark waves of chromatophore expansion) | One wide dark mass among the dots. It is the only strip that changes between frames. | A dark mass of lightness only |
| review | Two-scale mottle: pale leucophore blotches and dark patches. M/S: pale and deep patches whose size and spacing drift along the body. | Mottle (light/dark patches at two scales) | Large pale blocks alternate with deep blocks. It is the only identity strip with near-white areas. | Pale vs dark patches |
| needs-you | Wavy, tapering zebra bands of fully expanded sacs, plus amber soft-ringed eyespots (ink pupil). The literal `INPUT 4m` on an amber plate. | Intense zebra + ocelli | Regular dark bars plus wide amber blocks. Amber stays amber at 256. | Many narrow dark bars along the whole strip plus bright blocks, which is a different structure from fault |
| fault | Deimatic: the body blanches near-white, dark-ringed spots with red centres appear, and red flushes in from the margins. The literal `ERROR 2m` on a red plate. | Deimatic display (sudden blanch + dark-ringed spots) | A near-white strip with red ends and three dark-ringed spots: the only near-white strip | A pale strip with dark rings vs needs-you's dark bars. INPUT vs ERROR differs by structure (bars vs blanch), not only amber vs red. |
| unknown | A neutral wavy diagonal hatch, greys only, plus `?`. | No signal: no body pattern is claimed | A grey diagonal weave | Achromatic |

Degraded (no binding): the same hatch with `?` and the name `unbound` on a neutral plate. No identity hue (every pixel has chroma < 0.03) and never the last known state.

**Text.** Text sits on its own plates, in cell coordinates, starting one cell in from the left: the alarm or `?` first, then the name if it fits (M, the TUI pill and XL). The desktop 4×2 swatch returns `text: []` (D-R2-2). At 80 columns, `INPUT 4m atlas` takes 15 of 78 cells and the zebra plus three eyespots carry the rest.

**Identity (D-R2-1).** The vivid ground covers ≥ 65 % of an idle tile, so the tile median is the identity colour. The real-host G2 worst pair is 0.0262 @16 and 0.0260 @20, against a 0.020 threshold; round 1 measured 0.0190 / 0.0176.

**Cost.** M is 1–2 ms a frame. XL is about 0.2–0.45 s for the one cached frame of a static state. XL working takes about 0.57 s for its first frame (it builds two dermis layers, memoised per session and size), then about 45 ms a frame on a CPU core at 4 fps. P4's shader is the production path; this function is its oracle.

## Iteration log

Every capture was made through the real hosts with `tools/p1/capture_matrix.py --runtime upstream --display :102`, then validated with `check_manifest`. G2 was run on a copy of the capture. The probe is `explore-r1/run_g5x.py` (qwen3.8 only, `--tasks aesthetic`). It is exploratory and NOT a gate (D-R2-6). Each figure is the probe median by scale.

| round | change | check_manifest | G2 | probe XL | probe M | probe S | overall |
|---|---|---|---|---|---|---|---|
| r1 (round-1 design, `p1/explore-r1`) | flat hard-edged graphic | ok | FAIL (identity 0.0190/0.0176; swatch not animated) | 1 | 2 | 2 | 2 |
| iter1 | redesign: layered dermis at XL, posterised grammar at M/S, new tests | ok, 148 entries | **PASS** (0.0262 / 0.0260) | 3 | 2 | 2 | 2 |
| iter2 (final, this PR) | organic eyespot outlines, red flush instead of a frame, bolder XL zebra, rhythmic M mottle, cleaner M zebra, a structured 4×2 swatch for every state | ok, 148 entries | **PASS** (0.0262 / 0.0260) | 3 (min 2) | 3 (min 1) | 2 (min 1) | 2 |

Self-checks on the iter2 capture (vision, looked at directly):
- **XL next to a real *Sepia* photo (p3).** The rendered texture is instantly identifiable: it is a uniform cyan field with no body form or lighting, and its granules read as noise. This bar is **not** met.
- **M strips at the bg rung, named from pattern alone.** All seven are nameable: dots, a dark mass, pale/deep blocks, dark bars + amber blocks, a near-white strip with red ends, and two grey weaves (unknown and degraded are told apart only by their label, by design).
- **Needs-you vs fault under deutan.** These are different patterns: dense diagonal dark bars with bright ringed eyespots, against a pale empty strip with three dark-ringed spots and dark ends.

## Why the probe target (median ≥ 7 at each scale) is not met — measured, not guessed

- **S cannot reach 7 here.** The desktop swatch is 4×2 logical px, and the probe sees it as 8 nearest-upscaled blocks ("flat solid colour blocks"). The TUI pill is 14×2, and the contract requires the name and the alarm text on it, so most of its cells are text. Every S item scored 0–4 in every variant tried.
- **M is held down by text and dots.** The desktop chip (22×2, name + alarm text as DOM) scored 1–3 in every variant. The stipple (idle, working) scored 2–3 in every dot arrangement tried (eight variants: staggered, swelling, beads, rosettes). The probe calls dots "sparse blocky shapes" and rewards only continuous stripes or diagonals (zebra and hatch score 6). M has 21 items, and 7 chip + 4 idle/working strips sit at about 2, so a median ≥ 7 is not reachable without dropping the stipple that the state grammar mandates.
- **At XL, any hue cast costs about 4 points on a synthetic texture, but not on a photograph.** Measured on one wavy-hatch structure: grey scored 8, the same structure tinted at OKLCh C 0.03 scored 4, at C 0.06 scored 2 and at C 0.10 scored 3. A real *Sepia* crop scored 8, and the same crop hue-shifted to a saturated teal or purple still scored 8. So the qwen probe penalises tint only on synthetic textures. A direction whose identity is a saturated hue tops out at about 3–4 at XL under this instrument, while the neutral states (unknown/degraded) reach 6–8. The lead should weigh this when reading the two-family gate.

Dev evidence for the final iteration (real capture, `g2.md`, probe `g5.md`) is in the vault at `projects/cuttlefish-theme/p1/renders-r2-dev/b-disruptive/`.
