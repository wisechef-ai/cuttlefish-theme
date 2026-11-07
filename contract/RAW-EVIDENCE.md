# RAW evidence schema for the real-Desktop run (contract PART; closes luna F4 / F5 / F9)

Locked by `tests/acceptance/test_o7_part1_recompute.py` (+ `test_o8_part1_video_provenance.py`, which reads the same
manifest). The harness writes, under `evidence/v2/`, the locked `manifest.json` (shape: `test_o7_desktop_evidence.py`) **and** the
raw artifacts below. The part test **recomputes** every number the manifest claims from the raw files; a number that
cannot be recomputed is a failure. Loaders and validators: `tests/acceptance/raw_evidence.py`; pixel maths:
`tests/acceptance/instruments_py.py` (a port of `desktop/test/acceptance/instruments.ts`, pinned to it by
`test_instruments_py.py`). A harness should call the same two modules to emit its numbers.

```
evidence/v2/
  manifest.json
  raw/                                   every file below, and nothing else
    dom/<stored_id>.<state>.json         one DOM dump per session per state          (cf2-dom-dump/1)
    dom/idle-window.json                 a dump taken INSIDE the idle CPU window     (cf2-dom-dump/1)
    stills/<state>.png + <state>.json    state ∈ resting working needs_you error  (+ resting-idle)   (cf2-still/1)
    cpu/{idle,working}.{on,off}.csv      header exactly: pid,ts,cpu_pct
    cpu/working.field.csv                header exactly: ts,css_sha256
    vision/response.txt                  the vision model's raw reply text
```

## manifest additions (on top of the locked shape)

```jsonc
"capture": {
  "sessions": [{"stored_id": "…", "expected": "needs_you", "dom_state": "needs_you",
                "dom_dump": "dom/<stored_id>.needs_you.json"}],            // dom_dump: path relative to raw root
  "rows_total": 8, "rows_with_swatch": 8,
  "stills": [{"state": "resting", "path": "evidence/v2/raw/stills/resting.png", "sha256": "…",
              "meta": "stills/resting.json"},                                 // `meta` ⇒ the still is MEASURED
             {"state": "overview", "path": "evidence/v2/raw/stills/overview.png", "sha256": "…"}]  // no meta ⇒ hashed only
},
"field_pixels": {"resting": {"organs_detected": 612, "p95_dL": 0.041, "mean_dL": 0.03, "lowK": 0.1, "highK": 0.1},
                 "working": {…}, "needs_you": {…}, "error": {…}},          // all four states, every field recomputed
"perf": {"sessions": 8, "window_s": 60, "budget": {"idle_pp": 1.0, "working_pp": 6.0},
         "idle": {"on_pct": 2.0, "off_pct": 1.6}, "working": {"on_pct": 9.0, "off_pct": 5.0, "field_updates_per_s": 5.0}},
"vision": {"model": "…", "builder_models": ["…"], "file": "evidence/v2/raw/vision/response.txt",
           "verdicts": {"readable_at_a_glance": true, "five_states_distinguishable": true, "not_distracting_at_rest": true}},
"raw": {"root": "evidence/v2/raw",
        "files": [{"path": "dom/S1.resting.json", "sha256": "…"}],           // EVERY raw file, exactly; sha256 of its bytes
        "idle_window": {"dom_dump": "dom/idle-window.json"},
        "cpu": {"idle_on": "cpu/idle.on.csv", "idle_off": "cpu/idle.off.csv", "working_on": "cpu/working.on.csv",
                "working_off": "cpu/working.off.csv", "working_field": "cpu/working.field.csv"}}
```

`plugin_js_sha256` (locked O7.1) must equal the sha256 of `desktop/plugin.js` in this tree **and** of the `plugin_js_sha256`
field of every DOM dump.

## DOM dump — `cf2-dom-dump/1`

```jsonc
{"schema": "cf2-dom-dump/1", "stored_id": "…", "state": "needs_you",       // the scenario state this dump was taken for
 "focused": true,                                                           // was this session focused when dumped?
 "plugin_js_sha256": "…", "captured_at": 1700000000.5,                      // epoch seconds
 "html": {"data-cf-state": "needs_you"},                                    // data-cf-* attributes of <html>
 "row": {"data-cf-session": "…", "data-cf-state": "needs_you", "swatch_circles": 14},   // THIS session's sidebar row
 "rows": [ {"data-cf-session": "…"|null, "data-cf-state": "…"|null, "swatch_circles": 14}, … ],   // EVERY sidebar row
 "strip": {"text": "needs you"},                                            // the words the status strip shows
 "composer": {"rim": {"data-cf-state": "needs_you", "svg_sha256": "…"},    // the composer.top contribution's root + sha256 of its serialised <svg>
              "ring_vars": {"--dt-composer-ring": "…"}},                    // identity hue (R-S1 ruling 3), not a state signal
 "transcript_messages": 0}
```

Recomputed: `dom_state` := `row["data-cf-state"]` (must equal the manifest's, and the scenario `expected`);
`rows_total` := `len(rows)`, `rows_with_swatch` := rows with a session id and `swatch_circles > 0`; all dumps list the
same rows. Focused dumps (≥ 4 distinct states, incl. resting and needs_you): `html["data-cf-state"] == state`, the strip
text contains the state's default label (`contract/config-vectors.json`; resting's is `""`), strip texts differ per
state, `--dt-composer-ring` is set, `composer.rim["data-cf-state"] == state`, and the rim's `svg_sha256` differs across the
focused states (addendum R-S1: core pins the composer border with `!important`, so there is no border colour to record). A `finished_unseen` session cannot be focused (focusing clears it): its dump is judged by its row.

## Still sidecar — `cf2-still/1` (8-bit, non-interlaced PNG; colour type 0/2/4/6)

```jsonc
{"schema": "cf2-still/1", "state": "resting", "png_sha256": "…", "taken_at": 1700000010.0,
 "region": [x, y, w, h],                // the chat surface in the PNG; must cover ≥ 50 % of the image
 "exclude": [[x, y, w, h], …]}          // pixels ignored (composer, title bar, transcript text); ≤ 25 % of the region
```

Pixels → organs (`instruments_py.detect_organs`): crop to `region`, ignore `exclude`; ground = most frequent colour;
ink = |ΔL OKLab| to the ground ≥ 0.004; organs = 4-connected ink components of 4…5000 px; dot = centroid, r = √(area/π),
colour = mean colour, α = 1. Then `field_metrics`: `organs_detected`, `p95_dL`, `mean_dL` (O2 `lightnessStats`), `lowK`,
`highK` (O2 `banding` over the region size). The stills used for measuring show an **empty transcript** where the
region is not excluded. `resting-idle.png` is taken inside the idle `on` CPU window (`first_ts ≤ taken_at ≤ last_ts`).

## CPU sampler — `pid,ts,cpu_pct`

One row per pid per sample; `ts` epoch seconds, `cpu_pct` percent of one core (renderer + GPU pids; ≥ 2 pids). Per
timestamp the pids are summed; the mean over timestamps is `on_pct`/`off_pct` (± 0.01). Each of the four files spans ≥ 60 s with no gap > 2.5 s.
`working.field.csv` (`ts,css_sha256`) is the sha256 of the plugin's owned `<style>` text sampled at ≥ 8 Hz for ≥ 30 s,
inside the `working.on` window; `field_updates_per_s` = (number of changes) / span (± 0.05), and must be ≥ 4.

## Vision response

`vision/response.txt` is the reply as received, containing: a `model: <name>` line (= `vision.model`); each judged
still's full sha256 (every `capture.stills[]`); and exactly one line each of `readable_at_a_glance: yes|no`,
`five_states_distinguishable: yes|no`, `not_distracting_at_rest: yes|no`. At least 300 characters. The manifest's
`verdicts` are those lines, nothing else.

## Residual risk

A harness that fabricates the raw files themselves passes the part test; it cannot cheaply keep PNG pixels, sampler
timestamps, DOM dumps and the model's quoted hashes mutually consistent. M5 (sol) reads the harness that produced them.

## OPEN

- `finished_unseen` pixels are not measured in the field (it only shows in a swatch for an unfocused session); a swatch-crop measurement is not pinned.
- Classifier thresholds on real pixels are pinned only for resting and needs_you (as locked O7.5); working/error pixel thresholds are not.
