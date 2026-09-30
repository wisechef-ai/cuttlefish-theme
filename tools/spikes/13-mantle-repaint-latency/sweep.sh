#!/usr/bin/env bash
# G3 measurement for spike 13. One command: sweep.sh [outroot]
# Sequential by design (parallel runs contend for the same cores and invalidate each other).
# Tuned config x CF_REPEATS (default 3) fresh homes, then each swept sibling variant once. run.py exits 3 on an
# unsettled/loaded run and writes no verdict inputs; summarize.py turns the results into pass/fail/indeterminate.
set -u; cd "$(dirname "$0")"; PY=${PY:-../../.venv/bin/python}; OUT=${1:-/tmp/cf-spike-13}; mkdir -p "$OUT"
run() { local n=$1; shift
  CF_FPS=$1 CF_QUANT=$2 CF_MEMO=$3 CF_RLE=$4 CF_KEYS=${CF_KEYS:-240} "$PY" -u run.py "$OUT/$n" > "$OUT/$n.log" 2>&1
  echo "$n exit=$?"; }
for i in $(seq 1 "${CF_REPEATS:-3}"); do run "tuned-$i" 4 48 1 1; done
for cfg in "6 0 0 0" "4 0 0 0" "4 48 0 0" "4 48 1 0" "6 0 1 0" "4 48 0 1"; do set -- $cfg
  run "v-fps$1-q$2-memo$3-rle$4" "$@"; done
"$PY" summarize.py "$OUT"/*/results.json
