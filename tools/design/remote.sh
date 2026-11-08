#!/bin/bash
# Dev-only: sync tools/design + the pure domain to a scratch dir on the render host and run a script there in a niced systemd --user unit.
# usage: tools/design/remote.sh <render.mjs|spike...> [args]   (host/user come from $CF_RENDER_HOST, required)
set -euo pipefail
export SSH_AUTH_SOCK=
H=${CF_RENDER_HOST:?set CF_RENDER_HOST=user@host}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
R=cf2/design/repo
ssh "$H" "mkdir -p $R/tools $R/desktop/src"
tar -C "$ROOT" -cf - tools/design desktop/src/domain | ssh "$H" "tar -C $R -xf -"
ssh "$H" "cd \$HOME/$R && ln -sfn \$HOME/cf2/run/repo/tools/desktop/node_modules \$HOME/$R/tools/design/node_modules; mkdir -p \$HOME/cf2/design/out; find \$HOME/cf2/design/out -mindepth 1 -delete"
SCRIPT=$1; shift
ssh "$H" "systemd-run --user --pipe --wait --collect -p Environment=CF_STATES=${CF_STATES:-} -p Environment=PATH=\$HOME/.hermes/tools/node-26.12.1-linux-x64/bin:/usr/bin:/bin -p Nice=10 -p MemoryMax=4G -p WorkingDirectory=\$HOME/$R/tools/design /usr/bin/env node $SCRIPT \$HOME/cf2/design/out $*" 2>&1 | tail -15
mkdir -p "$ROOT/.design-out"; find "$ROOT/.design-out" -mindepth 1 -delete
scp -q -r "$H:cf2/design/out/." "$ROOT/.design-out/"
echo "fetched to .design-out"
