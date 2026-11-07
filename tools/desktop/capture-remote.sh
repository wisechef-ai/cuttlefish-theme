#!/bin/bash
# From adam-xps:  tools/desktop/capture-remote.sh <commit-or-branch> [dest-repo-dir]
# Runs capture.sh on hercules in a systemd --user unit (niced, memory-capped), polls it in the foreground, and copies
# evidence/v2 back into <dest-repo-dir> (default: this repo). The commit must already be on origin.
set -euo pipefail
export SSH_AUTH_SOCK=
H=adam@100.106.27.136
COMMIT=${1:?usage: capture-remote.sh <commit-or-branch> [dest]}
HERE=$(cd "$(dirname "$0")" && pwd); DEST=${2:-$(cd "$HERE/../.." && pwd)}
UNIT=cf2-capture; LOG='$HOME/cf2/logs/capture.log'
scp -q "$HERE/capture.sh" $H:cf2/bin/capture.sh
ssh $H "mkdir -p ~/cf2/logs; : > $LOG; systemd-run --user --unit=$UNIT --collect -p Nice=10 -p MemoryMax=24G -p WorkingDirectory=\$HOME \
  -p StandardOutput=append:$LOG -p StandardError=append:$LOG /bin/bash -lc 'bash \$HOME/cf2/bin/capture.sh $COMMIT; echo EXIT=\$?'" >/dev/null
for _ in $(seq 1 180); do
  sleep 5
  ssh $H "grep -q '^EXIT=' $LOG" 2>/dev/null && break
done
ssh $H "tail -n 40 $LOG"
ssh $H "grep -q '^EXIT=0' $LOG"
rm -rf "$DEST/evidence/v2"; mkdir -p "$DEST/evidence"
scp -q -r $H:cf2/run/repo/evidence/v2 "$DEST/evidence/v2"
echo "copied evidence/v2 to $DEST"
