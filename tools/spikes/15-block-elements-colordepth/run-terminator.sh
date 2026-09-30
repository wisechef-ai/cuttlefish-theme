#!/usr/bin/env bash
# cf2909 spike 15, matrix cells (a) Terminator/VTE local and (b) Terminator over SSH.
#
#   tools/spikes/15-block-elements-colordepth/run-terminator.sh [OUT_DIR]
#
# For every FONT x MODE it starts a real Terminator (VTE) on a private user-space
# Xvfb, runs pattern.py (unchanged) inside it under `script` so the raw SGR bytes
# are logged, records TERM/COLORTERM as seen INSIDE the session, and screenshots
# the display to PNG with the rootless ffmpeg x11grab helper (no ImageMagick).
#
# Modes:
#   local        pattern.py in Terminator's own environment (what VTE advertises)
#   local-256    same, truecolor withdrawn: TERM=xterm-256color, COLORTERM unset
#   ssh-herc     ssh -t to hercules ($SSH_REMOTE), pattern.py runs THERE (default ssh env)
#   ssh-local    ssh -t localhost (recorded honestly; fails without an authorized key)
#
# Env knobs: FONTS (';'-separated Pango font names), MODES (space-separated),
#   XDISPLAY (default :192 so it never collides with a sibling card's :92),
#   SSH_REMOTE (default adam@100.106.27.136), SETTLE (seconds before the shot).
# Isolation: throwaway HERMES_HOME + XDG_CONFIG_HOME; never touches ~/.hermes or :1.
set -uo pipefail
export HOME=/home/adam

HERE=$(cd "$(dirname "$0")" && pwd)
PATTERN="$HERE/pattern.py"
OUT=${1:-${TMPDIR:-/tmp}/spike15-terminator}
FONTS=${FONTS:-"DejaVu Sans Mono 13;Noto Mono 13;Liberation Mono 13"}
MODES=${MODES:-"local local-256 ssh-herc ssh-herc-forced ssh-local"}
XDISPLAY=${XDISPLAY:-:192}
SSH_REMOTE=${SSH_REMOTE:-adam@100.106.27.136}
SETTLE=${SETTLE:-7}
GEOM_W=1560 GEOM_H=880 SCREEN=1600x920
XVFB="$HOME/.local/opt/xvfb/root/usr/bin/Xvfb"
SHOT="$HOME/.local/opt/xvfb/xvfb-shot.sh"

[[ "$XDISPLAY" == ":1" ]] && { echo "refusing :1 (Adam's live desktop)" >&2; exit 2; }
for bin in "$XVFB" "$SHOT" /usr/bin/terminator /usr/bin/script; do
  [[ -e "$bin" ]] || { echo "missing prerequisite: $bin" >&2; exit 2; }
done

mkdir -p "$OUT"
export HERMES_HOME; HERMES_HOME=$(mktemp -d)
work=$(mktemp -d)
"$XVFB" "$XDISPLAY" -screen 0 "${SCREEN}x24" -nolisten tcp >/dev/null 2>&1 & xpid=$!
cleanup() { kill "$xpid" 2>/dev/null; rm -rf "$work" "$HERMES_HOME"; }
trap cleanup EXIT
sleep 1.5
kill -0 "$xpid" 2>/dev/null || { echo "Xvfb failed to start on $XDISPLAY (display busy?)" >&2; exit 2; }

# Stage the fixture on the remote once (unchanged bytes; sha recorded).
rdir=""
if [[ " $MODES " == *" ssh-herc "* ]]; then
  rdir=$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_REMOTE" 'mktemp -d') || rdir=""
  [[ -n "$rdir" ]] && scp -q "$PATTERN" "$SSH_REMOTE:$rdir/pattern.py"
fi

summary="$OUT/summary.tsv"
printf 'font\tmode\trc\tpng\tsession_env\n' > "$summary"
echo "pattern sha256: $(sha256sum "$PATTERN" | cut -d' ' -f1)" > "$OUT/meta.txt"
echo "terminator: $(terminator --version 2>&1)  vte: $(dpkg-query -W -f='${Version}' libvte-2.91-0 2>/dev/null)" >> "$OUT/meta.txt"
echo "remote: $SSH_REMOTE dir=$rdir" >> "$OUT/meta.txt"

IFS=';' read -r -a font_list <<< "$FONTS"
for font in "${font_list[@]}"; do
  fslug=$(echo "$font" | tr 'A-Z ' 'a-z-')
  for mode in $MODES; do
    tag="$fslug.$mode"
    cfg="$work/cfg-$tag"; mkdir -p "$cfg/terminator"
    printf '[global_config]\n[profiles]\n  [[default]]\n    use_system_font = False\n    font = %s\n    show_titlebar = False\n    scrollbar_position = hidden\n    background_color = "#101014"\n    foreground_color = "#d8d8d8"\n[layouts]\n[plugins]\n' "$font" > "$cfg/terminator/config"
    envlog="$OUT/$tag.env.log"; raw="$OUT/$tag.sgr.raw"; done_flag="$work/$tag.done"
    case "$mode" in
      local)
        inner="printf 'TERM=%s COLORTERM=%s\n' \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" > '$envlog'; python3 '$PATTERN'" ;;
      local-256)
        inner="export TERM=xterm-256color; unset COLORTERM; printf 'TERM=%s COLORTERM=%s\n' \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" > '$envlog'; python3 '$PATTERN'" ;;
      ssh-herc)
        inner="printf 'local TERM=%s COLORTERM=%s\n' \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" > '$envlog'; ssh -t -o BatchMode=yes '$SSH_REMOTE' 'printf \"remote TERM=%s COLORTERM=%s host=%s\\n\" \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" \"\$(hostname)\"; python3 $rdir/pattern.py'; echo \"ssh-herc rc=\$?\" >> '$envlog'" ;;
      ssh-herc-forced)
        # what lib/forceTruecolor.ts / a doctor fix would do: re-advertise truecolor remotely
        inner="printf 'local TERM=%s COLORTERM=%s\n' \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" > '$envlog'; ssh -t -o BatchMode=yes '$SSH_REMOTE' 'export COLORTERM=truecolor; printf \"remote TERM=%s COLORTERM=%s host=%s (forced)\\n\" \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" \"\$(hostname)\"; python3 $rdir/pattern.py'; echo \"ssh-herc-forced rc=\$?\" >> '$envlog'" ;;
      ssh-local)
        inner="printf 'local TERM=%s COLORTERM=%s\n' \"\${TERM:-(unset)}\" \"\${COLORTERM:-(unset)}\" > '$envlog'; ssh -t -o BatchMode=yes -o ConnectTimeout=5 localhost 'python3 $PATTERN' 2>>'$envlog'; echo \"ssh-local rc=\$?\" >> '$envlog'" ;;
      *) echo "unknown mode $mode" >&2; continue ;;
    esac
    # script(1) keeps the pty (so pattern.py sees the real size) and logs raw bytes.
    runner="$work/$tag.sh"
    printf '#!/bin/bash\nscript -q -f -c %q %q\necho rc=$? > %q\nsleep 600\n' "$inner" "$raw" "$done_flag" > "$runner"
    chmod +x "$runner"
    DISPLAY=$XDISPLAY XDG_CONFIG_HOME=$cfg dbus-run-session -- \
      terminator -u --geometry=${GEOM_W}x${GEOM_H}+0+0 -x "$runner" >"$work/$tag.term.log" 2>&1 & tpid=$!
    for _ in $(seq 1 60); do [[ -e "$done_flag" ]] && break; sleep 0.5; done
    sleep "$SETTLE"
    png="$OUT/$tag.png"
    bash "$SHOT" "$XDISPLAY" "$png" "$SCREEN"; shot_rc=$?
    rc=$(cat "$done_flag" 2>/dev/null || echo "rc=timeout")
    # The remote side prints its own env into the session; lift it from the byte log.
    grep -ao $'remote TERM=[^\r]*' "$raw" 2>/dev/null | grep -v '%s' >> "$envlog"
    pkill -P "$tpid" 2>/dev/null; kill "$tpid" 2>/dev/null; wait "$tpid" 2>/dev/null
    pkill -f "$runner" 2>/dev/null
    printf '%s\t%s\t%s\t%s\t%s\n' "$font" "$mode" "$rc/shot=$shot_rc" "$png" "$(tr '\n' ' ' < "$envlog" 2>/dev/null)" >> "$summary"
    echo "[$tag] $rc shot=$shot_rc env: $(tr '\n' ' ' < "$envlog" 2>/dev/null)" >&2
    sleep 1
  done
done
[[ -n "$rdir" ]] && ssh -o BatchMode=yes "$SSH_REMOTE" "rm -rf '$rdir'"
# Objective pixel metrics (needs a python with Pillow; PY overrides).
PY=${PY:-$HOME/.hermes/hermes-agent/venv/bin/python}
if "$PY" -c 'import PIL' 2>/dev/null; then
  pngs=(); for f in "$OUT"/*.png; do grep -q 'ssh-local rc=[1-9]' "${f%.png}.env.log" 2>/dev/null || pngs+=("$f"); done
  { "$PY" "$HERE/seam_metrics.py" "${pngs[@]}"
    for m in $MODES; do
      for f in "${font_list[@]:1}"; do
        a="$OUT/$(echo "${font_list[0]}" | tr 'A-Z ' 'a-z-').$m.png"; b="$OUT/$(echo "$f" | tr 'A-Z ' 'a-z-').$m.png"
        [[ " ${pngs[*]} " == *" $a "* && " ${pngs[*]} " == *" $b "* ]] || continue
        echo "same-blocks [$m] ${font_list[0]} vs $f: $("$PY" "$HERE/seam_metrics.py" --same "$a" "$b")"
      done
    done; } > "$OUT/seam-metrics.txt" 2>&1
else
  echo "Pillow not found for $PY; skipped seam_metrics" >&2
fi
echo "$summary"
