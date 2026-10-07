# gates/: P1 design gates (G2 deterministic, G5 blind vision)

Dev-only instruments (never imported by a shipping entrypoint). Thresholds are frozen in `tools/p1/CONTRACT.md` section 5 and mirrored in
`gatelib.FROZEN` / `g5lib`; a change is a logged deviation owned by the P1 lead, not a lane edit.

    python3.12 -m venv gates/.venv && gates/.venv/bin/pip install -r gates/requirements.txt
    gates/.venv/bin/python gates/g2.py <renders>/<direction>/manifest.json     # exit 0 PASS / 1 FAIL / 2 instrument error
    gates/.venv/bin/python gates/g5.py <renders>/<direction>/manifest.json [--backends a,b]

| file | job |
|---|---|
| `gatelib.py` | pure maths: WCAG contrast, OKLab / dE_OK, Machado-2009 CVD, manifest parsing, identity + static-proof checks |
| `dirtools.py`, `node/paint_dump.mjs` | run a direction module through `node` (authoredPairs, text-cell positions); write CVD images |
| `g2.py` | G2: writes `g2.json` + `g2.md` next to the manifest and `cvd/<kind>/...` simulations for G5 |
| `g5lib.py` | pure G5 parts: strict answer parsing, verdicts, confusion matrix, seeded shuffle, kill-rule round counter |
| `g5items.py` | what each blind call sees (legend sheet over one sample, identity sheet over one tile, aesthetic strips + photos) |
| `g5backends.py` | the two vision backends (`openrouter`, `codex`); public renders / photos only |
| `g5.py` | G5 runner: `g5.json`, `g5.md`, `g5_raw/<backend>/*.json`, appends to `g5_rounds.json` |
| `g5_prompts/*.txt` | fixed prompts, no design vocabulary (the neutral legend labels appear only in `legend.txt`) |
| `photos/`, `fetch_photos.py` | openly licensed real-animal anchors (see `photos/LICENSES.md`) |
| `tests/` | unit tests for the pure parts + the instruments proven on `fixtures/good` and `fixtures/bad` (synthetic renders, not host evidence) |

How the rendered numbers are taken (so a reviewer can reproduce them):

- Rendered text contrast: the direction's `paint().text` gives each string's cell box (11 x 23 px cells); the cell's most common colour is
  the background, the mean of the ~4 % of pixels farthest from it is the glyph colour. Half-truecolor and 256 rungs only.
- Identity: per tile of the 16/20-session grids, the per-channel median OKLab with the text cells masked out; nearest pair dE_OK >= 0.020.
  The report also carries a non-gating `informational_pigment_only` figure (median of non-background pixels) because a sparse-pigment
  pattern on a pale ground has a tile median that is just the ground.
- Static proof: single-session frame groups; the desktop sidebar mixes all six states, so it is not judged.
- G5 blindness: one image per call, fixed prompts, a throwaway cwd for `codex exec`; text is masked out of the identity task, kept in the
  legend task (alarms carry text by contract). Invalid, refused or errored answers count as FAIL for the item.
