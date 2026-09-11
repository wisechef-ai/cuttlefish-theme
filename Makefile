.PHONY: test lint proof clean help

# The interpreter that can `import hermes_cli`. Four tests assert against the
# real skin engine (v6 skin-file contract, v8 status-bar tint), so a bare
# `python3` without Hermes on its path reports 4 failures on a healthy tree —
# a red canonical command nobody trusts. Probe the same places Hermes'
# scripts/run_tests.sh does, then fall back to python3 so this stays usable on
# a machine without Hermes installed (those 4 tests then skip, see conftest).
PY := $(shell \
	for p in $(HOME)/.hermes/hermes-agent/venv/bin/python3 \
	         $(HOME)/.hermes/hermes-agent/.venv/bin/python3; do \
	  [ -x "$$p" ] && "$$p" -c 'import hermes_cli' 2>/dev/null && echo "$$p" && break; \
	done; true)
ifeq ($(PY),)
PY := python3
endif

help:
	@echo "make test   - THE canonical command: lint, suite, live proof"
	@echo "make lint   - syntax only (fast)"
	@echo "make proof  - live repaint proof against the real Hermes skin engine"
	@echo "make python - show which interpreter make test will use"

python:
	@echo "$(PY)"
	@$(PY) -c 'import hermes_cli; print("hermes_cli: importable")' 2>/dev/null \
	  || echo "hermes_cli: NOT importable (engine-contract tests will skip)"

# Syntax-only by design: a plugin that will not parse fails silently inside the
# agent's process, so this must be cheap enough to run on every edit.
lint:
	@$(PY) -m compileall -q . -x '\.worktrees|__pycache__|\.git' && echo "lint ok"

test: lint
	@$(PY) -m pytest tests/ -q
	@$(PY) tests/proofs/live_repaint_proof.py
	@$(PY) tests/proofs/running_app_proof.py
	@$(PY) tests/proofs/animated_repaint_proof.py
	@$(PY) tests/proofs/terminal_paint_proof.py

# Needs the Hermes venv on the path; skipped rather than failed when absent, so
# `make test` stays green on a machine without Hermes installed.
proof:
	@$(PY) tests/proofs/live_repaint_proof.py
	@$(PY) tests/proofs/running_app_proof.py
	@$(PY) tests/proofs/animated_repaint_proof.py
	@$(PY) tests/proofs/terminal_paint_proof.py

clean:
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null; true
	@find . -name '*.pyc' -delete 2>/dev/null; true
