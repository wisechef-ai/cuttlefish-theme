#!/usr/bin/env bash
# Runs the G3 measurement for the candidate cadences/renderings. One command: sweep.sh
set -e; cd "$(dirname "$0")"; PY=../../.venv/bin/python
for cfg in "4 48 0" "4 48 1"; do set -- $cfg
  CF_RLE=${CF_RLE:-0} CF_MEMO=$3 CF_FPS=$1 CF_QUANT=$2 CF_KEYS=${CF_KEYS:-240} $PY -u run.py /tmp/cf-spike-13/fps$1-q$2-memo$3-rle${CF_RLE:-0} 2>&1 | grep -v -E "Warn|sys.prefix" > /tmp/cf-spike-13-fps$1-q$2-memo$3-rle${CF_RLE:-0}.log
done
