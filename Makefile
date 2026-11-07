# Cuttlefish 2.0 — canonical commands. Every heavy target runs niced (host safety, incident 10-21) with TMPDIR=/tmp
# (adam-xps: /home/adam is itself a git repo, and pytest's tmp_path must not land under ~/.hermes).
SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c
PY ?= .venv/bin/python
NODE ?= node
NICE := nice -n 10
export TMPDIR := /tmp

CONTRACT_JS := desktop/test/acceptance/*.test.ts
UNIT_JS := $(wildcard desktop/test/unit/*.test.ts) $(wildcard desktop/test/adapters/*.test.ts)
RELEASE_ONLY := tests/acceptance/test_o7_desktop_evidence.py tests/acceptance/test_o8_submission_kit.py \
                tests/acceptance/test_o7_part1_recompute.py tests/acceptance/test_o8_part1_video_provenance.py \
                tests/acceptance/test_o7_part2_bindings.py tests/acceptance/test_o8_part2_frames.py

.PHONY: help venv build lint unit contract contract-js contract-py test release-check evidence clean

help:
	@echo "make test           THE builder gate: lint + unit + the locked contract (minus release evidence)"
	@echo "make contract       the whole locked contract, strict (missing Hermes = failure)"
	@echo "make release-check  O7 real-Desktop evidence + O8 submission kit (lead, before the tag)"
	@echo "make build          desktop/src -> desktop/plugin.js (deterministic)"
	@echo "make evidence       real-Desktop capture of HEAD on hercules -> evidence/v2 (HEAD must be pushed; ~12 min)"

venv:
	uv venv -q --python /usr/bin/python3 .venv && VIRTUAL_ENV=$$PWD/.venv uv pip install -q -r requirements-dev.txt

build:
	$(NODE) desktop/build.mjs

lint:
	$(PY) -m ruff check .
	$(PY) -m compileall -q -x '(\.venv|node_modules|\.git)' . >/dev/null
	if [ -f desktop/plugin.js ]; then $(NODE) --check desktop/plugin.js; fi
	if [ -d desktop/node_modules ]; then (cd desktop && $(NODE) node_modules/typescript/bin/tsc --noEmit -p .); fi
	echo "lint ok"

unit:
	if [ -n "$(strip $(UNIT_JS))" ]; then $(NICE) $(NODE) --test $(UNIT_JS); fi
	if [ -d tests/unit ]; then $(NICE) $(PY) -m pytest tests/unit -q -p no:cacheprovider; fi

contract-js:
	$(NICE) $(NODE) --test $(CONTRACT_JS)

contract-py:
	$(NICE) $(PY) -m pytest tests/acceptance -q -p no:cacheprovider $(foreach f,$(RELEASE_ONLY),--ignore=$(f))

contract: export CF_STRICT := 1
contract: contract-js contract-py

test: export CF_STRICT := 1
test: lint unit contract-js contract-py

release-check: export CF_STRICT := 1
release-check: contract
	$(NICE) $(PY) -m pytest $(RELEASE_ONLY) -q -p no:cacheprovider

# The O7 capture: hercules fetches HEAD from origin, runs the real Desktop, evidence/v2 is copied back here.
# Three short phases (each < 10 min): see tools/desktop/capture-remote.sh. Re-run on the final head: O7.1 binds plugin.js.
evidence:
	tools/desktop/capture-remote.sh start $$(git rev-parse HEAD)
	until tools/desktop/capture-remote.sh wait; do [ $$? -eq 3 ] || exit 1; done
	tools/desktop/capture-remote.sh fetch

clean:
	find . -name '__pycache__' -type d -prune -not -path './.venv/*' -exec rm -rf {} + ; rm -rf .pytest_cache .metrics coverage
