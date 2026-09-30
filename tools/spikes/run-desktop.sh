#!/usr/bin/env bash
# One-command runner for the desktop spikes:
#   tools/spikes/run-desktop.sh <spike-dir-name> [args...]
# Starts a private Xvfb (default :93; never :1), runs the spike under a MemoryMax=8G
# user scope (Electron + Playwright), and kills the Xvfb afterwards. Every spike
# creates its own throwaway HOME/HERMES_HOME; nothing here reads the live ~/.hermes.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tools="$(cd "$here/.." && pwd)"
spike="${1:?usage: run-desktop.sh <NN-slug> [args]}"; shift
display="${CF_DISPLAY:-:93}"
case "$display" in :0|:1) echo "refusing DISPLAY=$display (live desktop)" >&2; exit 2;; esac

[ -d "$tools/node_modules/@playwright/test" ] || (cd "$tools" && npm ci --no-audit --no-fund >&2)

xvfb="${XVFB:-$HOME/.local/opt/xvfb/root/usr/bin/Xvfb}"
started=""
if ! [ -e "/tmp/.X11-unix/X${display#:}" ]; then
  "$xvfb" "$display" -screen 0 1920x1200x24 -nolisten tcp >/dev/null 2>&1 &
  started=$!
  sleep 1.5
fi
cleanup() { [ -n "$started" ] && kill "$started" 2>/dev/null || true; }
trap cleanup EXIT

export CF_DISPLAY="$display"
export TMPDIR="${TMPDIR:-/tmp}"
runner=(node "$here/$spike/run.ts" "$@")
if command -v systemd-run >/dev/null && [ -z "${CF_NO_SCOPE:-}" ]; then
  systemd-run --user --scope -q -p MemoryMax=8G env CF_DISPLAY="$display" TMPDIR="$TMPDIR" "${runner[@]}"
else
  "${runner[@]}"
fi
