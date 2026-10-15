#!/usr/bin/env bash
# Record the desktop traces on the REAL upstream Electron build, on a private Xvfb (never :1/:0).
#   CF_DISPLAY=:111 tools/traces/record/run-desktop.sh [--only main,error,kill]
# Needs: the upstream desktop build (~/.worktrees/hermes-agent/cf2909-upstream/apps/desktop/dist), python3 (convert.py), `npm ci` in tools/.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tools="$(cd "$here/../.." && pwd)"
display="${CF_DISPLAY:-:111}"
case "$display" in :0|:1) echo "refusing DISPLAY=$display (live desktop)" >&2; exit 2;; esac
[ -d "$tools/node_modules/@playwright/test" ] || (cd "$tools" && npm ci --no-audit --no-fund >&2)
xvfb="${XVFB:-$HOME/.local/opt/xvfb/root/usr/bin/Xvfb}"
started=""
if ! pgrep -x Xvfb -a | grep -q " $display "; then  # a stale socket file alone does not mean a live server
  rm -f "/tmp/.X11-unix/X${display#:}"
  "$xvfb" "$display" -screen 0 1920x1200x24 -nolisten tcp >/dev/null 2>&1 &
  started=$!
  sleep 1.5
fi
trap '[ -n "$started" ] && kill "$started" 2>/dev/null || true' EXIT
export CF_DISPLAY="$display" TMPDIR="${TMPDIR:-/tmp}"
runner=(node "$here/desktop.ts" "$@")
if command -v systemd-run >/dev/null && [ -z "${CF_NO_SCOPE:-}" ]; then
  systemd-run --user --scope -q -p MemoryMax=8G env CF_DISPLAY="$display" TMPDIR="$TMPDIR" "${runner[@]}"
else
  "${runner[@]}"
fi
