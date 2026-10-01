# c-iridophore: "iridophore night"

The idea in 5 lines:
1. The mantle is a deep, dark field in the session's identity hue (OKLCh, chroma ≈ 0.12–0.15).
2. A second layer of bright, low-chroma sheen (iridophores/leucophores) sits over it, and a pale fin-edge line runs along the bottom row.
3. **State is the structure of the sheen layer**: dots, one band, patches, bars, or none. Shading never carries meaning.
4. Alarm states break the layering: needs-you turns into hard sheen/dark bars with amber eyes, and fault blanches the whole mantle bright with a red margin.
5. Unknown has no sheen at all, just a neutral grey hatch and a `?`. The degraded (unbound) mantle is pure grey and claims no hue.

Module: `direction.mjs` (pure ESM, CONTRACT §2). Behaviour tests: `tools/tests/test_p1_direction_c_iridophore.py`.
Dev previews (not gate evidence): `node tools/p1/preview.mjs design/directions/c-iridophore out.png --rung half|bg --cols 80|120`.

## Per state

| state | pattern | biology source | bg rung (1×2 px/cell, 10×22 cells) | 256 colours | deutan / protan / tritan |
|---|---|---|---|---|---|
| idle | **stipple**: isolated single-pixel sparkles (no two touch) on the deep base, plus the fin line | leucophore white spots on a resting *Sepia* mantle | single bright cells scattered across 2 rows, each one a tall white tick | the base bands to the nearest cube colour, and the sparkles stay near-white | sparkles are a luminance cue, so all three sims keep them |
| working | **passing cloud**: one wide, slanted luminous band drifting left→right at ~6 cells/s, quantised to 4 fps and 9 tones (measured ≤ 10 colours per frame across all 20 sessions) | the "passing cloud" chromatophore wave of *Sepia*/*Metasepia*, read here as a sheen band | one soft bright lump about 20 cells wide on a plain field | the band's ramp collapses to 3–4 steps but stays one lump | luminance lump, so it survives all three |
| review | **mottle**: three-tone cloudy patches (deep / base / light), with blobs several cells wide | *Sepia* mottle display | irregular light and dark blocks 3–10 cells wide | three tones stay three cube colours | the patches are a luminance structure, so they survive |
| needs-you | **zebra**: regular 2-cell sheen/dark vertical bars, plus **amber eyespots** (one per ~30 cells) in a dark moat, plus a literal `INPUT 4m` plate | *Sepia* zebra display + *Metasepia* ocelli | the highest-frequency regular pattern in the set; the eyes show as amber pairs | bars become white/black, amber becomes cube orange | the bars carry the meaning. Under tritan the amber turns pink, but the bars still name the state |
| fault | **deimatic blanch**: the whole field goes near-white, with red ends (2+1 cells) and a red fin line, plus a literal `ERROR 2m` plate | *Sepia* deimatic display (sudden blanch + dark-ringed margin) | the only strip that is almost entirely bright and flat | bright grey + cube red | red reads as olive/brown under deutan/protan, and **brightness carries the meaning**: no other state is bright and flat |
| unknown | **neutral hatch**: grey diagonal ticks on a dim ground, a dark bottom band instead of the fin line, no sheen, plus `?` | no pattern claimed (the animal is not reporting) | evenly staggered grey ticks | pure greys | grey is unchanged by every sim |
| degraded (no binding) | the unknown hatch on a **pure grey** ground (no identity hue at all), plus `?` and the name `unbound` | n/a | as unknown | as unknown | as unknown |

A known-but-stale session (`unknown` with a hue) keeps a dim identity ground (L 0.30, C 0.05) under the
grey hatch, so the who-needs-me strip can still say *who* went stale. The degraded mantle claims nothing.

Why INPUT never reads as ERROR: needs-you is the **busiest** strip (hard bars every 2 cells) and fault
is the **emptiest** (flat bright). They sit at opposite ends of the structure axis, so a sim or the
256 rung can remove hue and they still differ. Their plates differ too (amber/black vs red/white).

## Identity

The base lightness is per hue: the lowest L at which the hue still carries ≥ 0.118 chroma. Blues and
violets sit at L 0.40, while the narrow-gamut greens and teals rise to about 0.6. Hue never moves,
because the gamut clip only reduces chroma. On idle tiles at the bg rung, the 20 fixture sessions are
≥ ΔE_OK 0.020 apart by median OKLab (the test `test_identity_separates_twenty_sessions_on_idle_tiles`
holds this). No idle/working/review pixel with C ≥ 0.03 falls in the alarm arc [340°, 110°).
The light olive at h≈115° is the closest any identity colour gets to amber, and it still sits outside the alarm arc.

## Text

All text uses 4 fixed plates (`authoredPairs()`). Each is ≥ 4.5:1, and every emitted text pair is one of them:
name `#eef1f5/#0b0e13`, INPUT `#1a1000/#f2a516`, ERROR `#ffffff/#b3121e`, `?` `#0b0e13/#c9ccd1`.
M and S carry the session name. Alarms carry `alarm_text` verbatim.

## The 80-col needs-you case

At 80 cols the mantle is 78 cells. Row 0 holds ` INPUT 4m ` (10) + ` atlas ` (7) starting at col 1, so
cols 18–77 of row 0 and **all of row 1** still show zebra bars and 2–3 amber eyespots. On the 1-row
mantle (< 30 terminal rows) the plates take 17 of 78 cells and 61 cells of zebra remain. If a plate
doesn't fit, it drops its padding first, then the name plate goes. The alarm plate is always first and
always kept.
