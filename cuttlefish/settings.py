"""The settings validator — one vocabulary, two halves (contract/config-vectors.json).

The JS twin (``desktop/src/domain``, the desktop half of this plugin) resolves
the SAME shared vectors; this file implements them from the vectors and the
contract's semantics, not from the JS. The rules the vectors pin:

- a rejected FIELD keeps its default (a preset survives with its defaults);
- a rejected NEW state or pattern is dropped whole;
- ``null`` removes a preset (the resting state is required);
- nothing is fatal: garbage in, a usable config out, a warning for every miss.

Pure: stdlib only, no I/O, never mutates its input, never raises.
"""

from __future__ import annotations

import copy
import math
from typing import Any

#: A state is chosen by one of these signals (the desktop derives them).
SIGNALS = ("idle", "busy", "tool", "needs_input", "failed", "unseen", "compacting", "subagents", "offline")
#: The pattern vocabulary (SPEC C8): five kinds of skin language.
PATTERN_KINDS = ("mottle", "clouds", "zebra", "blanch", "eyespot")
#: Motion is configurable (SPEC C3): still by default, off means static only.
MOTIONS = ("still", "alive", "off")

#: Numeric bounds, shared with the desktop (config-vectors.json "ranges").
RANGES = {"intensity": (0, 2), "density": (0.25, 4), "contrast": (0, 2), "scale": (0.25, 4),
          "priority": (-1000, 1000)}
LABEL_MAX = 24

_STATE_FIELDS = ("when", "pattern", "priority", "label")
_PATTERN_FIELDS = ("base", "density", "contrast", "scale")

#: What an empty config resolves to (identical to the vectors' "defaults").
DEFAULT_SETTINGS: dict[str, Any] = {
    "intensity": 1,
    "motion": "still",
    "states": {
        "resting":         {"when": "idle",        "pattern": "mottle",  "priority": 0,   "label": ""},
        "working":         {"when": "busy",        "pattern": "clouds",  "priority": 60,  "label": "working"},
        "needs_you":       {"when": "needs_input", "pattern": "zebra",   "priority": 100, "label": "needs you"},
        "error":           {"when": "failed",      "pattern": "blanch",  "priority": 80,  "label": "error"},
        "finished_unseen": {"when": "unseen",      "pattern": "eyespot", "priority": 40,  "label": "done"},
    },
    "patterns": {
        "mottle":  {"base": "mottle",  "density": 1, "contrast": 1, "scale": 1},
        "clouds":  {"base": "clouds",  "density": 1, "contrast": 1, "scale": 1},
        "zebra":   {"base": "zebra",   "density": 1, "contrast": 1, "scale": 1},
        "blanch":  {"base": "blanch",  "density": 1, "contrast": 1, "scale": 1},
        "eyespot": {"base": "eyespot", "density": 1, "contrast": 1, "scale": 1},
    },
}


def _warn(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}


def _number(value: Any, field: str) -> tuple[Any, str | None]:
    """(the value, None) when *value* is a finite in-range number (bools are not
    numbers), else (None, why it was rejected: "type" or "range")."""
    lo, hi = RANGES[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "type"
    if not math.isfinite(value) or not lo <= value <= hi:
        return None, "range"
    return value, None


def _label(value: Any) -> tuple[str | None, str | None]:
    """Same contract as :func:`_number` for a state label (a short string)."""
    if not isinstance(value, str):
        return None, "type"
    if len(value) > LABEL_MAX:
        return None, "range"
    return value, None


def resolve_settings(raw: Any) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Resolve *raw* (the ``settings:`` mapping from config.yaml, any YAML value)
    into ``(settings, warnings)``. A rejected field keeps its default; a rejected
    new state or pattern is dropped whole; never mutates *raw*."""
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if raw is None:
        return settings, []
    if not isinstance(raw, dict):
        return settings, [_warn("settings", "type",
                                f"settings must be a mapping, got {type(raw).__name__}")]
    warnings: list[dict[str, str]] = []
    _apply_section(settings, warnings, "patterns", raw.get("patterns"), _apply_pattern)  # first: states may use new patterns
    _apply_section(settings, warnings, "states", raw.get("states"), _apply_state)
    _apply_intensity(settings, warnings, raw.get("intensity"))
    _apply_motion(settings, warnings, raw.get("motion"))
    for key in raw:
        if key not in ("intensity", "motion", "states", "patterns"):
            warnings.append(_warn(str(key), "unknown",
                                  f"unknown setting {key!r} (known: intensity, motion, states, patterns)"))
    return settings, warnings


def _apply_intensity(settings: dict, warnings: list, value: Any) -> None:
    if value is None:
        return
    number, why = _number(value, "intensity")
    if why is not None:
        warnings.append(_warn("intensity", why, f"intensity must be a number in {RANGES['intensity']}, got {value!r}"))
    else:
        settings["intensity"] = number


def _apply_motion(settings: dict, warnings: list, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and value in MOTIONS:
        settings["motion"] = value
    else:
        warnings.append(_warn("motion", "enum", f"motion must be one of {list(MOTIONS)}, got {value!r}"))


def _apply_section(settings: dict, warnings: list, section: str, raw_section: Any, apply_one) -> None:
    """Walk one settings section (``states``/``patterns``): absent is fine, a
    non-mapping warns as a type, otherwise apply each entry through *apply_one*."""
    if raw_section is None:
        return
    if not isinstance(raw_section, dict):
        warnings.append(_warn(section, "type",
                              f"{section} must be a mapping of name -> spec (or null to remove), "
                              f"got {type(raw_section).__name__}"))
        return
    for name, spec in raw_section.items():
        apply_one(settings, warnings, str(name), spec)


def _apply_state(settings: dict, warnings: list, name: str, spec: Any) -> None:
    if not _entry(settings, warnings, "states", name, spec, unremovable=_only_resting):
        return
    if name in DEFAULT_SETTINGS["states"]:
        _tune_preset(settings, warnings, name, spec)
    else:
        _add_state(settings, warnings, name, spec)


def _tune_preset(settings: dict, warnings: list, name: str, spec: dict) -> None:
    """Remap a preset: every field keeps its default when the input is rejected."""
    state = settings["states"][name]
    _state_when(state, warnings, f"states.{name}", spec)
    _state_pattern(state, warnings, f"states.{name}", spec, settings)
    _state_priority(state, warnings, f"states.{name}", spec)
    _state_label(state, warnings, f"states.{name}", spec)
    _unknown_keys(warnings, f"states.{name}", spec, _STATE_FIELDS)


def _add_state(settings: dict, warnings: list, name: str, spec: dict) -> None:
    """A user-added state: needs a signal, a known pattern and a priority;
    any rejection drops it whole. Its label defaults to its name."""
    state, problems = _new_state_fields(name, spec, settings)
    warnings.extend(problems)
    if problems:
        return  # a rejected new state is dropped whole
    settings["states"][name] = state
    _unknown_keys(warnings, f"states.{name}", spec, _STATE_FIELDS)


def _new_state_fields(name: str, spec: dict, settings: dict) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Validate a user-added state's four fields; (the accepted ones, the problems)."""
    path = f"states.{name}"
    state: dict[str, Any] = {}
    problems: list[dict[str, str]] = []
    _need_signal(state, problems, path, name, spec.get("when"))
    _need_pattern(state, problems, path, name, spec.get("pattern"), settings)
    _need_priority(state, problems, path, name, spec.get("priority"))
    label, why = _label(spec["label"] if "label" in spec else name)
    if why is not None:
        problems.append(_warn(f"{path}.label", why, f"label must be a string of at most {LABEL_MAX} chars"))
    else:
        state["label"] = label
    return state, problems


def _need_signal(state: dict, problems: list, path: str, name: str, when: Any) -> None:
    if when is None:
        problems.append(_warn(f"{path}.when", "missing", f"new state {name!r} needs a when (a signal)"))
    elif not (isinstance(when, str) and when in SIGNALS):
        problems.append(_warn(f"{path}.when", "enum", f"unknown signal {when!r} (one of {list(SIGNALS)})"))
    else:
        state["when"] = when


def _need_pattern(state: dict, problems: list, path: str, name: str, pattern: Any, settings: dict) -> None:
    if pattern is None:
        problems.append(_warn(f"{path}.pattern", "missing", f"new state {name!r} needs a pattern"))
    elif not (isinstance(pattern, str) and pattern in settings["patterns"]):
        problems.append(_warn(f"{path}.pattern", "unknown", f"unknown pattern {pattern!r}"))
    else:
        state["pattern"] = pattern


def _need_priority(state: dict, problems: list, path: str, name: str, priority: Any) -> None:
    if priority is None:
        problems.append(_warn(f"{path}.priority", "missing", f"new state {name!r} needs a priority"))
        return
    number, why = _number(priority, "priority")
    if why is not None:
        problems.append(_warn(f"{path}.priority", why,
                              f"priority must be an integer in {RANGES['priority']}, got {priority!r}"))
    else:
        state["priority"] = number


def _state_when(state: dict, warnings: list, path: str, spec: dict) -> None:
    when = spec.get("when")
    if when is None:
        return
    if isinstance(when, str) and when in SIGNALS:
        state["when"] = when
    else:
        warnings.append(_warn(f"{path}.when", "enum", f"unknown signal {when!r} (one of {list(SIGNALS)})"))


def _state_pattern(state: dict, warnings: list, path: str, spec: dict, settings: dict) -> None:
    pattern = spec.get("pattern")
    if pattern is None:
        return
    if isinstance(pattern, str) and pattern in settings["patterns"]:
        state["pattern"] = pattern
    else:
        warnings.append(_warn(f"{path}.pattern", "unknown",
                              f"unknown pattern {pattern!r} (kept {state['pattern']!r})"))


def _state_priority(state: dict, warnings: list, path: str, spec: dict) -> None:
    priority = spec.get("priority")
    if priority is None:
        return
    number, why = _number(priority, "priority")
    if why is not None:
        warnings.append(_warn(f"{path}.priority", why,
                              f"priority must be an integer in {RANGES['priority']}, got {priority!r}"))
    else:
        state["priority"] = number


def _state_label(state: dict, warnings: list, path: str, spec: dict) -> None:
    if "label" not in spec or spec["label"] is None:
        return
    label, why = _label(spec["label"])
    if why is not None:
        warnings.append(_warn(f"{path}.label", why, f"label must be a string of at most {LABEL_MAX} chars"))
    else:
        state["label"] = label


def _entry(settings: dict, warnings: list, section: str, name: str, spec: Any, unremovable) -> bool:
    """The null / non-mapping cases "states" and "patterns" share: ``null``
    removes a built-in entry unless *unremovable*(name) says it must stay, and a
    non-mapping warns as a type. True when *spec* is a mapping the caller
    should go on to validate."""
    kind = section[:-1]  # states -> state, patterns -> pattern
    path = f"{section}.{name}"
    if spec is None:
        if name not in DEFAULT_SETTINGS[section]:
            return False  # removing something not configured here: nothing to do
        if unremovable(name):
            warnings.append(_warn(path, "required", f"the built-in {kind} {name!r} cannot be removed"))
        else:
            settings[section].pop(name, None)
        return False
    if not isinstance(spec, dict):
        warnings.append(_warn(path, "type",
                              f"{kind} {name!r} must be a mapping (or null to remove), got {type(spec).__name__}"))
        return False
    return True


def _only_resting(name: str) -> bool:
    """The one state that must always exist: something is showing at rest."""
    return name == "resting"


def _every_builtin(_name: str) -> bool:
    """Every built-in pattern stays: the five pattern kinds are the vocabulary."""
    return True


def _apply_pattern(settings: dict, warnings: list, name: str, spec: Any) -> None:
    if not _entry(settings, warnings, "patterns", name, spec, unremovable=_every_builtin):
        return
    if name in DEFAULT_SETTINGS["patterns"]:
        _tune_builtin_pattern(settings, warnings, name, spec)
    else:
        _add_pattern(settings, warnings, name, spec)


def _tune_builtin_pattern(settings: dict, warnings: list, name: str, spec: dict) -> None:
    """Tune a built-in pattern's parameters; its base (its name) is fixed."""
    pattern = settings["patterns"][name]
    base = spec.get("base")
    if base is not None and base != name:
        warnings.append(_warn(f"patterns.{name}.base", "required",
                              f"a built-in pattern's base is fixed: {name!r} keeps base {name!r}"))
    _pattern_params(pattern, warnings, f"patterns.{name}", spec)
    _unknown_keys(warnings, f"patterns.{name}", spec, _PATTERN_FIELDS)


def _add_pattern(settings: dict, warnings: list, name: str, spec: dict) -> None:
    """A user-added pattern: needs a valid base; parameters default to 1 and a
    rejected parameter keeps its default (the pattern survives)."""
    base = spec.get("base")
    if base is None:
        warnings.append(_warn(f"patterns.{name}.base", "missing",
                              f"new pattern {name!r} needs a base (one of {list(PATTERN_KINDS)})"))
        return
    if not (isinstance(base, str) and base in PATTERN_KINDS):
        warnings.append(_warn(f"patterns.{name}.base", "enum",
                              f"unknown pattern base {base!r} (one of {list(PATTERN_KINDS)})"))
        return
    pattern = {"base": base, "density": 1, "contrast": 1, "scale": 1}
    _pattern_params(pattern, warnings, f"patterns.{name}", spec)
    settings["patterns"][name] = pattern
    _unknown_keys(warnings, f"patterns.{name}", spec, _PATTERN_FIELDS)


def _pattern_params(pattern: dict, warnings: list, path: str, spec: dict) -> None:
    for field in ("density", "contrast", "scale"):
        if spec.get(field) is None:
            continue
        number, why = _number(spec[field], field)
        if why is not None:
            warnings.append(_warn(f"{path}.{field}", why,
                                  f"{field} must be a number in {RANGES[field]}, got {spec[field]!r}"))
        else:
            pattern[field] = number


def _unknown_keys(warnings: list, path: str, spec: dict, known: tuple[str, ...]) -> None:
    for key in spec:
        if key not in known:
            warnings.append(_warn(f"{path}.{key}", "unknown", f"unknown key {key!r} (known: {list(known)})"))
