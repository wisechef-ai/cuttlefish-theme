#!/bin/bash
# Dev-only: a SCRATCH git repo (never pushed to the project remote) = HEAD of the product + the candidate field changes, branch `fix`, so the
# real-Desktop capture (tools/desktop/capture.sh via d3_run.sh-style unit) can measure it. usage: spike_build.sh [dir]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); S=${1:-/tmp/spike2-origin}
mkdir -p "$S"; find "$S" -mindepth 1 -delete; cd "$ROOT"
git archive HEAD | tar -x -C "$S"
cd "$S"; git init -q; git add -A; git -c user.name=d3 -c user.email=d3@local commit -qm base; BASE=$(git branch --show-current)
git checkout -q -b fix
python3 - <<'P'
import re
p="desktop/src/adapters/painter.ts"; s=open(p).read()
s=s.replace("    layerCircles(renderField({","    layerFor(v.pattern.base, renderField({")
s=s.replace("export function layerCircles(","/** The circle budget is for the only state that repaints (the working clouds); a static field draws every organ (the stripes need the dim ones). */\nexport function layerFor(base: string, dots: readonly Dot[]): Dot[] {\n  return base === 'clouds' ? layerCircles(dots) : dots.filter(d => d.alpha > 0 && d.r > 0)\n}\nexport function layerCircles(",1)
open(p,"w").write(s)
P
if [ -n "${CF_DOMAIN_FIX:-}" ]; then cp "$CF_DOMAIN_FIX"/pattern.ts "$CF_DOMAIN_FIX"/field.ts desktop/src/domain/; fi
node desktop/build.mjs >/dev/null 2>&1
git add -A; git -c user.name=d3 -c user.email=d3@local commit -qm "fix: budget only for clouds; error fewer not bigger"
echo built "$S" branch fix
