# Changelog

## 2.1.0 — the v2.1 language (unreleased)

- **Marks.** The sidebar mark is 24×16 with five coarse silhouettes read at 1×: a small soft oval (resting), a large solid cloud (working), a filled striped chip (needs you), a hollow pale square with a missing corner (error), a ringed eye with a dark core (finished unseen). Ink holds ≥ 3.6:1 on the row, selected or not (WCAG 1.4.11). The strip is the same mark at ×0.875, one nowrap row.
- **Composer rim.** One 10 px pill in every state; only its fill and outline change, echoing the mark.
- **Field.** Organs live only in the reading lane (right of the text and cards, below the header, above the composer). The finished eye-spot is one dark disc anchored in the right gutter. Needs-you and error are quieter.
- **Working on the CPU.** The working state runs at 4 field updates per second, and the field layer keeps the 48 highest-alpha circles (never below the locked 40).

## 2.0.0 — desktop-first

v2 moves the skin to the Hermes Desktop. One plugin, two halves.

- **Desktop colour-pattern language.** Each session keeps its own hue — its identity, for the life of the session — and its state shows as pattern + brightness, never a hue change. Five preset states: `resting` (calm mottle), `working` (slow passing clouds), `needs you` (high-contrast zebra stripes), `error` (blanching to pale), `finished_unseen` (one dark eye-spot). Surfaces: a skin swatch on every sidebar session row, and for the focused session a sparse chromatophore dot field behind the chat, a rim on the composer and a status-bar strip that says the state in words — beside core's own amber/emerald status dots, never over them. Motion is configurable (`still` default, `alive`, `off`) and honours `prefers-reduced-motion`; one budgeted animation loop, parked when nothing moves.
- **Python half.** Approval, clarify and error hooks become `broadcast_plugin_event` events (`plugin.cuttlefish-theme.needs_you`, `plugin.cuttlefish-theme.error`) — state only, never prompt, command or error text. With the Python half off, the Desktop falls back to polling `session.active_list`.
- **Live config.** Everything sits under `plugins.entries.cuttlefish-theme.settings` in `config.yaml`: `intensity`, `motion`, and `states`/`patterns` mappings that remap the presets or add your own. Edits apply without a restart; a rejected value keeps its default and produces a warning, never a crash.
- **Classic CLI: a static colour skin.** `hermes cuttlefish skin` installs it (explicit, never auto-selected); `hermes cuttlefish doctor` reports the resolved config and skin state; `hermes cuttlefish legend` prints the vocabulary.
- **Fixes from the real-Desktop capture (M4).** A direct focus switch no longer maps the session being left to the one being entered (rows showed the wrong state and `finished_unseen` never fired); Ctrl+N unfocuses the stored session. Needs-you stripes are now 8 bands across the field (4 cycles) so they still read as parallel bands in the cropped chat region. Idle no longer re-renders anything (an unchanged view never rewrites the style or notifies the surfaces) and the cloud loop runs at 5 fps to stay inside the CPU budget.
- **Legibility.** State now reads from our own surfaces alone: each sidebar row swatch is a state glyph in the session hue (soft dots · cloud · three diagonal bars · hollow pale ring · dark eye-spot in a halo), the composer rim is one clean band that echoes it (not grain), needs-you in the chat field is diagonal bands of big dots between near-invisible ones, and error swells the dots into soft pale colourless blobs.
- **Legibility, round 2.** The status strip is one nowrap row (the state's words were clipped below the glyph); swatches are 28×14 with heavier marks (bold resting dots, a dashed-oval error outline, one bold dark spot on a light chip for finished-unseen); the rim is 6 px with bold cloud segments for working and a pale wash in a dashed outline for error; error in the field swells into large overlapping pale colourless blobs.
- **Removed: the v1 terminal engine.** The live terminal repaint depended on core hooks that never merged, so it is gone from what ships. The history stays on `main` at `0a33840`.
- **Fixed.** The Python half no longer imports PyYAML at load, so it loads on Hermes runtimes without it (Python 3.14 "No module named 'yaml'"); config is read through core's `hermes_cli.config` and an import guard keeps undeclared imports out of the shipped code.

## 0.5.0 — bioluminescent frame

- Add six deterministic coherent-noise cuttlefish body patterns.
- Add multi-hue chromatophore linework, Rich response separators, and per-cell logo ink.
- Add optional Tier-B chrome renderer with Tier-A fallback for older Hermes cores.
- Pin the uniform OKLab navy ground and document the VTE rendering ceiling.
