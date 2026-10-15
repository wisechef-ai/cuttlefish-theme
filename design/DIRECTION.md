# Locked direction: D — dots

**Locked 2026-10-15 by the P1 lead (card t_0c601204), on Adam's ruling in #tori:**
> "I imagine that the cuttlefish design can be simply a set of colloured dots without any sophisticated background"

This supersedes the three P1 candidates (a-chromatophore, b-disruptive, c-iridophore). They stay in
`design/directions/` as history and as harness references; nothing ships from them.

Module: `design/directions/d-dots/direction.mjs` · Frozen tokens: `packages/core/tokens.json` · Behaviour
contract: `tools/tests/test_p1_direction_d_dots.py`.

## The grammar

The whole visual is **chromatophores and nothing else**: a lattice of coloured dots on one flat,
terminal-dark ground (`#0e0f13`). No mantle silhouette, no shading layer, no texture under the dots.

- **Hue = identity.** Each session's dots are its OKLCh identity hue (arc [110°, 340°), never amber/red),
  in three lightness steps (L 0.58 / 0.66 / 0.74, C 0.135) so neighbouring dots read as separate organs.
- **Pattern = state.** State is only *which dots are open, closed or blanched*:

| state | body pattern (Sepia) | dots | text |
|---|---|---|---|
| idle | uniform stipple | all open, ~18 % closed at random | — |
| working | passing cloud | a band of closed dots drifts one dot per 0.25 s — **the only animation** | — |
| review | mottle | open/closed in soft blotches | — |
| needs-you | zebra + eyespots | alternating open/closed bands, two amber eyespots | `INPUT 4m` |
| fault | deimatic blanch | every dot opens pale; red dots on the margin | `ERROR 2m` |
| unknown | (no pattern claimed) | sparse grey dots on a diagonal, no identity hue | `?` |
| degraded (no binding) | as unknown | grey, no hue | `unbound` |

- **Scales.** XL (desktop field) draws round, anti-aliased dots on a hex lattice (pitch 7 internal px,
  radius 0.36·pitch, 4 coverage levels) at ≤ 57 600 internal px, upscaled with smoothing. M (TUI mantle,
  desktop chip) and S (TUI pill, desktop 4×2 swatch) are the same grammar with one dot per logical pixel.
  The 4×2 swatch carries no text and still shows ≥ 3 distinct working frames; narrow strips use a short
  cloud period so the cloud is never hidden under the name plate.
- **Motion.** Only `working` moves, ≤ 4 fps, ≤ 48 colours; `prefers-reduced-motion` freezes it.

## Why D fits the evidence

- Round 1 (G5 qwen + codex) found function passing everywhere but aesthetics capped by the TUI half-block
  *mantle* rendering (a body silhouette drawn in half blocks). D removes the silhouette entirely: in the TUI
  a dot is one cell pixel on a plain ground, which is what the terminal draws well.
- The frozen G2 identity metric (median OKLab per tile) needs the identity hue to own the tile. D keeps idle
  tiles ≥ 80 % open dots, so the tile median is the identity colour while the ground stays plain.

## Gate evidence

See the plan-doc `## P1 — as built` section and `p1/renders-d/` in the vault (real-host renders,
check_manifest, G2, G5). Adam's live verdict is G6.

## Consumers

P2 (core) implements the pattern function from `tokens.json` in `packages/core/domain/` and keeps this
module as its oracle; P3/P4/P5 adapters render the core's model and never re-derive colour or pattern.
