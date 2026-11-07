# Real-Desktop evidence (O7) — how it is made

One command makes `evidence/v2/` (dev only, never shipped). The product is not built: `desktop/plugin.js` of the commit is what runs.

```
make evidence                                   # HEAD (must be on origin): start → wait → fetch, ~12 min wall
tools/desktop/capture-remote.sh start <commit>  # hercules: niced, memory-capped systemd --user unit running capture.sh
tools/desktop/capture-remote.sh wait            # polls ≤ 8 min per call: exit 0 done, 3 still running, 1 failed
tools/desktop/capture-remote.sh fetch           # copies hercules' evidence/v2 into this repo
tools/desktop/capture.sh <commit>               # (on hercules) fetch the commit into ~/cf2/run/repo, unit tests, capture.ts
```

`capture.ts` (sandbox up → scenario → video/stills/pixels/perf → manifest → sandbox down):

* **Isolation** (asserted, never assumed): sandbox under `~/repos/hackathon/sandboxes/`, own `HERMES_HOME` and Electron userData,
  `HERMES_DESKTOP_ISOLATED_BACKEND=1`, `HERMES_DESKTOP_IGNORE_EXISTING=1`, credentials stripped, private Xvfb `:93`, the deterministic
  `mock_llm.py` on 127.0.0.1:18931, sandbox gateway ports checked disjoint from every Hermes listener present BEFORE launch
  (the full `ss -ltnp` snapshot is in `manifest.isolation`). `recordIsolation` throws if any of it breaks.
* **Scenario** (core's real paths, nothing poked into the plugin): the plugin is switched on through Capabilities ▸ Plugins; eight sessions:
  four resting (`[done]`), working (`[work]`, a stream that never ends), needs you (`[approve]`: a real approval, left open), error
  (`[fail]`: HTTP 400 through core's error path), finished unseen (`[brief]`: a 6 s turn that ends while another session holds the focus).
* **Dumps** are read from the DOM (`pagecode.ts`): sidebar rows and swatches, `<html>` attributes, status strip words, the composer rim's
  svg hash, the identity ring variable. **Stills** are grabbed from the REAL screen (`ffmpeg x11grab`, no mouse), region = the chat surface
  above the composer, exclusions = transcript text lines and painted parts (tight, ≤ 25 %), sidecars per `contract/RAW-EVIDENCE.md`.
  Extra, report-only stills: `*.bloom` (1.5 s after the state change) and `dark.*` (colour mode dark, best effort).
* **Perf**: 8 sessions, four 62 s windows (idle on/off, working off/on), renderer + GPU pids of the app tree, `/proc/<pid>/stat` at 1 Hz;
  the plugin is switched through the real Capabilities switch. Every window follows a toggle and a 20 s settle: the first switch-off leaves
  the Desktop ~1.5 pp busier for good, so the plugin is cycled off→on once before the first window (otherwise the windows are not comparable).
  The css sampler (10 Hz, sha256 of the plugin's owned `<style>`) runs in the working windows (also, as a no-op, in the off window).
* `measure.py` recomputes every manifest number from the raw files with the contract's own `instruments_py` / `raw_evidence`.
* Run-twice safe: everything is written to `evidence/v2.staging` and swapped in only when complete.
* The `vision` block is NOT written here: the conductor adds `raw/vision/response.txt` and `manifest.vision` after a separate critique.
