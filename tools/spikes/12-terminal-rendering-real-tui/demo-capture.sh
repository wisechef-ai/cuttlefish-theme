#!/usr/bin/env bash
# One-command demo of tools/capture_tui.py against the REAL `hermes --tui` running the spike-12
# 2-row mantle widget, in a throwaway HERMES_HOME (never touches ~/.hermes).
#
#   tools/spikes/12-terminal-rendering-real-tui/demo-capture.sh [outdir]
#
# Captures the same TUI twice in the pty+pyte backend: truecolor (COLORTERM=truecolor) and the
# 256-colour rung (COLORTERM unset), then checks the mantle rows are pixel-identical in both.
# With CF_TERMINATOR=1 it also captures a real Terminator window on Xvfb ($CF_DISPLAY, default :92).
#
# Outputs per run: <name>.png  <name>.sgr (raw SGR byte log)  <name>.txt (screen text).
# Env: CF_COLS (120) CF_ROWS (40) CF_TIMEOUT (180) CF_PYTHON (python with pyte+Pillow;
#      default tools/.venv or .venv if present, else python3), plus launch-tui.sh's CF_* knobs.
set -euo pipefail
export HOME="${HOME:-/home/adam}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
OUT="${1:-${TMPDIR:-/tmp}/cf-spike-12-demo}"
COLS="${CF_COLS:-120}" ROWS="${CF_ROWS:-40}" TIMEOUT="${CF_TIMEOUT:-180}"
PY="${CF_PYTHON:-}"
for cand in "$ROOT/.venv/bin/python" "$ROOT/tools/.venv/bin/python"; do
  [[ -z "$PY" && -x "$cand" ]] && PY="$cand"
done
PY="${PY:-python3}"
"$PY" -c 'import pyte, PIL' 2>/dev/null || { echo "need pyte + Pillow: $PY -m pip install -r $ROOT/tools/requirements-capture.txt" >&2; exit 1; }
mkdir -p "$OUT"

HH="$(mktemp -d "${TMPDIR:-/tmp}/cf-spike12-home-XXXXXX")"
trap 'rm -rf "$HH"' EXIT
mkdir -p "$HH/tui-widgets"
cp "$HERE/mantle.mjs" "$HH/tui-widgets/cfmantle.mjs"
# Offline: a dead local endpoint, never a real provider.
cat > "$HH/config.yaml" <<'YAML'
model:
  default: stub
  provider: custom
  base_url: http://127.0.0.1:9/v1
  api_key: stub
display:
  interface: tui
YAML

# The mantle is the only full-width run of ▀ on screen: cols-2 cells.
WAIT="▀{$((COLS - 2))}"
cap() {  # name, extra capture_tui args...
  local name="$1"; shift
  echo "== $name" >&2
  HERMES_HOME="$HH" "$PY" "$ROOT/tools/capture_tui.py" --wait-for "$WAIT" --timeout "$TIMEOUT" --settle 2 \
    --cols "$COLS" --rows "$ROWS" --png "$OUT/$name.png" --raw-log "$OUT/$name.sgr" --text-out "$OUT/$name.txt" \
    "$@" -- bash "$HERE/launch-tui.sh"
}

cap virtual-truecolor
cap virtual-256 --no-colorterm
"$PY" "$HERE/compare_mantle.py" "$OUT/virtual-truecolor.sgr" "$OUT/virtual-256.sgr" --cols "$COLS" --rows "$ROWS"

if [[ "${CF_TERMINATOR:-0}" == 1 ]]; then
  cap terminator-truecolor --mode terminator --display "${CF_DISPLAY:-:92}"
fi
echo "artifacts in $OUT" >&2
ls -1 "$OUT"
