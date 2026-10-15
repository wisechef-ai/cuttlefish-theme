"""Everything lives under ``<HERMES_HOME>/cuttlefish/`` (CONTRACT §4)."""
import os
import re
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def hermes_home(env=None):
    """Resolve HERMES_HOME the way core does: env HERMES_HOME, else ~/.hermes."""
    v = (os.environ if env is None else env).get("HERMES_HOME")
    return Path(v) if v else Path.home() / ".hermes"


def safe_name(raw):
    return _UNSAFE.sub("_", raw)


def cuttlefish_dir(home):
    return Path(home) / "cuttlefish"


def identity_file(home):
    return cuttlefish_dir(home) / "identity.json"


def identity_lock(home):
    return cuttlefish_dir(home) / "identity.lock"


def hooks_file(home):
    return cuttlefish_dir(home) / "hooks.json"


def bus_dir(home):
    return cuttlefish_dir(home) / "bus"


def bus_file(home, lineage_root):
    return bus_dir(home) / (safe_name(lineage_root) + ".json")
