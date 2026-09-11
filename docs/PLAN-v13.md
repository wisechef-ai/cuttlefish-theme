# v13 "C+" — one dominant family, small islands, narrow band, dithered

## Why

Three rounds of palette tuning failed because *readable* and *smooth* were
mutually exclusive on this surface. Measured cause:

    chromatic xterm-256 entries by lightness band
      L 0.15-0.25 :  1
      L 0.25-0.35 :  4
      L 0.35-0.45 :  8
      L 0.45-0.55 : 20

Legibility needs a NARROW lightness band (so the background under one line of
text barely varies). A narrow band in the dark region holds 1-4 entries per hue
family, so the palette collapses to 1-2 tones and looks like 144p pixel art.

Adam's reframe breaks the deadlock: **one dominant hue family with small
islands of others**. Needing shades of only ONE hue (not four) means the whole
palette fits inside a narrow band, and the islands supply colour interest that a
monochrome ramp would lack.

Dithering then multiplies the tone count without widening the band: two colours
per cell at 0/25/50/75/100% gives 5 perceived tones per pair, so ~4 in-band
entries become ~22 perceived tones.

Measured targets, from `/tmp/audit_c_plus.py`:

    TODAY                       contrast swing 3.06x   worst-contrast 5.15:1
    dominant + islands          swing 2.21x            worst 6.42:1
    + ground inside the ramp    swing 1.00-1.42x       <- legibility solved

## The four parts

1. **Dominant family** — each session gets ONE hue family carrying ~85% of lit
   cells. Derived from the session's identity hue, so sessions stay distinct.
2. **Islands** — the other chromatophore classes, ~12-15% of lit cells, in
   CLUSTERS not scatter (a lone off-hue cell is confetti; a 3-5 cell island is
   a marking).
3. **Narrow band + ground in the ramp** — the ground is the darkest step of the
   dominant family, not a separate near-black. No hole for text to fall into.
4. **Quadrant dithering** — `▖▗▘▝▌▐▀▄█` etc. mix two colours at sub-cell scale
   for intermediate tones and 4x shape resolution.

## Hard constraints (unchanged, these are regressions if broken)

- Sessions differ: >= 16 distinct palettes over 20 sessions.
- Acute signals are IDENTICAL across every session: exactly 1 needs_me set and
  1 fault set. Amber = waiting on you; red = failed.
- Acute state changes BOTH bars and mantle, drastically (0 shared indices with
  the session's resting palette).
- Everything behind text clears 3:1 post-quantisation against `#E8E6EA`.
- The bar is FILLED with the session's dominant colour, dots brighter-only,
  >= 3:1 dot/fill separation.
- Per-line cost <= 15 microseconds.

## Acceptance — measured over >= 200 sessions, all three signals

| # | contract | threshold |
|---|---|---|
| 1 | contrast swing per line | <= 1.6x |
| 2 | worst contrast vs `#E8E6EA` | >= 3.0:1 |
| 3 | dominant family share of lit cells | 0.75 - 0.92 |
| 4 | island share | 0.08 - 0.20 |
| 5 | island cluster size (mean) | >= 2.5 cells |
| 6 | perceived tones (incl. dither) | >= 12 |
| 7 | distinct session palettes / 20 | >= 16 |
| 8 | acute sets across sessions | exactly 1 each |
| 9 | acute vs resting shared indices | 0 |
| 10 | bar fill chroma | > 0.05 |
| 11 | bar dot/fill separation | >= 3.0:1 |
| 12 | per-line cost | <= 15 us |

## Dither and text

Dithering draws GLYPHS, so it cannot occupy a cell where text already sits.
Rule: the transcript's occupied cells use the flat narrow-band background
(contract 1 keeps them near-uniform); blank regions, margins and the bars get
the full dithered treatment. Quiet where you read, detailed where you do not.
