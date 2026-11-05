"""ACCEPTANCE CONTRACT — structure: the folder IS the architecture (PLAN-v22 §13.3, review-enforced + this file) (locked).

The bar includes clean code, which behaviour cannot see. Pure domain, adapters only translate, the shipped bundle is a
deterministic build of the sources in this tree, and the v1 terminal engine (which depended on unmerged core hooks)
is gone from what ships.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from .helpers import ROOT, STRICT

DOMAIN = ROOT / "desktop" / "src" / "domain"
NODE = os.environ.get("CF_NODE", shutil.which("node") or "node")
V1_ENGINE = ["mantle.py", "chrome.py", "live.py", "termbg.py", "field.py", "morph.py", "linework.py", "pattern.py",
             "patterns.py", "palette.py", "session.py", "skinio.py", "banner.py", "bootstrap.py", "seed.py", "naming.py",
             "plugin.py", "cli.py", "v19_adapter.py"]
IMPURE = {
    "SDK/React import": r"""from\s+['"](@hermes/plugin-sdk|react|react/jsx-runtime)['"]""",
    "DOM": r"\b(document|window|globalThis|navigator)\.",
    "clock": r"\b(Date\.now|performance\.now|new Date)\b",
    "randomness": r"\bMath\.random\b",
    "timers": r"\b(setTimeout|setInterval|requestAnimationFrame)\b",
}


def _ts(dirpath: Path) -> list[Path]:
    return sorted(p for p in dirpath.rglob("*.ts") if ".test." not in p.name)


def test_S1_domain_is_pure():
    files = _ts(DOMAIN)
    assert files, "desktop/src/domain is empty"
    bad = []
    for f in files:
        src = f.read_text()
        for name, rx in IMPURE.items():
            if re.search(rx, src):
                bad.append(f"{f.relative_to(ROOT)}: {name}")
        for spec in re.findall(r"""from\s+['"]([^'"]+)['"]""", src):
            if not spec.startswith("./"):
                bad.append(f"{f.relative_to(ROOT)}: imports {spec} (domain imports only its siblings)")
    assert bad == [], "\n".join(bad)


def test_S2_every_domain_module_is_reachable_from_the_index():
    assert (DOMAIN / "index.ts").is_file(), "desktop/src/domain/index.ts is the domain's one public door"
    seen, todo = set(), [DOMAIN / "index.ts"]
    while todo:
        f = todo.pop()
        if f in seen or not f.is_file():
            continue
        seen.add(f)
        for spec in re.findall(r"""(?:from|import)\s+['"](\./[^'"]+)['"]""", f.read_text()):
            todo.append((f.parent / spec).resolve())
    dead = [p.relative_to(ROOT).as_posix() for p in _ts(DOMAIN) if p.resolve() not in {s.resolve() for s in seen}]
    assert dead == [], f"dead domain modules: {dead}"


def test_S3_adapters_never_reach_into_the_domain_internals():
    adapters = ROOT / "desktop" / "src" / "adapters"
    files = _ts(adapters)
    assert files, "desktop/src/adapters is empty"
    bad = []
    for f in files:
        for spec in re.findall(r"""from\s+['"]([^'"]+)['"]""", f.read_text()):
            if "/domain/" in spec and not spec.endswith("/domain/index.ts"):
                bad.append(f"{f.relative_to(ROOT)} imports {spec} (use the domain's public index)")
    assert bad == [], "\n".join(bad)


def test_S4_bundle_is_a_fresh_deterministic_build():
    build = ROOT / "desktop" / "build.mjs"
    assert build.is_file()
    if not (ROOT / "desktop" / "node_modules").is_dir():
        msg = "desktop/node_modules missing: npm ci --prefix desktop"
        pytest.fail(msg) if STRICT else pytest.skip(msg)
    r = subprocess.run([NODE, str(build), "--check"], capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, f"desktop/plugin.js is stale or non-deterministic:\n{r.stdout}\n{r.stderr}"


def test_S5_the_v1_terminal_engine_does_not_ship():
    present = [n for n in V1_ENGINE if (ROOT / n).exists()]
    assert present == [], f"v1 modules still at the package root: {present} (history: origin/main 0a33840)"
    for d in ("color", "v19", "python", "packages", "gates", "design", "tui"):
        assert not (ROOT / d).exists(), f"{d}/ is v1/v22 residue in the shipped package"


def test_S6_the_repo_says_what_it_is():
    readme = (ROOT / "README.md").read_text()
    assert "2.0" in readme and "Desktop" in readme
    for word in ("resting", "working", "needs you", "error", "finished"):
        assert word in readme.lower(), f"README teaches the language: {word}"
    assert re.search(r"plugins\.entries\.cuttlefish-theme\.settings", readme), "README shows where config lives"
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert re.search(r"^## \[?2\.0\.0", changelog, re.M)
    assert (ROOT / "LICENSE").is_file()
