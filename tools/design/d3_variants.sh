#!/bin/bash
# Dev-only: build a SCRATCH git repo (never pushed to the project remote) holding the evidence harness with a perf-only capture and
# the D3 variants of the plugin as branches v0..vN, ready to be shipped to the render host and run by tools/design/d3_run.sh.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd); S=${1:-/tmp/spike-origin}
mkdir -p "$S"; find "$S" -mindepth 1 -delete; cd "$ROOT"
git archive origin/v2/evidence | tar -x -C "$S"            # tools/desktop (the harness) and its tests
git archive HEAD | tar -x -C "$S"                          # the product tree wins over the evidence branch's older copy
cp tools/design/capture_perf.ts "$S/tools/desktop/capture.ts"
cd "$S"; git init -q; git add -A; git -c user.name=d3 -c user.email=d3@local commit -qm "base: harness (perf-only capture) + product"; BASE=$(git branch --show-current)
variant() { # name, then python snippet editing files
  git checkout -q -b "$1" "$BASE"
  python3 -c "$2"; node desktop/build.mjs >/dev/null 2>&1
  git add -A; git -c user.name=d3 -c user.email=d3@local commit -q --allow-empty -qm "variant $1"; git checkout -q "$BASE"
}
variant v0 "pass"
CULL='
import re
p="desktop/src/adapters/painter.ts"; s=open(p).read()
s=s.replace("const svg = toSvg(\n    renderField({","const svg = toSvg(\n    renderField({",1)
s=s.replace("    v.width,\n    v.height,\n  )\n  const layer","    v.width,\n    v.height,\n  )\n  const layer",1)
open(p,"w").write(s)'
FPS4='
p="desktop/src/adapters/runtime.ts"; s=open(p).read()
s=s.replace("const FRAME_GAP_MS = 190","const FRAME_GAP_MS = 240").replace("const FRAME_GRID_MS = 200","const FRAME_GRID_MS = 250"); open(p,"w").write(s)
p="desktop/src/domain/motion.ts"; s=open(p).read()
s=s.replace("pattern === \x27clouds\x27) return { animate: true, fps: 8 }","pattern === \x27clouds\x27) return { animate: true, fps: 4 }"); open(p,"w").write(s)'
cull() { cat <<EOF
p="desktop/src/adapters/painter.ts"; s=open(p).read()
s=s.replace("  const svg = toSvg(\n    renderField({","  const svg = toSvg(\n    renderField({",1)
i=s.index("  const svg = toSvg("); j=s.index("  const layer")
body=s[i:j]
body=body.replace("  const svg = toSvg(\n    renderField(","  const svg = toSvg(\n    (renderField(").replace("    }),\n    v.width,","    }) as any[]).filter(d => d.alpha >= $1),\n    v.width,")
s=s[:i]+body+s[j:]
open(p,"w").write(s)
EOF
}
variant v1 "$FPS4
$(cull 0.08)"
variant v2 "$FPS4
$(cull 0.2)"
variant v3 "$FPS4"
git branch -a
