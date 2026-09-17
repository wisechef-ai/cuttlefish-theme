"""Make the repo importable as the `cuttlefish_theme` package during tests.

Hermes loads a plugin directory AS the package, so the package root is this repo
root. Tests need the PARENT directory on sys.path to `import cuttlefish_theme`, and
the repo directory itself may be named anything (a clone, a worktree), so we bind
the module name explicitly rather than trusting the directory basename.
"""

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

if "cuttlefish_theme" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "cuttlefish_theme", _ROOT / "__init__.py",
        submodule_search_locations=[str(_ROOT)],
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        _mod.__path__ = [str(_ROOT)]
        sys.modules["cuttlefish_theme"] = _mod
        _spec.loader.exec_module(_mod)


def pytest_configure(config):
    """Point every registry read at an empty, test-owned file.

    The renderer resolves peers from the HOST's live
    ``~/.hermes/runtime/active_sessions.json``. Without this, the suite's
    colours depend on which sessions happen to be running on the machine
    executing the tests — measured, the same test passed alone and failed
    in file order purely because the host's live sessions leaked into
    identity allocation. A test suite must be a function of the repo, not
    of the machine it runs on.
    """
    import os
    import tempfile

    empty_registry = Path(tempfile.gettempdir()) / "cuttlefish-tests-empty-registry.json"
    empty_registry.write_text("[]")
    os.environ["CUTTLEFISH_SESSION_REGISTRY"] = str(empty_registry)


def pytest_unconfigure(config):
    import os
    os.environ.pop("CUTTLEFISH_SESSION_REGISTRY", None)
