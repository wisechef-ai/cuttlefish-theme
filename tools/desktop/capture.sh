#!/bin/bash
# THE capture, on hercules (dev only):  tools/desktop/capture.sh <commit-or-branch> [WxH]   (WxH: window size, default 1600x1000)
#
# Fetches that commit into a PRIVATE clone (~/cf2/run/repo; never the working checkout), runs the harness unit tests,
# then the real-Desktop capture, which records everything under <clone>/evidence/v2 (sandbox up -> scenario -> video,
# stills, pixels, perf -> manifest -> sandbox down). Builds nothing in the product: desktop/plugin.js is what the commit ships.
# Heavy: run it in a unit (capture-remote.sh does). Isolation is asserted in code; if it breaks the run aborts.
set -euo pipefail
COMMIT=${1:?usage: capture.sh <commit-or-branch> [WxH]}
SIZE=${2:-}   # empty = the default window (evidence/v2); 1280x800 writes evidence/v2-1280x800
export PATH=$HOME/.hermes/tools/node-26.12.1-linux-x64/bin:$PATH TMPDIR=/tmp
export CF_HERMES_CORE=${CF_HERMES_CORE:-$HOME/repos/hackathon/hermes-core} CF_SANDBOXES=${CF_SANDBOXES:-$HOME/repos/hackathon/sandboxes}
export CF_HERMES_PYTHON=${CF_HERMES_PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python} CF_DISPLAY=${CF_DISPLAY:-:93}
RUN=${CF_RUN_DIR:-$HOME/cf2/run/repo}
ORIGIN=${CF_ORIGIN:-https://github.com/wisechef-ai/cuttlefish-theme.git}

core=$(git -C "$CF_HERMES_CORE" rev-parse HEAD)
case "$core" in b200f5bc60e*) ;; *) echo "core is $core, not v0.22.7 (b200f5bc60e)"; exit 2;; esac
[ -d "$RUN/.git" ] || { mkdir -p "$(dirname "$RUN")"; git clone -q "$ORIGIN" "$RUN"; }
cd "$RUN"
git reset -q --hard && git clean -fdq   # this clone is private to the capture: no hand edits survive
git fetch -q origin '+refs/heads/*:refs/remotes/origin/*'
sha=$(git rev-parse --verify -q "$COMMIT^{commit}" || git rev-parse --verify "origin/$COMMIT^{commit}")
git checkout -q --detach "$sha"
echo "capture of $sha (core $core)"
(cd tools/desktop && npm ci --silent --no-audit --no-fund)
node --test tools/desktop/evidence_lib.test.ts tools/desktop/manifest.test.ts tools/desktop/harness.test.ts
node tools/desktop/capture.ts $SIZE
echo "evidence: $RUN/evidence/v2${SIZE:+-$SIZE} (commit $sha)"
