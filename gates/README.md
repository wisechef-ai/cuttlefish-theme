# gates/: P1 design gates (G2 deterministic, G5 blind vision)

Dev-only instruments (never imported by a shipping entrypoint). Thresholds are frozen in `tools/p1/CONTRACT.md` section 5 and mirrored in
`gatelib.FROZEN` / `g5lib`; a change is a logged deviation owned by the P1 lead, not a lane edit.

    python3.12 -m venv gates/.venv && gates/.venv/bin/pip install -r gates/requirements.txt
    gates/.venv/bin/python gates/g2.py <renders>/<direction>/manifest.json     # exit 0 PASS / 1 FAIL / 2 instrument error
    gates/.venv/bin/python gates/g5.py <renders>/<direction>/manifest.json [--backends qwen,glm] [--no-cache]

| file | job |
|---|---|
| `gatelib.py` | pure maths: WCAG contrast, OKLab / dE_OK, Machado-2009 CVD, manifest parsing, identity + static-proof checks |
| `dirtools.py`, `node/paint_dump.mjs` | run a direction module through `node` (authoredPairs, text-cell positions); write CVD images |
| `g2.py` | G2: writes `g2.json` + `g2.md` next to the manifest and `cvd/<kind>/...` simulations for G5 |
| `g5lib.py` | pure G5 parts: strict answer parsing, verdicts, confusion matrix, seeded shuffle, kill-rule round counter |
| `g5items.py` | what each blind call sees (legend sheet over one sample, identity sheet over one tile, aesthetic strips + photos) |
| `g5backends.py` | vision backends: default pair `qwen` (hercules qwen3.8-27b, local) + `glm` (zai glm-4.6v-flash, paced 3 s, 429/5xx backoff); optional `codex`, `openrouter`; `gemini:<m>` smoke only (20 req/day). Public renders / photos only |
| `g5cache.py` | raw-answer cache keyed by (backend, model, image sha256, prompt sha256) under `gates/.g5_cache/` (git-ignored); `--no-cache` forces fresh calls, cached answers are flagged `cached` in `g5_raw/` and counted in `g5.md` |
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
- G5 blindness: one image per call, fixed prompts, a throwaway cwd for `codex exec`; text policy (D-R2-5): identity masks all text; the plain legend keeps the alarm words
  (alarms carry literal text by contract) with session names masked; the three CVD legends mask all text (the state must be named from pattern).
  `--keep-alarm-text` / `--mask-alarm-text` override every legend variant and are for informational runs only; g5.md records the policy in force. Invalid, refused or errored answers count as FAIL for the item.

glm runs with thinking off by default (on at 1024 tokens the reasoning model burns its budget and returns an empty answer on ~1 in 5 items); `G5_GLM_THINKING=on` re-enables it with an 8192-token budget (the cache key records the setting). Empty replies are never cached.

Backend env: `G5_QWEN_MODEL` (default `qwen3.8-27b-heretic`), `G5_QWEN_URL`, `G5_GLM_MODEL` (default `glm-4.6v-flash`), `G5_GLM_MIN_INTERVAL` (3 s),
keys `HERCULES_API_KEY` / `GLM_API_KEY` from the environment or `~/.hermes/.env`.

Deviation (D-R2-4): Hermes' `vision_analyze` aux route cannot be driven headless (OpenRouter 400/404 on both homes; no Anthropic API key; OpenAI API
key without credits; Gemini free tier = 20 requests/day), so G5 calls two free/local vision models directly. `codex` stays as an optional substitute.
zai's free tier logs prompts: G5 only ever sends public renders, synthetic fixtures and openly licensed photos.
