#!/usr/bin/env bash
# cf2909 spike 15, matrix cells (c) iTerm2 local on mac01 and (d) iTerm2 on mac01 -> SSH.
#
# Run from the Linux box:   tools/spikes/15-block-elements-colordepth/run-mac01.sh
#   --preflight        read-only checks only (install state, GUI session, SSH auth), then exit
#   --print-profiles   print the iTerm2 Dynamic Profiles JSON this script installs, then exit
#
# Env knobs:
#   MAC=mac01                        ssh alias of the macOS box
#   SSH_TARGET=adam@100.106.204.93   host iTerm2-on-mac01 ssh-es into for cell (d)
#   OUT=./out/spike15-mac01          where PNGs + env records land locally
#
# How it works (no Apple Events, so no Automation TCC grant is needed):
#   1. user-local iTerm2 install (~/Applications, official zip, Developer ID H7V7XYVQ7D checked)
#   2. one Dynamic Profile per run (font + command), selected via "Default Bookmark Guid"
#   3. `open -na iTerm.app` -> the profile's command (cell.sh) runs pattern.py INSIDE iTerm2,
#      then screencapture -l<own window id>. Because iTerm2 is the responsible process, the
#      only TCC grant needed is Screen Recording for iTerm.
# Exit: 0 all runs captured; 3 one or more runs BLOCKED (structured lines on stdout).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAC="${MAC:-mac01}"
SSH_TARGET="${SSH_TARGET:-adam@100.106.204.93}"
OUT="${OUT:-./out/spike15-mac01}"
REMOTE_DIR='cf15'                       # relative to $HOME on mac01
ITERM_URL='https://iterm2.com/downloads/stable/latest'
ITERM_TEAM='H7V7XYVQ7D'
SSHO=(-o BatchMode=yes -o ConnectTimeout=10)

# run id | font (PostScript name + size) | where | depth arg
RUNS=(
  "c-menlo|Menlo-Regular 14|local|auto"
  "c-courier|Courier 14|local|auto"
  "c-menlo-256|Menlo-Regular 14|local|256"
  "d-menlo|Menlo-Regular 14|ssh|auto"
  "d-courier|Courier 14|ssh|auto"
)

profiles_json() {
  python3 - "$REMOTE_DIR" "${RUNS[@]}" <<'PY'
import json, sys, uuid
rdir, runs = sys.argv[1], sys.argv[2:]
profiles = []
for r in runs:
    rid, font, where, depth = r.split("|")
    profiles.append({
        "Name": f"cf15 {rid}",
        "Guid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"cf2909/spike15/{rid}")),
        "Normal Font": font,
        "Non Ascii Font": font,
        "Use Non-ASCII Font": False,
        "Columns": 110, "Rows": 30,
        "Custom Command": "Yes",
        "Command": f"/bin/bash -l __HOME__/{rdir}/cell.sh {rid} {where} {depth} '{font}'",
        "Close Sessions On End": True,
        "Prompt Before Closing 2": False,
    })
print(json.dumps({"Profiles": profiles}, indent=1))
PY
}

guid_of() { python3 -c "import uuid,sys;print(uuid.uuid5(uuid.NAMESPACE_URL,'cf2909/spike15/'+sys.argv[1]))" "$1"; }

preflight() {  # read-only; prints key=value lines
  ssh "${SSHO[@]}" "$MAC" "SSH_TARGET='$SSH_TARGET' bash -s" <<'SH'
v=$(defaults read ~/Applications/iTerm.app/Contents/Info.plist CFBundleShortVersionString 2>/dev/null || echo missing)
echo "iterm_version=$v"
if launchctl print "gui/$(id -u)" >/dev/null 2>&1; then echo gui_session=yes; else echo gui_session=no; fi
echo "console_owner=$(stat -f %Su /dev/console)"
if ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_TARGET" true 2>/tmp/cf15-ssh.err; then echo ssh_target=ok
else echo "ssh_target=fail:$(tr '\r\n' '  ' </tmp/cf15-ssh.err)"; fi
SH
}

case "${1:-}" in
  --print-profiles) profiles_json; exit 0 ;;
  --preflight) preflight; exit 0 ;;
  "") ;;
  *) echo "usage: $0 [--preflight|--print-profiles]" >&2; exit 2 ;;
esac

mkdir -p "$OUT"
PF="$(preflight)"; echo "$PF" | sed 's/^/preflight: /' >&2
gui=$(sed -n 's/^gui_session=//p' <<<"$PF"); sshok=$(sed -n 's/^ssh_target=//p' <<<"$PF")

# 1. install (idempotent, user-local, signature checked)
# shellcheck disable=SC2087  # client-side expansion of $REMOTE_DIR/$ITERM_* is intended
ssh "${SSHO[@]}" "$MAC" "bash -s" <<SH
set -e
mkdir -p ~/Applications ~/$REMOTE_DIR/out
if [ ! -d ~/Applications/iTerm.app ]; then
  curl -fsSL -o ~/Applications/iTerm2.zip '$ITERM_URL'
  ditto -x -k ~/Applications/iTerm2.zip ~/Applications/
fi
codesign -dv ~/Applications/iTerm.app 2>&1 | grep -q 'TeamIdentifier=$ITERM_TEAM'
# quiet first-launch UI (this install exists only for the spike)
defaults write com.googlecode.iterm2 SUEnableAutomaticChecks -bool false
defaults write com.googlecode.iterm2 PromptOnQuit -bool false
defaults write com.googlecode.iterm2 NoSyncNeverRemindPrefsChangesLostForFile -bool true
defaults write com.googlecode.iterm2 OpenNoWindowsAtStartup -bool false
SH

# 2. ship fixture + helpers + profiles
scp -q "$HERE/pattern.py" "$HERE/mac01/cell.sh" "$HERE/mac01/winid.js" "$MAC:$REMOTE_DIR/"
profiles_json | ssh "${SSHO[@]}" "$MAC" \
  'd="$HOME/Library/Application Support/iTerm2/DynamicProfiles"; mkdir -p "$d"; sed "s#__HOME__#$HOME#g" >"$d/cf15.json"'

blocked=0
for r in "${RUNS[@]}"; do
  IFS='|' read -r rid _font where _depth <<<"$r"
  if [ "$gui" != yes ]; then
    echo "$rid BLOCKED(needs_input): no Aqua GUI session for $(ssh "${SSHO[@]}" "$MAC" id -un) on $MAC (console=loginwindow); log in at the console or via Screen Sharing"
    blocked=1; continue
  fi
  if [ "$where" = ssh ] && [ "$sshok" != ok ]; then
    echo "$rid BLOCKED(needs_input): $MAC cannot ssh to $SSH_TARGET ($sshok)"; blocked=1; continue
  fi
  g=$(guid_of "$rid")
  # shellcheck disable=SC2087  # $g/$rid expand client-side; \$ and ~ stay remote
  ssh "${SSHO[@]}" "$MAC" "bash -s" <<SH
pkill -x iTerm2 2>/dev/null; sleep 1
rm -f ~/$REMOTE_DIR/out/$rid.*
defaults write com.googlecode.iterm2 'Default Bookmark Guid' '$g'
open -na ~/Applications/iTerm.app
for i in \$(seq 1 60); do [ -f ~/$REMOTE_DIR/out/$rid.done ] && break; sleep 1; done
[ -f ~/$REMOTE_DIR/out/$rid.done ] || echo 'BLOCKED timeout: no .done from cell.sh after 60s (iTerm2 did not start the profile command)' >~/$REMOTE_DIR/out/$rid.done
cat ~/$REMOTE_DIR/out/$rid.done
pkill -x iTerm2 2>/dev/null || true
SH
  scp -q "$MAC:$REMOTE_DIR/out/$rid.*" "$OUT/" 2>/dev/null || true
  if [ -s "$OUT/$rid.png" ]; then echo "$rid CAPTURED $OUT/$rid.png"; else
    echo "$rid BLOCKED: see $OUT/$rid.done (Screen Recording for iTerm? System Settings > Privacy & Security > Screen & System Audio Recording > iTerm on > Quit & Reopen)"; blocked=1; fi
done
[ "$blocked" = 0 ] || exit 3
