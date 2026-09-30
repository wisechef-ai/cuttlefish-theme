#!/usr/bin/env bash
# cf2909 spike 12, cell 2: real Terminator (VTE) on a private Xvfb, running the REAL Hermes TUI
# with the 2-row test mantle on the far side of an SSH connection.
#
#   tools/spikes/12-terminal-rendering-real-tui/run-ssh.sh OUT_DIR
#
# Targets (TARGETS, space-separated):
#   herc         ssh adam@100.106.27.136: hermes-agent + node on hercules, stock ssh env
#   herc-forced  same, COLORTERM=truecolor re-exported remotely (what a doctor fix would do)
#   loop         ssh to THIS box through a throwaway user-space sshd on 127.0.0.1:$LOOP_PORT
#                (temp host key + temp authorized key; ~/.ssh is never touched). This is the
#                `ssh localhost` cell without authorizing a key in the real ~/.ssh.
#
# Every remote run gets its own mktemp HERMES_HOME holding only mantle.mjs + an offline config.
# Outputs per target: <t>.png <t>.sgr <t>.txt <t>.pixels.txt, plus remote env in <t>.env.txt.
set -uo pipefail
export HOME=/home/adam
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
OUT=${1:?usage: run-ssh.sh OUT_DIR}
TARGETS=${TARGETS:-"herc herc-forced loop"}
HERC=${HERC:-adam@100.106.27.136}
DISP=${CF_DISPLAY:-:92}
LOOP_PORT=${LOOP_PORT:-22922}
COLS=${CF_COLS:-120} ROWS=${CF_ROWS:-40}
PY=${CF_PYTHON:-python3}
"$PY" -c 'import pyte, PIL' || { echo "need pyte + Pillow in $PY" >&2; exit 2; }
[[ "$DISP" == ":1" ]] && { echo "refusing :1" >&2; exit 2; }
mkdir -p "$OUT"
work=$(mktemp -d); sshd_pid=""
cleanup() { [[ -n "$sshd_pid" ]] && kill "$sshd_pid" 2>/dev/null; rm -rf "$work"; }
trap cleanup EXIT

CONFIG='model:\n  default: stub\n  provider: custom\n  base_url: http://127.0.0.1:9/v1\n  api_key: stub\ndisplay:\n  interface: tui\n'

# stage_remote SSH_ARGS... -> prints remote dir holding launch-tui.sh and home/ (throwaway HERMES_HOME)
stage_remote() {
  local rdir
  rdir=$(ssh -o BatchMode=yes "$@" 'mktemp -d') || return 1
  ssh -o BatchMode=yes "$@" "mkdir -p $rdir/home/tui-widgets && printf '$CONFIG' > $rdir/home/config.yaml" || return 1
  ssh -o BatchMode=yes "$@" "cat > $rdir/home/tui-widgets/cfmantle.mjs" < "$HERE/mantle.mjs" || return 1
  ssh -o BatchMode=yes "$@" "cat > $rdir/launch-tui.sh" < "$HERE/launch-tui.sh" || return 1
  echo "$rdir"
}

start_loop_sshd() {
  local d="$work/sshd"; mkdir -p "$d"
  ssh-keygen -q -t ed25519 -N '' -f "$d/host" && ssh-keygen -q -t ed25519 -N '' -f "$d/client" || return 1
  cp "$d/client.pub" "$d/authorized_keys"
  cat > "$d/sshd_config" <<EOF
Port $LOOP_PORT
ListenAddress 127.0.0.1
HostKey $d/host
AuthorizedKeysFile $d/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
UsePAM no
StrictModes no
PidFile $d/sshd.pid
AcceptEnv LANG LC_*
EOF
  /usr/sbin/sshd -D -e -f "$d/sshd_config" 2>"$OUT/loop.sshd.log" & sshd_pid=$!
  sleep 1; kill -0 "$sshd_pid" 2>/dev/null || return 1
  printf '[127.0.0.1]:%s %s\n' "$LOOP_PORT" "$(cut -d' ' -f1,2 "$d/host.pub")" > "$d/known_hosts"
  LOOP_ARGS=(-i "$d/client" -o IdentitiesOnly=yes -o UserKnownHostsFile="$d/known_hosts" -p "$LOOP_PORT" adam@127.0.0.1)
}

summary="$OUT/summary.tsv"; printf 'target\trc\tpixels\tremote_env\n' > "$summary"
for t in $TARGETS; do
  case "$t" in
    herc|herc-forced) args=("$HERC"); node=/home/adam/.local/bin/node ;;
    loop) start_loop_sshd || { echo "loop sshd failed" >&2; printf 'loop\tsshd-fail\t-\t-\n' >> "$summary"; continue; }
          args=("${LOOP_ARGS[@]}"); node=$(command -v node) ;;
    *) echo "unknown target $t" >&2; continue ;;
  esac
  rdir=$(stage_remote "${args[@]}") || { printf '%s\tstage-fail\t-\t-\n' "$t" >> "$summary"; continue; }
  force=""; [[ "$t" == *-forced ]] && force="export COLORTERM=truecolor;"
  remote="$force printf 'remote host=%s TERM=%s COLORTERM=%s LC_TERMINAL=%s sha=%s\n' \"\$(hostname)\" \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" \"\${LC_TERMINAL:-(unset)}\" \"\$(git -C ~/.hermes/hermes-agent rev-parse --short=11 HEAD)\" > $rdir/env.txt; HERMES_HOME=$rdir/home CF_NODE=$node exec bash $rdir/launch-tui.sh"
  echo "== $t ($rdir)" >&2
  HERMES_HOME=$(mktemp -d) "$PY" "$ROOT/tools/capture_tui.py" --mode terminator --display "$DISP" \
    --wait-for "▀{$((COLS - 2))}" --timeout 180 --settle 3 --cols "$COLS" --rows "$ROWS" \
    --png "$OUT/$t.png" --raw-log "$OUT/$t.sgr" --text-out "$OUT/$t.txt" \
    -- ssh -t -o BatchMode=yes "${args[@]}" "$remote"
  rc=$?
  ssh -o BatchMode=yes "${args[@]}" "cat $rdir/env.txt; rm -rf $rdir" > "$OUT/$t.env.txt" 2>&1
  pix="-"
  if [[ -s "$OUT/$t.png" ]]; then
    "$PY" "$HERE/mantle_pixels.py" "$OUT/$t.png" "$OUT/$t.sgr" --cols "$COLS" --rows "$ROWS" | tee "$OUT/$t.pixels.txt" >&2
    pix=$(cut -d' ' -f2 "$OUT/$t.pixels.txt")
  fi
  printf '%s\t%s\t%s\t%s\n' "$t" "$rc" "$pix" "$(head -1 "$OUT/$t.env.txt")" >> "$summary"
  [[ "$t" == loop && -n "$sshd_pid" ]] && { kill "$sshd_pid"; sshd_pid=""; }
done
cat "$summary"
