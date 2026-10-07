# c-iridophore: "iridophore night" (round 2)

The idea in 5 lines:
1. A dark-mode skin built in the animal's own layers. The base is a deep dermis in the session's identity hue (OKLCh), lit as relief.
2. On top sits an iridophore sheen. Its hue drifts within ±25° of the identity hue and is clamped inside the identity arc.
3. Chromatophore sacs come in three size classes on jittered lattices. Each sac opens at its own threshold of one domain-warped expansion field, so the patterns emerge rather than being drawn as rectangles.
4. **State is how the sacs and sheen organise.** Each state is one of: scattered glints, a drifting dark wave, two-scale patches, wavy bands with ocelli, a blanch, or nothing.
5. Amber and red appear only on the two alarm states. The degraded (unbound) mantle is pure grey and claims no hue.

Module: `direction.mjs`, pure ESM per CONTRACT §2, with no imports, timers or I/O.

Behaviour tests: `tools/tests/test_p1_direction_c_iridophore.py`. The tests drive the module via `node -e`, and none of them reads the source text.

Dev previews (not gate evidence): `node tools/p1/preview.mjs design/directions/c-iridophore out.png --rung half|bg --cols 80|120`.

## Three canvases, one skin

- **XL (the desktop field pane).** The host paints it at about ¼ size and upscales it smoothly. It shows a stretch of mantle seen from above. Fins run along both long sides with the pale marginal line, and dark night water lies beyond the ruffled fin edge. Every layer is drawn:
  - dermis relief
  - sheen filaments
  - leucophore points clustered by a low-frequency density field
  - sacs in 3 size classes

  The working frame is built from cached per-pixel tables, at about 25 ms per frame.
- **Strips (the TUI mantle `cols-2 × 2`, the TUI pill, the desktop chip).** These are only a few pixels tall, so the skin is drawn as its *rhythm*: one motif per state over a dermis that slowly swells and fades. Since iteration 5, no strip motif sits on a lattice. Glints, patches and ghosts are placed by seeded hash and noise fields. The seed comes from `lineage_id`.
- **Desktop swatch (4×2).** A jewel of the same skin: an identity gradient with one glint. It carries no text (D-R2-2). In working, a dark wave moves one pixel per frame, which gives 4 distinct frames at t = 0, .25, .5 and .75.

## Per state

| state | pattern | biology source | bg rung (1×2 px per tall cell) | 256 colours | deutan / protan / tritan |
|---|---|---|---|---|---|
| idle | **stipple**: leucophore glints scattered by a slow density field, so they form clusters and quiet stretches. Each glint is trailed by a dim sheen cell. | retracted-sac stipple of a resting *Sepia* mantle; leucophore white spots | irregular bright ticks on the identity ground | the ground takes the nearest cube colour; the glints stay near-white | the glints are luminance, so they survive all three |
| working | **passing cloud**: a soft dark wave of expanded sacs drifts through leaning sheen striations. This is the ONLY animated state. It runs at ≤ 4 fps with ≤ 48 colours per frame (one 48-step skin curve). reducedMotion freezes it at t=0. | *Sepia* / *Metasepia* passing-cloud display | one dark lump on a striated field | the lump stays one lump | the wave is luminance, so it survives |
| review | **mottle**: a domain-warped field at two scales. Large dark patches have a mid-tone rim, and small pale flecks sit in the light gaps. | *Sepia* two-scale mottle | irregular dark blocks with pale flecks | the three tones stay three cube colours | the structure is luminance, so it survives |
| needs-you | **zebra**: dark bands over leucophore white. The lean flips every band, so the bands look wavy and tapering. **Soft-ringed amber ocelli** sit about one per 30 cells (pupil, amber, rim, dark moat). The literal `alarm_text` plate is added. | *Sepia* zebra + *Metasepia* ocelli | the busiest, highest-frequency strip; the ocelli read as ringed pairs | the bars become white and black; amber becomes cube orange | tritan turns the amber pink, but the bars still name the state |
| fault | **deimatic blanch**: the pigment withdraws, so the field goes pale and flat with a few scattered ghost points. The margin flushes red: 2 + 1 cells at each end, plus the bottom row when h ≥ 3. The literal `alarm_text` plate is added. At XL, the blanch also shows scattered, uneven dark-ringed spots. | *Sepia* deimatic display | the only strip that is almost entirely bright and flat | bright grey + cube red | red goes olive under deutan and protan, so **brightness carries the state**: nothing else is bright and flat |
| unknown | **neutral hatch**: grey diagonal ticks on a dim ground, with no sheen and no sacs, plus `?` | none: the state claims no pattern | evenly staggered grey ticks | pure greys | grey is unchanged by every sim |
| degraded | the same hatch on a **pure grey** ground with no identity hue at all, plus `?` and `unbound` | n/a | as unknown | as unknown | as unknown |

INPUT never reads as ERROR because the two states sit at opposite ends of the structure axis. Needs-you is the busiest strip (bands and ringed eyes). Fault is the emptiest (flat bright field with a red edge). Their plates differ too: amber on black for INPUT, red on white for ERROR.

A known-but-stale session (`unknown` with a hue) keeps a dim identity ground (L 0.28, C 0.045) under the hatch. That way the who-needs-me strip can still say *who* went stale.

## Identity and text

The base lightness is set per hue: it is the lowest L at which the hue still carries ≥ 0.118 chroma. Hue never moves, because the gamut clip only reduces chroma.

- Idle tiles of the 20 fixture sessions stay ≥ ΔE_OK 0.020 apart (`test_identity_separates_twenty_sessions_on_idle_tiles`).
- No idle, working or review pixel with C ≥ 0.03 falls in the alarm arc [340°, 110°).
- The identity hue owns more than 50 % of an idle S tile (D-R2-1).

All text uses 4 fixed plates (`authoredPairs()`), each with contrast ≥ 4.5:1:

| plate | fg / bg |
|---|---|
| name | `#e8ecf1` / `#0c0f14` |
| INPUT | `#1a1000` / `#f2a516` |
| ERROR | `#ffffff` / `#b3121e` |
| `?` | `#0c0f14` / `#c9ccd1` |

M and the pill carry the session name. Alarms carry `alarm_text` verbatim, and the alarm plate is always first and always kept.

## The 80-col needs-you case

At 80 cols the mantle is 78 cells wide. Row 0 holds ` INPUT 4m ` (10 cells) and ` atlas ` (7 cells), starting at col 1. That leaves cols 18–77 of row 0 and **all of row 1** showing zebra bands and 2–3 ocelli.

On the 1-row mantle (fewer than 30 terminal rows), the plates take 17 of the 78 cells and 61 cells of zebra remain. If a plate doesn't fit, it drops its padding first. If it still doesn't fit, the name plate goes.

## Iteration log

Real host: capture_matrix with `--runtime upstream`, Xvfb :103, MemoryMax=8G.

The probe is the exploratory aesthetic probe (`run_g5x.py --backends qwen,qwenb --tasks aesthetic`). It is NOT a gate. The table gives its median per scale across both backends. The target is median ≥ 7 and no score < 6 at each of XL, M and S. The real-animal anchor photos scored 9 on every run.

| iter | commit (pre-rebase branch hash) | change | check_manifest | G2 | probe XL / M / S (median) | overall median / min |
|---|---|---|---|---|---|---|
| 1 | 099ee00 | layered skin field (sacs ×3, sheen, leucophores, fins); strips still gradient-like | exit 0 | PASS | 4 / 2 / 2 | 2 / 1 |
| 2 | ea5be1a | lit XL mantle, rhythmic strip motifs | aborted mid-run, superseded by iter 3 | n/a | n/a | n/a |
| 3 | 58621a8 | strips drawn as rhythm (lattice stipple, striation cloud, two-scale mottle, flip-lean zebra) | exit 0 | PASS | 3 / 3 / 2 | 3 / 1 |
| 4 | c0ce393 | XL working from cached tables, continuous dome, review flecks on the bg rung | exit 0 | PASS | 3 / 3 / 2 | 3 / 1 |
| 5 | 857fa28 | strips lose their lattices (density-clustered glints, warped two-scale mottle, scattered ghosts) | exit 0 | **FAIL** IDENTITY_DELTA_E_20 (worst pair dE_OK 0.0165 < 0.02) | 3 / 3 / 2 | 2 / 1 |

Iteration 5 was **reverted**: it broke G2 identity separation and did not raise the probe. The shipped module is the iteration-4 skin (`direction.mjs` identical to c0ce393). Iteration 4 is the final evidence: G2 PASS, probe XL 3 / M 3 / S 2, overall median 3, min 1.

### Where it falls short, and why

The probe target is **not met**. The final iteration-4 numbers are XL 3, M 3, S 2 (medians), with min 1 at every scale, against a target of median ≥ 7 and none < 6. I have not rounded these up. The deterministic bar is met: G2 PASSes on the real-host capture, and every state is nameable at the bg rung, at 256 colours and under the CVD sims. I checked needs-you vs fault under deutan by eye: busy bands with ringed spots vs flat pale with a red edge.

- **XL (3):** the critic credits "organic, layered striations" and "mottled texture with depth". It still calls the result monochrome, high-contrast and too abstract. In the self-check next to `gates/photos/p1.jpg`, vision named the render instantly ("flat monochrome teal, regular wavy striations, dotted noise, no 3D form"). Bar item 1 is therefore **not cleared**. The skin has layers but no body: it has no form shading of a three-dimensional animal and no hue variation beyond ±25°. A real *Sepia* shows browns, whites and iridescent greens at once. The identity-hue rule (L7) forbids most of that range by design.
- **M (3):** the TUI mantle reached 6 on several strips (working, needs-you, review, unknown at 80 cols). It falls to 2–3 on the desktop chip, where the name and alarm plates cover most of a ~20-cell strip. The critic reads that strip as "a flat UI strip of text and colour blocks". The contract requires the plates (alarm text verbatim; M carries the name), so little skin is left to judge.
- **S (2):** the desktop swatch is 4×2 = 8 pixels, and the TUI pill is mostly its text plate. The critic calls both "flat solid colour blocks" and "a text label". I don't believe an 8-pixel tile can score ≥ 7 on "richly patterned" under this prompt. The sibling directions (a, b) also sit at S = 2 on the same probe. That suggests a ceiling of the canvas, not of this direction alone.
