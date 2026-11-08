#!/bin/bash
# From adam-xps (no long foreground command: three phases, each < 10 min):
#   tools/desktop/capture-remote.sh start <commit-or-branch> [WxH]  runs capture.sh on hercules in a niced, capped systemd --user unit
#   tools/desktop/capture-remote.sh wait                             polls up to ~8 min; exit 0 = finished OK, 3 = still running, 1 = failed
#   tools/desktop/capture-remote.sh fetch [WxH] [dest-repo-dir]      copies hercules' evidence/v2[-WxH] into dest (default: this repo)
# Runs are sequential (one Xvfb :93, one mock port): never start a second capture while one runs.
# The commit must already be on origin.
set -euo pipefail
export SSH_AUTH_SOCK=
H=adam@100.106.27.136
HERE=$(cd "$(dirname "$0")" && pwd)
UNIT=cf2-capture; LOG='$HOME/cf2/logs/capture.log'
case "${1:?start|wait|fetch}" in
  start)
    COMMIT=${2:?usage: start <commit-or-branch> [WxH]}
    SIZE=${3:-}
    scp -q "$HERE/capture.sh" $H:cf2/bin/capture.sh
    ssh $H "mkdir -p ~/cf2/logs; : > $LOG; systemd-run --user --unit=$UNIT --collect -p Nice=10 -p MemoryMax=24G -p WorkingDirectory=\$HOME \
      -p StandardOutput=append:$LOG -p StandardError=append:$LOG /bin/bash -lc 'bash \$HOME/cf2/bin/capture.sh $COMMIT $SIZE; echo EXIT=\$?'" ;;
  wait)
    for _ in $(seq 1 96); do
      ssh $H "grep -q '^EXIT=' $LOG" 2>/dev/null && break
      sleep 5
    done
    ssh $H "tail -n 25 $LOG"
    ssh $H "grep -q '^EXIT=' $LOG" 2>/dev/null || exit 3
    ssh $H "grep -q '^EXIT=0' $LOG" ;;
  fetch)
    SIZE=${2:-}; DIR=evidence/v2${SIZE:+-$SIZE}
    DEST=${3:-$(cd "$HERE/../.." && pwd)}
    rm -rf "$DEST/$DIR"; mkdir -p "$DEST/evidence"
    scp -q -r $H:cf2/run/repo/$DIR "$DEST/$DIR"
    echo "copied $DIR to $DEST" ;;
esac
