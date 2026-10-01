# Direction B: b-disruptive (flamboyant graphic)

The idea: *Metasepia pfefferi* as graphic design. Flat, hard-edged colour only, with no gradients and no shading, so state is structure.
Identity is the ground colour (OKLCh at `session.hue_deg`, L .52 / C .13, with a light and a dark sibling of the same hue). Ink and paper are neutral.
Amber and red appear only on alarm states, so they never carry identity. Literal text sits on solid plates: alarm or `?` first, then the session name (name on M and S).
Only `working` moves, at 4 fps; every other state is byte-identical across t.

| state | pattern | biology | bg rung (1x2) / 256 colours | CVD |
|---|---|---|---|---|
| idle | regular dot lattice, ink dots on identity ground, every other row staggered | resting papillae | dots survive as vertical ticks, flat colours so no banding | structure only, hue not needed |
| working | one hard-edged ink mass with a bright leading edge sweeping across, stepped edge, 4 fps, <= 48 colours (it uses ~5) | passing cloud | a solid dark bar moving on a coloured strip | luminance only |
| review | blocky camouflage runs of 2..5 px in 3 identity tones, no equal neighbours | disruptive coat | patchy blocks, no bars or dots | tones differ in lightness, not just hue |
| needs-you | thick vertical zebra (identity / ink, period 5) plus amber ring eyespots with ink pupils, `INPUT 4m` on an amber plate | zebra display + ocelli | stripes + amber rings stay visible as amber ticks | amber vs ink is a luminance contrast; the literal text breaks any tie |
| fault | full paper-white blanch, red frame (tall cells) or red end caps, red eyespots, `ERROR 2m` on a red plate | deimatic | white strip with red ends; the opposite of every other strip | white vs dark is luminance; INPUT vs ERROR differ by pattern (stripes vs blanch), text, and plate |
| unknown | neutral grey diagonal hatch, `?` plate, no identity hue | no signal | diagonal weave | achromatic |

Degraded (no binding): the same hatch, with the name `unbound` on a neutral plate. It never shows an old state or hue.

80-col needs-you: M is 78 logical px wide. The alarm plate (`INPUT 4m`, 10 cells) takes the left edge; the name plate follows, then the stripes and 3 eyespots run across the rest. If the name does not fit, the alarm takes priority.
Previews (dev only, not gate evidence): vault `projects/cuttlefish-theme/p1/previews/b-disruptive/`.
