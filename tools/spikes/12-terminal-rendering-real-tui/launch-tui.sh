#!/usr/bin/env bash
# Exec the REAL Hermes TUI against $HERMES_HOME (which the caller made throwaway).
#
# Default: exec what `hermes --tui` execs (node --expose-gc ui-tui/dist/entry.js with the env
# `_launch_tui()` sets), bypassing the python launcher's update/build preflight, which rebuilds
# on a fresh HERMES_HOME and contends with other lanes (same approach as the P0-TUI lane).
# CF_VIA_LAUNCHER=1 runs the real `hermes --tui` launcher instead.
#
# Env: HERMES_HOME (required), CF_HERMES_SRC (default ~/.hermes/hermes-agent),
#      CF_TUI_DIST (ui-tui dir, default $CF_HERMES_SRC/ui-tui), CF_NODE (default: node on PATH).
set -euo pipefail
: "${HERMES_HOME:?set HERMES_HOME to a throwaway directory}"
case "$HERMES_HOME" in "$HOME/.hermes"|"$HOME/.hermes/") echo "refusing to run against the live ~/.hermes" >&2; exit 1;; esac

# Parent agent sessions leak HERMES_* (QUIET, SINGLE_QUERY, ...) that change TUI behaviour.
while IFS='=' read -r name _; do
  case "$name" in HERMES_HOME) ;; HERMES_*|_HERMES*|TERMINAL_*|COGNEE*|AI_AGENT*) unset "$name" ;; esac
done < <(env)

if [[ "${CF_VIA_LAUNCHER:-0}" == 1 ]]; then exec hermes --tui; fi

SRC="${CF_HERMES_SRC:-$HOME/.hermes/hermes-agent}"
DIST="${CF_TUI_DIST:-$SRC/ui-tui}"
NODE="${CF_NODE:-$(command -v node || true)}"
[[ -x "$NODE" ]] || { echo "node not found (set CF_NODE)" >&2; exit 1; }
[[ -f "$DIST/dist/entry.js" ]] || { echo "no TUI bundle at $DIST/dist/entry.js" >&2; exit 1; }
export HERMES_PYTHON="$SRC/venv/bin/python3" HERMES_PYTHON_SRC_ROOT="$SRC" HERMES_CWD="$HOME" \
       NODE_ENV=production HERMES_TUI_NATIVE=0 HERMES_TUI_ACTIVE_SESSION_FILE="$HERMES_HOME/active-session.json" \
       NODE_OPTIONS=--max-old-space-size=4096
exec "$NODE" --expose-gc "$DIST/dist/entry.js"
