# Direction A: chromatophore field

Idea: the skin is a field of pigment sacs over a pale leucophore ground. Each logical pixel (XL: each disc) is one
sac that is either contracted (ground) or expanded in one of three tones of the session's identity hue.
Hue = who (OKLCh `hue_deg`, always inside [110, 340)); pattern = what. Amber and red appear only on needs-you and fault.
All colours are discrete flats (no gradients), so the look survives the 256 rung. Only `working` moves.

| state | pattern | biology source | bg rung (1x2 px/cell) | 256 colours | deutan / protan / tritan |
|---|---|---|---|---|---|
| idle | sparse isolated expanded sacs (stipple), static | Sepia close-up resting skin | scattered single cells on pale ground | tones stay distinct flats | density, not hue, carries it |
| working | one dense dark band drifting right, soft sparse edge; <=4 fps, <=48 colours, static under reducedMotion | Sepia passing-cloud display | 3-12 cell wide dark block, travelling | 3 tones + ground only | a moving dark block on pale: luminance only |
| review | irregular contiguous light/dark patches (value noise, 3 tones) | Sepia mottle | blobs 4-16 cells wide, 2 rows deep | tones are 3 fixed steps | patch shape, not colour |
| needs-you | vertical dark/pale bars (tall cells) with two dark-ringed amber eyespots, dark plate with amber `INPUT 4m` | Sepia/Metasepia zebra + eyespots | bars 1-2 cells wide, eyes = dark/amber/dark | amber and dark are far apart in the cube | bars + eyes are luminance-structure; text is literal |
| fault | blanched near-white field, dark-edged pale eye spots, red edge, red plate with white `ERROR 2m` | deimatic display | blank pale vs every other state, red edge column | red is a pure cube corner | blank vs barred is the INPUT/ERROR separator |
| unknown | neutral grey diagonal hatch, `?`; session.hue_deg null (degraded) claims no hue; labelled `unbound` | desaturated skin | checkerboard 1x2 | greys only | identical in all sims |

INPUT vs ERROR is separated by structure (barred dark vs blanched pale) before colour is considered.

80-col needs-you: M is 78 cells. The `INPUT 4m` plate (10 cells) takes the top-left, the name sits under it, and the bars plus
the amber eyes fill the remaining ~66 cells, so the pattern stays visible. Fault is the same. Eyes are dropped only if the free
width is under ~6 cells. On S (14 px pill) the alarm replaces the name: it is the durable signal, and the name is
elsewhere on the row. Name label is present on every M/S non-alarm state.

DEV previews (`tools/p1/preview.mjs`) are not evidence. No real-host render: `tools/p1/capture_matrix.py` is not on v22 yet;
P1-R renders this directory through the real hosts.
