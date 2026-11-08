#!/bin/bash
# Dev-only: a SCRATCH git repo = HEAD of the product + a candidate desktop/src tree ($1, e.g. /tmp/f4/desktop), branch `r4`, for the real-Desktop capture.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); CAND=${1:?candidate desktop dir}; S=${2:-/tmp/spike-r4}
mkdir -p "$S"; find "$S" -mindepth 1 -delete; cd "$ROOT"
git archive HEAD | tar -x -C "$S"
cd "$S"; git init -q; git add -A; git -c user.name=d3 -c user.email=d3@local commit -qm base
git checkout -q -b r4
cp -r "$CAND"/src/. desktop/src/
node desktop/build.mjs >/dev/null 2>&1
git add -A; git -c user.name=d3 -c user.email=d3@local commit -qm "r4 candidate"
echo built "$S"
