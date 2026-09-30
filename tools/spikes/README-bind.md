# P0-BIND spikes (05, 06, 11)
Re-run against a temp HERMES_HOME (each script creates its own). Needs `pip install pexpect pyte` and the installed `hermes`.
- 05: `python tools/spikes/05-active-session-binding/run.py OUT [true|false]` (+ `run_lineage.py OUT`)
- 06: `python tools/spikes/06-hook-payloads/run.py OUT both` (+ `run_extra.py`, `run_extra2.py`)
- 11: `python tools/spikes/11-enable-flows/run.py OUT`
Receipts: obsidian-vault/projects/cuttlefish-theme/spikes/{05,06,11}-*.md. Note: first boot of a fresh HERMES_HOME can take minutes on a loaded box (`common.boot` waits up to 15 min).
