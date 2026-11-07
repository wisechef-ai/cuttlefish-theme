# Changelog

## 2.0.0 — desktop-first

v2 moves the skin to the Hermes Desktop. One plugin, two halves.

- **Desktop colour-pattern language.** Each session keeps its own hue — its identity, for the life of the session — and its state shows as pattern + brightness, never a hue change. Five preset states: `resting` (calm mottle), `working` (slow passing clouds), `needs you` (high-contrast zebra stripes), `error` (blanching to pale), `finished_unseen` (one dark eye-spot). Surfaces: a skin swatch on every sidebar session row, and for the focused session a sparse chromatophore dot field behind the chat, a rim on the composer and a status-bar strip that says the state in words — beside core's own amber/emerald status dots, never over them. Motion is configurable (`still` default, `alive`, `off`) and honours `prefers-reduced-motion`; one budgeted animation loop, parked when nothing moves.
- **Python half.** Approval, clarify and error hooks become `broadcast_plugin_event` events (`plugin.cuttlefish-theme.needs_you`, `plugin.cuttlefish-theme.error`) — state only, never prompt, command or error text. With the Python half off, the Desktop falls back to polling `session.active_list`.
- **Live config.** Everything sits under `plugins.entries.cuttlefish-theme.settings` in `config.yaml`: `intensity`, `motion`, and `states`/`patterns` mappings that remap the presets or add your own. Edits apply without a restart; a rejected value keeps its default and produces a warning, never a crash.
- **Classic CLI: a static colour skin.** `hermes cuttlefish skin` installs it (explicit, never auto-selected); `hermes cuttlefish doctor` reports the resolved config and skin state; `hermes cuttlefish legend` prints the vocabulary.
- **Removed: the v1 terminal engine.** The live terminal repaint depended on core hooks that never merged, so it is gone from what ships. The history stays on `main` at `0a33840`.

## 0.5.0 — bioluminescent frame

- Add six deterministic coherent-noise cuttlefish body patterns.
- Add multi-hue chromatophore linework, Rich response separators, and per-cell logo ink.
- Add optional Tier-B chrome renderer with Tier-A fallback for older Hermes cores.
- Pin the uniform OKLab navy ground and document the VTE rendering ceiling.
