#!/bin/bash
# Dev-only: sync tools/design + the pure domain to a scratch dir on the render host and run a script there in a niced systemd --user unit.
# usage: tools/design/remote.sh <render.mjs|spike...> [args]   (host/user come from $CF_RENDER_HOST, required)
set -euo pipefail
export SSH_AUTH_SOCK=
H=${CF_RENDER_HOST:?set CF_RENDER_HOST=user@host}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
R=cf2/design/repo
ssh "$H" "mkdir -p $R/tools $R/desktop/src"
tar -C "$ROOT" -cf - tools/design desktop/src/domain docs/design/field-f1-f2.patch | ssh "$H" "tar -C $R -xf -"
ssh "$H" "cd \$HOME/$R && patch -s -p1 < docs/design/field-f1-f2.patch; ln -sfn \$HOME/cf2/run/repo/tools/desktop/node_modules \$HOME/$R/tools/design/node_modules; rm -rf \$HOME/cf2/design/out; mkdir -p \$HOME/cf2/design/out"
SCRIPT=$1; shift
ssh "$H" "systemd-run --user --pipe --wait --collect -p Environment=PATH=\$HOME/.hermes/tools/node-26.12.1-linux-x64/bin:/usr/bin:/bin -p Nice=10 -p MemoryMax=4G -p WorkingDirectory=\$HOME/$R/tools/design /usr/bin/env node $SCRIPT \$HOME/cf2/design/out $*" 2>&1 | tail -15
rm -rf "$ROOT/.design-out"; mkdir -p "$ROOT/.design-out"
scp -q -r "$H:cf2/design/out/." "$ROOT/.design-out/"
echo "fetched to .design-out"
