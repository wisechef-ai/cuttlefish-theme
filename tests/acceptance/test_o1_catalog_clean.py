"""ACCEPTANCE CONTRACT — O1: catalog-clean (locked).

`hermes plugins validate <fresh clone> --install-deps` is CLEAN on Hermes v0.22.7: rc 0, no ✗, no ⚠ (no private core
imports, no security caution), and the desktop-surface lint actually ran on our desktop half (floor: a validate that
never saw the desktop half proves nothing). Plus our own rule-9 AST guard and the rule-8 static guard on the bundle.
"""
from __future__ import annotations

import ast
import re
import subprocess

import yaml

from .helpers import ROOT, FakeCtx, plugin_package, run_hermes, shipping_files

UNMERGED_CORE_HOOKS = ("register_chrome_renderer", "input_rule_art", "pet_state", "chrome_renderer")
CORE_PACKAGES = {"hermes_cli", "agent", "tools", "gateway", "tui_gateway", "run_agent", "hermes_state", "cli",
                 "model_tools", "toolsets", "prompt_toolkit", "rich"}
# Public, documented doors (SDK doc "Pushing events to your desktop half"; "can import hermes_cli.config").
ALLOWED_CORE_IMPORTS = {"hermes_cli.plugin_events", "hermes_cli.config"}


def _fresh_clone(tmp_path):
    dst = tmp_path / "cuttlefish-theme"
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(dst)], check=True)
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", str(dst), "checkout", "-q", head], check=True)
    return dst


def test_O1_1_validate_is_clean_on_a_fresh_clone(tmp_path):
    clone = _fresh_clone(tmp_path)
    home = tmp_path / "hermes-home"
    home.mkdir()
    r = run_hermes(["plugins", "validate", str(clone), "--install-deps"], home)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "Validation passed" in out, out
    bad = [ln for ln in out.splitlines() if ln.lstrip().startswith(("✗", "⚠", "✘"))]
    assert bad == [], "validate must be CLEAN (no failures, no warnings):\n" + "\n".join(bad)
    assert re.search(r"✓ desktop surface", out), "the desktop-surface lint must have run on desktop/plugin.js:\n" + out
    assert re.search(r"✓ no core override", out), out
    scan = re.search(r"security scan — (\w+)", out)
    assert scan and scan.group(1) == "safe", f"security scan verdict: {scan.group(1) if scan else None}\n{out}"


def test_O1_2_manifest_is_v2_and_declares_what_registers():
    m = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    assert m["name"] == "cuttlefish-theme"
    assert str(m["version"]) == "2.0.0"
    assert re.fullmatch(r">=0\.22\.\d+", str(m.get("requires_hermes", ""))), m.get("requires_hermes")
    for key in ("intensity", "motion", "states", "patterns"):
        assert key in (m.get("config_schema") or {}), f"config_schema.{key} missing"
    ctx = FakeCtx()
    plugin_package().register(ctx)
    declared = set(m.get("provides_hooks") or [])
    assert declared == set(ctx.hooks), f"declared {sorted(declared)} vs registered {sorted(ctx.hooks)}"
    needed = {"pre_approval_request", "post_approval_response", "on_human_input_request", "on_human_input_resolved",
              "api_request_error"}
    assert needed <= declared, f"missing hooks: {sorted(needed - declared)}"
    assert "cuttlefish" in ctx.cli, "hermes cuttlefish <doctor|skin> is registered"
    assert not m.get("python_dependencies"), "no Python dependencies: nothing for --install-deps to fetch"


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name, node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found += [(f"{node.module}.{a.name}", node.lineno) for a in node.names] + [(node.module, node.lineno)]
    return found


def _public(name: str) -> bool:
    parents = {a.rsplit(".", 1)[0] for a in ALLOWED_CORE_IMPORTS}
    return name in parents or any(name == a or name.startswith(a + ".") for a in ALLOWED_CORE_IMPORTS)


def _core_import_problems(tree: ast.AST, rel: str) -> list[str]:
    return [f"{rel}:{line} imports {name} (only {sorted(ALLOWED_CORE_IMPORTS)} are public doors)"
            for name, line in _imports(tree) if name.split(".")[0] in CORE_PACKAGES and not _public(name)]


def _core_bound_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if (getattr(node, "module", None) or a.name).split(".")[0] in CORE_PACKAGES:
                    names.add(a.asname or a.name.split(".")[0])
    return names


FORBIDDEN_CALLS = {"setattr", "delattr", "sys.modules.__setitem__", "sys.modules.update", "sys.meta_path.insert",
                   "sys.meta_path.append", "importlib.reload"}


def _rebind_problems(tree: ast.AST, rel: str) -> list[str]:
    core_names = _core_bound_names(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in FORBIDDEN_CALLS:
            out.append(f"{rel}:{node.lineno} calls {ast.unparse(node.func)}()")
        targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target] \
            if isinstance(node, ast.AugAssign) else []
        for t in targets:
            src = ast.unparse(t)
            if src.startswith(("sys.modules", "builtins.", "sys.meta_path")):
                out.append(f"{rel}:{node.lineno} writes {src}")
            elif isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in core_names:
                out.append(f"{rel}:{node.lineno} rebinds core attribute {src}")
    return out


def test_O1_3_rule9_ast_guard_no_core_override_and_only_public_core_imports():
    problems = []
    for path in shipping_files((".py",)):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(), filename=rel)
        problems += _core_import_problems(tree, rel) + _rebind_problems(tree, rel)
    assert problems == [], "\n".join(problems)


def test_O1_4_no_dependence_on_unmerged_core_hooks():
    hits = []
    for path in shipping_files((".py", ".js", ".mjs", ".yaml", ".json")):
        text = path.read_text(errors="replace")
        for word in UNMERGED_CORE_HOOKS:
            if word in text:
                hits.append(f"{path.relative_to(ROOT)}: {word}")
    assert hits == [], "\n".join(hits)


RULE8 = {
    "eval(": r"(?<![\w.$])eval\s*\(",
    "new Function": r"new\s+Function\s*\(",
    "dynamic import()": r"(?<![\w.$])import\s*\(",
    "<script": r"<script",
    "document.query*": r"document\.(querySelector|querySelectorAll|getElementBy|getElementsBy)",
    "MutationObserver": r"MutationObserver",
    "requestAnimationFrame": r"requestAnimationFrame",
    "bare setTimeout/setInterval": r"(?<![\w.$])(setTimeout|setInterval)\s*\(",
    "window.addEventListener": r"window\.addEventListener",
    "localStorage": r"localStorage",
    "window.hermesDesktop": r"hermesDesktop",
    "innerHTML": r"innerHTML",
    "core markup in CSS": r"data-(slot|testid|sidebar|tour)\b",
    "setColor": r"sessions\.setColor",
}


def test_O1_5_rule8_static_guard_on_the_shipped_bundle():
    js = ROOT / "desktop" / "plugin.js"
    assert js.is_file(), "desktop/plugin.js (the shipped, generated bundle) is missing"
    src = js.read_text()
    specs = set(re.findall(r"""(?:^|\n)\s*import\s+(?:[^'";]+?\s+from\s+)?['"]([^'"]+)['"]""", src))
    assert specs <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}, f"imports: {sorted(specs)}"
    assert "@hermes/plugin-sdk" in specs
    hits = [name for name, rx in RULE8.items() if re.search(rx, src)]
    assert hits == [], f"rule-8 tripwires in desktop/plugin.js: {hits}"
    assert src.startswith("// GENERATED"), "the bundle says it is generated (edit desktop/src, run the build)"
