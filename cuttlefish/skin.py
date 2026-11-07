"""The classic-CLI skin: STATIC colours only, installed by an explicit command.

SPEC C10: the classic CLI gets a static colour skin, nothing animated. The skin
file ships at ``skins/cuttlefish.yaml`` in the plugin; ``install`` copies it
into ``<home>/skins/`` (the real core skin loader's directory) but never
selects it — choosing a skin is the user's decision (``display.skin``), not
ours. Uninstall removes the file only when it is still byte-ours: a user-edited
copy is theirs now and stays.
"""

from __future__ import annotations

import os
from pathlib import Path

#: The skin's name (the file stem core's loader looks up: ``skins/<name>.yaml``).
SKIN_NAME = "cuttlefish"

_SKIN_FILE = f"{SKIN_NAME}.yaml"


def skin_source() -> Path:
    """The shipped skin file inside this plugin."""
    return Path(__file__).resolve().parents[1] / "skins" / _SKIN_FILE


def _skin_bytes() -> bytes:
    return skin_source().read_bytes()


def skin_target(hermes_home: Path) -> Path:
    return Path(hermes_home) / "skins" / _SKIN_FILE


def install(hermes_home: Path) -> Path:
    """Write the skin into ``<home>/skins/cuttlefish.yaml``; idempotent.

    One file, written atomically (temp + rename): a crash halfway leaves either
    the old file or the new one, never a half-written skin. Never touches
    config.yaml."""
    home = Path(hermes_home)
    (home / "skins").mkdir(parents=True, exist_ok=True)
    target = skin_target(home)
    data = _skin_bytes()
    if not (target.exists() and target.read_bytes() == data):
        tmp = target.with_name(_SKIN_FILE + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return target


def uninstall(hermes_home: Path) -> bool:
    """Remove the skin; True when ours was removed. A user-edited copy (bytes
    differ from the shipped skin) is the user's and is kept."""
    target = skin_target(hermes_home)
    try:
        ours = target.read_bytes() == _skin_bytes()
    except OSError:
        return False
    if not ours:
        return False
    target.unlink()
    return True
