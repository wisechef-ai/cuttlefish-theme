#!/bin/bash
# Dev-only: ship the scratch repo made by d3_variants.sh to the render host and run the perf-only capture for each variant, one after the other,
# in a niced, memory-capped systemd --user unit. usage: d3_run.sh start "v0 v1 v2" | status | fetch
set -euo pipefail
export SSH_AUTH_SOCK=
H=${CF_RENDER_HOST:?set CF_RENDER_HOST=user@host}; S=${CF_SPIKE_SRC:-/tmp/spike-origin}
case "${1:?start|status|fetch}" in
  start)
    ssh "$H" "rm -rf ~/cf2/spike/origin ~/cf2/spike/results; mkdir -p ~/cf2/spike/results ~/cf2/spike/logs"
    tar -C "$S" -cf - . | ssh "$H" "mkdir -p ~/cf2/spike/origin && tar -C ~/cf2/spike/origin -xf -"
    ssh "$H" "cp ~/cf2/spike/origin/tools/desktop/capture.sh ~/cf2/spike/capture.sh; : > ~/cf2/spike/logs/run.log; systemd-run --user --unit=cf2-d3 --collect -p Nice=10 -p MemoryMax=24G -p WorkingDirectory=\$HOME \
      -p StandardOutput=append:\$HOME/cf2/spike/logs/run.log -p StandardError=append:\$HOME/cf2/spike/logs/run.log /bin/bash -lc 'for v in ${2:-v0 v1}; do echo === \$v; CF_VARIANT=\$v CF_RUN_DIR=\$HOME/cf2/spike/run CF_ORIGIN=\$HOME/cf2/spike/origin bash \$HOME/cf2/spike/capture.sh \$v && cp \$HOME/cf2/spike/run/evidence/v2/perf-summary.json \$HOME/cf2/spike/results/\$v.json; echo EXIT_\$v=\$?; done; echo ALLDONE'" ;;
  status) ssh "$H" "tail -n 12 ~/cf2/spike/logs/run.log; ls ~/cf2/spike/results" ;;
  fetch) mkdir -p "${2:-.design-out/d3}"; scp -q -r "$H:cf2/spike/results/." "${2:-.design-out/d3}/"; scp -q "$H:cf2/spike/logs/run.log" "${2:-.design-out/d3}/run.log" ;;
esac
