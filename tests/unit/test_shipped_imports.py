"""Unit: every import in the SHIPPED Python is stdlib, our own package, a Hermes core module, or a declared exception.

This is the class of defect that shipped in 2.0.0-dev: a third-party import (PyYAML) that the dev venv had and a Hermes
runtime does not. The walk is over every import statement (module level or lazy), so it cannot be dodged by moving an
import into a function. The allowances are closed lists below; adding one is a deliberate, reviewed change.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]

#: Modules a Hermes runtime always provides (core's own import surface). Plugins may import these freely.
CORE = frozenset({"hermes_cli", "hermes_yaml", "hermes_constants", "tui_gateway", "gateway", "agent", "tools"})

#: Our own package, under either name the host or the tests load it by.
OWN = frozenset({"cuttlefish", "cuttlefish_theme"})

#: Provided by the host, but only where the host loads the file: FastAPI is supplied by the Hermes dashboard server,
#: and ``dashboard/`` is loaded only there. Anywhere else it is an undeclared dependency.
HOST_PROVIDED = {"fastapi": ("dashboard/",)}

#: Optional third-party modules, allowed ONLY inside a ``try`` whose handler catches ImportError (lazy, degradable).
OPTIONAL = frozenset({
    "yaml",  # PyYAML: a standalone/dev convenience. The runtime parser is core's hermes_yaml (liveconfig._parse_yaml).
})

_IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError"}


def _catches_import_error(node: ast.Try) -> bool:
    for handler in node.handlers:
        if handler.type is None:
            return True
        kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
        if any(isinstance(k, ast.Name) and k.id in _IMPORT_ERRORS for k in kinds):
            return True
    return False


def _judge(name: str, level: int, guarded: bool, relpath: str, lineno: int, found: list[str]) -> None:
    if level or not name:  # package-relative (``from . import x``): ours by construction
        return
    top = name.split(".")[0]
    if top in sys.stdlib_module_names or top in OWN or top in CORE:
        return
    if top in HOST_PROVIDED and relpath.startswith(HOST_PROVIDED[top]):
        return
    if top in OPTIONAL and guarded:
        return
    found.append(f"{relpath}:{lineno} import {name}")


def _visit(node: ast.AST, guarded: bool, relpath: str, found: list[str]) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            _judge(alias.name, 0, guarded, relpath, node.lineno, found)
    elif isinstance(node, ast.ImportFrom):
        _judge(node.module or "", node.level, guarded, relpath, node.lineno, found)
    if isinstance(node, ast.Try):
        inside = guarded or _catches_import_error(node)
        for child in node.body:
            _visit(child, inside, relpath, found)
        for child in [*node.handlers, *node.orelse, *node.finalbody]:
            _visit(child, guarded, relpath, found)
        return
    for child in ast.iter_child_nodes(node):
        _visit(child, guarded, relpath, found)


def undeclared_imports(relpath: str, source: str) -> list[str]:
    found: list[str] = []
    _visit(ast.parse(source, filename=relpath), False, relpath, found)
    return found


def _shipped() -> list[Path]:
    return [ROOT / "__init__.py", *sorted((ROOT / "cuttlefish").glob("*.py")),
            *sorted((ROOT / "dashboard").rglob("*.py"))]


def test_every_shipped_import_is_stdlib_own_core_or_declared():
    files = _shipped()
    assert any(p.name == "liveconfig.py" for p in files), "the walk must see the real package, not nothing"
    offenders = []
    for path in files:
        relpath = path.relative_to(ROOT).as_posix()
        offenders += undeclared_imports(relpath, path.read_text(encoding="utf-8"))
    assert offenders == [], "undeclared runtime imports (a Hermes host may not have them):\n" + "\n".join(offenders)


def test_the_guard_flags_a_bare_third_party_import():
    assert undeclared_imports("cuttlefish/x.py", "import yaml\n") == ["cuttlefish/x.py:1 import yaml"]
    assert undeclared_imports("cuttlefish/x.py", "def f():\n    import yaml\n")  # lazy but unguarded: still flagged
    assert undeclared_imports("cuttlefish/x.py", "from requests import get\n")
    assert undeclared_imports("cuttlefish/x.py", "try:\n    import yaml\nexcept ValueError:\n    pass\n")


def test_the_guard_allows_what_is_declared():
    ok = [
        "import json\nfrom pathlib import Path\n",
        "from hermes_yaml import safe_load\n",
        "from hermes_cli.config import get_process_hermes_home\n",
        "from .settings import resolve_settings\n",
        "from . import events\n",
        "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n",
        "try:\n    import yaml\nexcept (ImportError, OSError):\n    pass\n",
    ]
    for source in ok:
        assert undeclared_imports("cuttlefish/x.py", source) == [], source


def test_fastapi_is_allowed_only_where_the_host_loads_it():
    assert undeclared_imports("dashboard/plugin_api.py", "from fastapi import APIRouter\n") == []
    assert undeclared_imports("cuttlefish/x.py", "from fastapi import APIRouter\n")
