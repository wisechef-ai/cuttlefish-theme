# Direction A, round 2: "Sepia dermis"

Idea in five lines:
1. One pure skin function, sampled at every scale, in body space (a = along the long side, b = across it).
2. Layered like real *Sepia* dermis: a leucophore ground tinted in the identity hue, iridophore sheen streaks and white flecks, and three size classes of chromatophore sacs that expand as whole organs.
3. Each state is an expansion field over those sacs (multi-scale, domain-warped), so patterns emerge from sac expansion, not from drawn shapes.
4. XL is a macro of the dorsal mantle: organised dermal grain, folds and papillae under a lit relief with a wet highlight, a convex body, the pale mantle-edge line and a rippled fin. It is painted small and upscaled smoothly (D-R2-3), with muted natural chroma.
5. The M/S strips treat their centre line as the body midline. Every layer is bilaterally mirrored, and the zebra bands chevron at the midline. Hue is identity (OKLCh `hue_deg`), and amber and red appear only on alarms.
6. Since iter5, M (TUI mantle, desktop chip) draws the same biology as **crisp sac bands**: one tone per cell (pale leucophore ground, a rim of half-expanded sacs, a band of expanded sacs). At 2-4 cells tall the sampled skin collapsed into a blocky mosaic. S (pill, 4x2 swatch, identity grid tiles) is unchanged, byte for byte, so G2 is untouched.
7. Since iter5, XL idle, fault and needs-you replace the single diagonal grain with growth lines that turn: the isolines of a warped low-frequency field. Idle adds a faint light mottle and fewer stipple sacs, and needs-you bands darken as continuous pigment with smaller eyespots. XL working, review and unknown are unchanged.

## States

| state | pattern | biology source | M since iter5 (crisp, one tone per cell; also the bg rung) | 256 colours | deutan / protan / tritan |
|---|---|---|---|---|---|
| idle | sparse fine sacs gathered in loose wavy rows on a tinted ground; static | resting *Sepia* stipple: fine spots along growth lines | thin waving lines of sacs, period 10 | the ground and the dots are far apart in L | dots on a calm ground: luminance only |
| working | idle, plus a soft dark wave of fully expanded sacs drifting along the body. Two waves, half a span apart. Steps at 4 fps, <= 42 colours, static under reducedMotion | passing cloud | breathing wavefronts of expanded sacs drift one cell per frame | the band is 3-5 L steps darker | moving dark band: luminance only |
| review | dark blotches repeated on a loose warped lattice, with small pale dapples between them (two scales) | *Sepia* mottle | two-scale bands: a wide blotch band, a narrow one, pale between | blotch vs dapple is about 0.25 L apart | patch shape, not colour |
| needs-you | wavy, tapering transverse bands that chevron at the midline, on a white leucophore ground; soft-ringed amber eyespots (pale halo, dark ring, amber iris); dark plate with amber `INPUT 4m` | zebra + eyespots (*Sepia* / *Metasepia*) | crisp chevrons (period 7) meeting at the midline, amber eyes | amber and dark sit far apart in the cube | barred dark field: structure, not hue |
| fault | sudden blanch (every sac a pinpoint), soft dark rings around blanched centres, red flush at the margin; red plate with white `ERROR 2m` | deimatic display | blanched, faint growth lines, ring spots, red end column | pale field + red corner of the cube | blanched pale field vs barred dark field is the INPUT/ERROR separator (unit test: needs-you dark fraction > 2x fault + 0.1) |
| unknown | neutral grey warped diagonal hatch, `?`; degraded (no binding) claims no hue and is labelled `unbound` | desaturated skin | diagonal steps | greys only | identical in every sim |

The desktop swatch (4x2) carries no text (D-R2-2). There, working is a cloud crossing the swatch, a step per quarter second.
The XL pane carries only the alarm text or `?` in CSS px. It shows the focused session, whose name is already on screen,
and the exploratory probe was reading the name label as content ("quill" became "a feather quill").

Identity (D-R2-1): the idle ground sits at the lightness in [0.72, 0.80] where the hue has the most chroma available, and asks for C 0.15 (clipped to gamut per pixel).
The hue owns more than 50 % of every idle tile (unit test). On the real host, the G2 nearest pair is about 0.024 at 16 and 20, against a threshold of 0.020.
XL hue drift never moves past the session hue toward the arc ends, and deep shadow desaturates, so no XL pixel leaves [110, 340).

Cost: static frames and layers are memoised per (scale, size, state, session). A working frame only evaluates the cloud
and blends two precomputed coverage layers: about 4-5 ms at M (118x4) and about 150 ms at XL (180x287) on this host. XL working is the
remaining hot spot, and the P4 shader takes it over.

## Iteration log (DEV evidence; the lead's gate runs on P1-R2's batched render)

Probe = `p1/explore-r1/run_g5x.py`, qwen only, `--tasks aesthetic` (NON-gate, D-R2-6). The six anchor photos score 9 on every run.

| round | module | real-host capture | G2 | probe median (min) XL / M / S |
|---|---|---|---|---|
| r1 (round 1, for reference) | v22 @4cb09e6 | p1/renders | FAIL (identity 0.000) | 0 / 2 / 2 |
| iter1 | 7c1222f + live edits during the run (mixed) | 148 entries, check_manifest 0 | PASS, identity 0.0242 @16 | 4 (2) / 2 (2) / 2 (1) |
| iter2 | 5d4a138 | 148 entries, check_manifest exit=0 | PASS, identity 0.0254 @16 | 4.0 (2) / 2.0 (1) / 2.0 (1) |
| iter3 | f8f112b (merged v22 @4f64dec incl. arc-safe drift + shadow desaturation, plus finer/weaker XL grain amp 0.45 period 2.6) | 148 entries, check_manifest exit=0 | PASS, identity 0.0254 @16 | 7.0 (2) / 2 (1) / 2.0 (1) |
| iter4 (rejected, not merged) | 00ff565 (branch agent/tori/cf2909-p1-da2-iter4): the periodic diagonal grain replaced by an isotropic pebbled grain, plus an isotropic warped relief | 148 entries, check_manifest exit=0 | PASS, identity 0.0260 @16 | 3.5 (2) / 3.0 (1) / 2.0 (1) |
| iter5 (shipped) | 01dc276: XL growth lines that turn in idle/fault/needs-you only, idle light mottle, continuous zebra + smaller eyes; crisp M sac bands; S unchanged | 148 entries, check_manifest exit=0 | PASS, identity 0.0253 @16 | 8.0 (2) / 3.0 (2) / 2.0 (1) |

iter3 re-captures the two pixel fixes added after iter2 (the arc-safe hue drift and the shadow desaturation) on the real host, together with the finer grain. The XL scores per backend were qwen 6 and qwenb 8. Per state, on both backends: working, review and unknown scored 8, degraded 6/8, needs-you 3, idle 2 ("regular diagonal ribbed") and fault 2 ("mechanical diagonal lines").

Calibration runs (dev, same prompts and backend, repeated 3-5x):
- Real *Sepia* skin crops scored about 1-2 when downsampled to the M/S geometry (118x4 / 14x2) and 4-6 when downsampled to XL size.
- A crisp chevron strip scored 8 at M; smooth sine bands scored 6; a smooth gradient scored 2.
- The same lattice texture scored 8 tinted muted and 3 tinted saturated cyan.
- On identical images the probe was bimodal under load (8 / 3 / 2).

Where this falls short, and why: the probe target (median >= 7, none < 6 at each scale) is **not met**.
- XL (iter3): the median reaches 7, but the minimum is 2. Idle and fault score 2 and needs-you 3; the probe reads them as regular, mechanical diagonals.
- M/S: these are block strips with text plates, and the probe scores them about 2-4 whatever the pattern. Its ceiling for any naturalistic block strip, measured on real skin, is about 2, and only crisp geometric rhythm (chevrons) scores higher.
- The 4x2 desktop swatch is 8 flat blocks and cannot score as "richly patterned".

The finer, weaker dermal grain (amplitude 0.45, period 2.6) was captured in iter3 and moved the real-host XL median from 4 to 7. XL still misses the bar on the minimum: idle, fault and needs-you score 2-3 because the probe reads the diagonal growth-line rhythm as mechanical. iter4 tried to break that regularity everywhere with an isotropic pebbled grain. It lost the striated look that carried working, review and unknown to 8, and the XL median fell to 3.5 with idle still at 2, so it was reverted. iter3 remains the shipped module and the vault evidence. The next lever is to break the diagonal per state, only in idle, fault and needs-you. M and S stay at 2-3. The cross-direction evidence says this is structural, not specific to this design: in the R2 dev runs, the bold-graphic b-disruptive and the dark-iridescent c-iridophore also score M 2-3 and S 2 on the same probe. The reasons the probe gives at M/S are "flat, low-resolution pixel strip, mechanical", and for the 4x2 desktop swatch "flat vertical colour bands". That swatch is 8 pixels, which physically cannot carry rich pattern.

### iter5 (P1-DA2b, t_83a55a9b)

Per state on the real host, qwen / qwenb, XL: fault 6/6 (was 2), needs-you 8/8 (was 3), working 8/8, review 8/8, unknown 8/6, degraded 8/6, **idle 2/2 (unchanged)**. The XL minimum is still 2, and only idle is below 6. Across 12 dev variants, idle scored 4-8 on other sessions but never above 4 on the captured session (quill, hue 207, cyan). The probe reads it as "speckled, granular, microscopic", and earlier as "metallic sheen". This matches the earlier calibration: the same texture scored 8 muted and 3 tinted saturated cyan.

M split per ruling R5 (the probe aim covers XL and the TUI M mantle only, as a dev signal): TUI mantle median 3.0, min 2 (n 28; iter3 about 2-3). The desktop chip has median 2 and S median 2; those are judged on function, not the probe.
The crisp-strip hypothesis, tested on dev synthetic strips with real hues and labels: crisp rhythmic sac bands plateau at 6 for idle, working, review and fault, and chevron zebra with amber eyes reaches 8. Grey (unknown and degraded) scores 2-4. The best synthetic 4x2 swatch (a checker) scored 4, the best pill 4, and the best desktop chip 4. So crispness lifts M from the naturalistic ceiling of about 2, but not to 7, and the module on the real host lands at a median of 3. Probe noise between the two backends and between near-identical strips is ±3, as in the earlier calibration.
Per ruling R5, no further redesign rounds were started.

## Files

- `direction.mjs`: the module (CONTRACT §2). It is pure, with no imports, no `Math.random` and no `Date.now`. The clock is `t` and the seed is `session.lineage_id`.
- `tools/tests/test_p1_direction_a_chromatophore.py`: behaviour tests through `node -e`. They never read source text.
