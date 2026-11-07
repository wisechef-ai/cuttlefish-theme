#!/bin/bash
# From adam-xps (no long foreground command: three phases, each < 10 min):
#   tools/desktop/capture-remote.sh start <commit-or-branch>   runs capture.sh on hercules in a niced, capped systemd --user unit
#   tools/desktop/capture-remote.sh wait                       polls up to ~8 min; exit 0 = finished OK, 3 = still running, 1 = failed
#   tools/desktop/capture-remote.sh fetch [dest-repo-dir]      copies hercules' evidence/v2 into dest (default: this repo)
# The commit must already be on origin.
set -euo pipefail
export SSH_AUTH_SOCK=
H=adam@100.106.27.136
HERE=$(cd "$(dirname "$0")" && pwd)
UNIT=cf2-capture; LOG='$HOME/cf2/logs/capture.log'
case "${1:?start|wait|fetch}" in
  start)
    COMMIT=${2:?usage: start <commit-or-branch>}
    scp -q "$HERE/capture.sh" $H:cf2/bin/capture.sh
    ssh $H "mkdir -p ~/cf2/logs; : > $LOG; systemd-run --user --unit=$UNIT --collect -p Nice=10 -p MemoryMax=24G -p WorkingDirectory=\$HOME \
      -p StandardOutput=append:$LOG -p StandardError=append:$LOG /bin/bash -lc 'bash \$HOME/cf2/bin/capture.sh $COMMIT; echo EXIT=\$?'" ;;
  wait)
    for _ in $(seq 1 96); do
      ssh $H "grep -q '^EXIT=' $LOG" 2>/dev/null && break
      sleep 5
    done
    ssh $H "tail -n 25 $LOG"
    ssh $H "grep -q '^EXIT=' $LOG" 2>/dev/null || exit 3
    ssh $H "grep -q '^EXIT=0' $LOG" ;;
  fetch)
    DEST=${2:-$(cd "$HERE/../.." && pwd)}
    rm -rf "$DEST/evidence/v2"; mkdir -p "$DEST/evidence"
    scp -q -r $H:cf2/run/repo/evidence/v2 "$DEST/evidence/v2"
    echo "copied evidence/v2 to $DEST" ;;
esac
