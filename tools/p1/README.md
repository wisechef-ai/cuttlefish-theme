# tools/p1: real-host render harness

`capture_matrix.py` renders a direction (`design/directions/<id>`) through the real hosts and writes
`manifest.json`; `check_manifest.py` validates it. The contract is `CONTRACT.md`.

## Run prerequisites (the harness installs none of these)

1. **Python with `pyte` and `Pillow` importable in the interpreter that runs `capture_matrix.py` / `check_manifest.py`**
   (`pip install -r tools/requirements-capture.txt`, ideally in a venv). Without them the TUI backends and the PNG
   crops fail.
2. **`@playwright/test` resolvable from `tools/`** for the desktop host: `cd tools && npm ci`, or symlink an existing
   `node_modules` that carries it (for example a built Hermes checkout's) to `tools/node_modules` (git-ignored).
3. A built Hermes checkout (`apps/desktop/dist` + `ui-tui/dist/entry.js`), selected with `--runtime installed|upstream|<path>`;
   never edit or build inside the installed one.
4. A private X display for the desktop and terminator hosts (never `:1`), e.g. user-space Xvfb:
   `Xvfb :104 -screen 0 1920x1200x24 -nolisten tcp &`, then pass `--display :104`. Wrap heavy runs in
   `systemd-run --user --scope -p MemoryMax=8G`.

```bash
python tools/p1/capture_matrix.py --direction design/directions/_ref --out /tmp/renders --display :104
python tools/p1/check_manifest.py /tmp/renders/_ref/manifest.json   # exit 0 = complete and valid
```

## Tests

```bash
python -m pytest tools/tests/test_p1_*.py          # manifest checker + harness outputs
node --test tools/tests/p1_desktop_stub.test.mjs    # the desktop stub's paint rules (XL budget, no swatch text)
```
