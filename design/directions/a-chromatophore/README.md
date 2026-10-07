# Direction A, round 2: "Sepia dermis"

Idea in five lines:
1. One pure skin function, sampled at every scale, in body space (a = along the long side, b = across it).
2. Layered like real *Sepia* dermis: a leucophore ground tinted in the identity hue, iridophore sheen streaks and white flecks, and three size classes of chromatophore sacs that expand as whole organs.
3. Each state is an expansion field over those sacs (multi-scale, domain-warped), so patterns emerge from sac expansion, not from drawn shapes.
4. XL is a macro of the dorsal mantle: organised dermal grain, folds and papillae under a lit relief with a wet highlight, a convex body, the pale mantle-edge line and a rippled fin. It is painted small and upscaled smoothly (D-R2-3), with muted natural chroma.
5. The M/S strips treat their centre line as the body midline. Every layer is bilaterally mirrored, and the zebra bands chevron at the midline. Hue is identity (OKLCh `hue_deg`), and amber and red appear only on alarms.

## States

| state | pattern | biology source | bg rung (1x2 px/cell) | 256 colours | deutan / protan / tritan |
|---|---|---|---|---|---|
| idle | sparse fine sacs gathered in loose wavy rows on a tinted ground; static | resting *Sepia* stipple: fine spots along growth lines | single dark cells in loose rows | the ground and the dots are far apart in L | dots on a calm ground: luminance only |
| working | idle, plus a soft dark wave of fully expanded sacs drifting along the body. Two waves, half a span apart. Steps at 4 fps, <= 42 colours, static under reducedMotion | passing cloud | a 10-16 cell dark band that moves | the band is 3-5 L steps darker | moving dark band: luminance only |
| review | dark blotches repeated on a loose warped lattice, with small pale dapples between them (two scales) | *Sepia* mottle | blotches 3-6 cells wide | blotch vs dapple is about 0.25 L apart | patch shape, not colour |
| needs-you | wavy, tapering transverse bands that chevron at the midline, on a white leucophore ground; soft-ringed amber eyespots (pale halo, dark ring, amber iris); dark plate with amber `INPUT 4m` | zebra + eyespots (*Sepia* / *Metasepia*) | bars 2-4 cells wide, eyes dark/amber/dark | amber and dark sit far apart in the cube | barred dark field: structure, not hue |
| fault | sudden blanch (every sac a pinpoint), soft dark rings around blanched centres, red flush at the margin; red plate with white `ERROR 2m` | deimatic display | almost all pale, a few ring spots, red end column | pale field + red corner of the cube | blanched pale field vs barred dark field is the INPUT/ERROR separator (unit test: needs-you dark fraction > 2x fault + 0.1) |
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

After iter2, the merged module adds two pixel-level fixes that were not re-captured: the arc-safe hue drift and the shadow desaturation (see the unit tests).

Calibration runs (dev, same prompts and backend, repeated 3-5x):
- Real *Sepia* skin crops scored about 1-2 when downsampled to the M/S geometry (118x4 / 14x2) and 4-6 when downsampled to XL size.
- A crisp chevron strip scored 8 at M; smooth sine bands scored 6; a smooth gradient scored 2.
- The same lattice texture scored 8 tinted muted and 3 tinted saturated cyan.
- On identical images the probe was bimodal under load (8 / 3 / 2).

Where this falls short, and why: the probe target (median >= 7, none < 6 at each scale) is **not met**.
- XL: the best dev states reach 6-8 (working, review, needs-you), but idle and fault stay at 2-4. Idle reads as "regular, ribbed, metallic" and fault as "artificial rings".
- M/S: these are block strips with text plates, and the probe scores them about 2-4 whatever the pattern. Its ceiling for any naturalistic block strip, measured on real skin, is about 2, and only crisp geometric rhythm (chevrons) scores higher.
- The 4x2 desktop swatch is 8 flat blocks and cannot score as "richly patterned".

Next lever, measured but not yet captured on the real host: a finer, weaker dermal grain (amplitude 0.45, period 2.6) moved the XL dev median from 3 to 4.

## Files

- `direction.mjs`: the module (CONTRACT §2). It is pure, with no imports, no `Math.random` and no `Date.now`. The clock is `t` and the seed is `session.lineage_id`.
- `tools/tests/test_p1_direction_a_chromatophore.py`: behaviour tests through `node -e`. They never read source text.
