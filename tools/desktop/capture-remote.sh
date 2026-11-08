#!/bin/bash
# Drives the real-Desktop capture on a Linux capture host (dev only). The host comes ONLY from the environment:
#   export CF_CAPTURE_HOST=<user@host>        required; there is no default
# From a workstation (no long foreground command: three phases, each < 10 min):
#   tools/desktop/capture-remote.sh start <commit-or-branch> [WxH]   runs capture.sh on the host in a niced, capped systemd --user unit.
#                                                                   Picks a FREE private display (:90-:99) and mock port (18900-18999)
#                                                                   on the host at start, so two runs never share them.
#   tools/desktop/capture-remote.sh wait                             polls up to ~8 min; exit 0 = finished OK, 3 = still running, 1 = failed
#   tools/desktop/capture-remote.sh fetch [WxH] [dest-repo-dir]      copies the host's evidence/v2[-WxH] into dest (default: this repo)
# Runs are sequential on one host: never start a second capture while one runs. The commit must already be on origin.
set -euo pipefail
export SSH_AUTH_SOCK=
H=${CF_CAPTURE_HOST:?set CF_CAPTURE_HOST to the capture host (user@host of a Linux box with Xvfb); there is no default}
HERE=$(cd "$(dirname "$0")" && pwd)
UNIT=cf2-capture; LOG='$HOME/cf2/logs/capture.log'
case "${1:?start|wait|fetch}" in
  start)
    COMMIT=${2:?usage: start <commit-or-branch> [WxH]}
    SIZE=${3:-}
    # a free private display and a free mock port on the host, decided now and handed to the unit
    PICK=$(ssh "$H" 'bash -s' <<'REMOTE'
      d=""; for n in $(seq 90 99); do [ -e /tmp/.X11-unix/X$n ] || [ -e /tmp/.X$n-lock ] || { d=$n; break; }; done
      q=""; for p in $(seq 18900 18999); do ss -ltn | grep -q ":$p " || { q=$p; break; }; done
      [ -n "$d" ] && [ -n "$q" ] && echo "$d $q" || { echo "no free display (90-99) or port (18900-18999)" >&2; exit 1; }
REMOTE
    )
    read -r DISP PORT <<<"$PICK"
    echo "run on the host: display :$DISP, mock port $PORT"
    scp -q "$HERE/capture.sh" "$H":cf2/bin/capture.sh
    ssh "$H" "mkdir -p ~/cf2/logs; : > $LOG; systemd-run --user --unit=$UNIT --collect -p Nice=10 -p MemoryMax=24G -p WorkingDirectory=\$HOME \
      --setenv=CF_DISPLAY=:$DISP --setenv=CF_MOCK_PORT=$PORT \
      -p StandardOutput=append:$LOG -p StandardError=append:$LOG /bin/bash -lc 'bash \$HOME/cf2/bin/capture.sh $COMMIT $SIZE; echo EXIT=\$?'" ;;
  wait)
    for _ in $(seq 1 96); do
      ssh "$H" "grep -q '^EXIT=' $LOG" 2>/dev/null && break
      sleep 5
    done
    ssh "$H" "tail -n 25 $LOG"
    ssh "$H" "grep -q '^EXIT=' $LOG" 2>/dev/null || exit 3
    ssh "$H" "grep -q '^EXIT=0' $LOG" ;;
  fetch)
    SIZE=${2:-}; DIR=evidence/v2${SIZE:+-$SIZE}
    DEST=${3:-$(cd "$HERE/../.." && pwd)}
    rm -rf "$DEST/$DIR"; mkdir -p "$DEST/evidence"
    scp -q -r "$H":cf2/run/repo/$DIR "$DEST/$DIR"
    echo "copied $DIR to $DEST" ;;
esac
