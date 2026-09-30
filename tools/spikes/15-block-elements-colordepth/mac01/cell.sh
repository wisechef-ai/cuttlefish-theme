#!/bin/bash
# Runs INSIDE an iTerm2 session on mac01 (launched by run-mac01.sh via a Dynamic Profile).
# usage: cell.sh <run-id> <local|ssh> <auto|256|truecolor|16> <font>
# Writes out/<id>.env (terminal env as seen by the pattern), out/<id>.png, out/<id>.done.
rid="$1"; where="$2"; depth="$3"; font="$4"
D="$HOME/cf15"; O="$D/out"; mkdir -p "$O"
SSH_TARGET="${SSH_TARGET:-adam@100.106.204.93}"
envline='echo "host=$(hostname -s) TERM=$TERM COLORTERM=${COLORTERM:-unset} TERM_PROGRAM=${TERM_PROGRAM:-unset} LC_TERMINAL=${LC_TERMINAL:-unset}"'
{
  echo "run=$rid where=$where depth=$depth font=$font"
  echo "local: $(eval "$envline")"
} >"$O/$rid.env"
clear
if [ "$where" = ssh ]; then
  scp -q -o BatchMode=yes "$D/pattern.py" "$SSH_TARGET:/tmp/cf15-pattern.py" 2>>"$O/$rid.env"
  # -tt so TERM is forwarded exactly as for the pattern run below
  echo "remote: $(ssh -tt -o BatchMode=yes "$SSH_TARGET" "$envline" 2>&1 | tr -d '\r')" >>"$O/$rid.env"
  ssh -tt -o BatchMode=yes "$SSH_TARGET" "python3 /tmp/cf15-pattern.py --depth $depth --cols 108"
else
  /usr/bin/python3 "$D/pattern.py" --depth "$depth" --cols 108
fi
printf '\033[2m[cf15 %s font=%s]\033[0m' "$rid" "$font"
sleep 2
wid=$(/usr/bin/osascript -l JavaScript "$D/winid.js" iTerm2 2>>"$O/$rid.env")
if [ -z "$wid" ]; then
  echo "BLOCKED no on-screen iTerm2 window in CGWindowList" >"$O/$rid.done"
elif err=$(/usr/sbin/screencapture -x -o -l"$wid" "$O/$rid.png" 2>&1) && [ -s "$O/$rid.png" ]; then
  echo "OK window=$wid" >"$O/$rid.done"
else
  echo "BLOCKED screencapture -l$wid: ${err:-empty png} (Screen Recording TCC for iTerm)" >"$O/$rid.done"
fi
sleep 1
