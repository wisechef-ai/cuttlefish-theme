"""STRUCTURAL CONTRACT — cuttlefish v19. LOCKED.

Authored by Tori AFTER the v19 engine passed all 42 behavioural outcomes while
violating the stated quality bar. THE IMPLEMENTER MUST NOT EDIT THIS FILE.

WHY THIS FILE EXISTS
--------------------
Adam asked for code that "follows the patterns from books clean_code and
clean_architecture". The behavioural contract could not see any of that, so a
green suite hid four real defects:

  A. DEAD CODE. `field.sample()` ended with `_contract(out, 1.0 if False else
     0.0, fine)` — a branch that can never be taken, so the function could
     never contract. Clean Code: dead code is deleted, never commented out or
     disguised behind a constant condition.

  B. DUPLICATED LOGIC. `sample()` and `sample_contracted()` each carried their
     own copy of the entire field computation — same noise, same three layers.
     They had ALREADY DRIFTED: `sample()` used a constant leucophore lightness
     (.25) while `sample_contracted()` varied it (.20 + broad*.13). Two
     definitions of one concept is how a codebase starts lying to you.

  C. AN ORPHANED MODULE. `noise.py` implements value/fractal noise and is
     imported by `field.py` — and never called. The field used raw `math.sin`
     instead. Clean Architecture: a module nothing depends on is either deleted
     or wired; leaving it is a false promise to the next reader.

  D. A SECOND ORPHANED MODULE. `contraction.py` owns the finite-support mask
     and is likewise imported but never called from `field.py`.

None of these change a single rendered pixel today. All of them mislead the
next person to open the file, which is precisely the cost Clean Code is about.

WHAT THIS FILE ENFORCES
-----------------------
Structure, not behaviour. It reads the shipped source with `ast` and asserts
the properties a human reviewer would check: no dead branches, no duplicated
field computation, every module actually wired, the dependency rule respected,
no magic numbers in the public surface, and functions small enough to hold in
your head.

RUN:  cd ~/.hermes/plugins/cuttlefish-theme && make test
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

V19 = Path(__file__).resolve().parent.parent / "v19"

pytestmark = pytest.mark.skipif(not V19.is_dir(), reason="v19 port not yet implemented")

MODULES = ("oklab", "palette", "noise", "contraction", "field", "renderer")


def _tree(module: str) -> ast.Module:
    return ast.parse((V19 / f"{module}.py").read_text(encoding="utf-8"))


def _functions(module: str) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(_tree(module)) if isinstance(n, ast.FunctionDef)]


def _imported_names(module: str) -> set[str]:
    """Sibling v19 modules this module imports."""
    names: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            names.update(a.name for a in node.names)
    return names


def _called_attributes(module: str) -> set[str]:
    """Module names used as `x.something(...)` anywhere in the file."""
    used: set[str] = set()
    for node in ast.walk(_tree(module)):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used.add(node.value.id)
    return used


# ===========================================================================
# CLEAN CODE — no dead code, no duplication, no magic numbers on the surface
# ===========================================================================

class TestNoDeadCode:
    @pytest.mark.parametrize("module", MODULES)
    def test_no_constant_condition_branches(self, module):
        """`1.0 if False else 0.0` is a branch that can never be taken."""
        for node in ast.walk(_tree(module)):
            if isinstance(node, (ast.IfExp, ast.If)):
                test = node.test
                if isinstance(test, ast.Constant) and isinstance(test.value, bool):
                    pytest.fail(f"{module}.py line {node.lineno}: constant-condition branch")

    @pytest.mark.parametrize("module", MODULES)
    def test_every_sibling_import_is_actually_used(self, module):
        """An imported-but-never-called module is a false promise."""
        unused = _imported_names(module) - _called_attributes(module)
        assert not unused, f"{module}.py imports but never calls: {sorted(unused)}"

    def test_the_noise_module_is_wired_into_the_field(self):
        """noise.py exists to give the field organic structure. If the field
        computes its own sin() terms instead, the module is decoration."""
        assert "noise" in _called_attributes("field"), "field.py never calls noise.*"

    def test_the_contraction_module_is_wired_into_the_field(self):
        """contraction.py owns the finite-support mask — the fix for a defect
        that silently contracted the whole surface. It must be the one used."""
        assert "contraction" in _called_attributes("field"), "field.py never calls contraction.*"


class TestNoDuplication:
    def test_the_field_is_computed_in_exactly_one_place(self):
        """`sample` and `sample_contracted` must not each carry their own copy
        of the layer stack: two definitions of one concept drift apart."""
        bodies: dict[str, str] = {}
        for fn in _functions("field"):
            layer_calls = sum(
                1 for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_layer"
            )
            if layer_calls >= 3:
                bodies[fn.name] = ast.dump(fn)
        assert len(bodies) <= 1, (
            f"the three-layer stack is built in {len(bodies)} functions "
            f"({sorted(bodies)}); extract it into one"
        )

    def test_no_two_public_functions_share_an_identical_body(self):
        for module in MODULES:
            seen: dict[str, str] = {}
            for fn in _functions(module):
                if fn.name.startswith("_"):
                    continue
                body = ast.dump(ast.Module(body=fn.body, type_ignores=[]))
                assert body not in seen, f"{module}.{fn.name} duplicates {seen[body]}"
                seen[body] = fn.name


class TestSmallFocusedFunctions:
    @pytest.mark.parametrize("module", MODULES)
    def test_functions_stay_readable(self, module):
        """Clean Code's first rule of functions: they should be small."""
        for fn in _functions(module):
            span = (fn.end_lineno or fn.lineno) - fn.lineno
            assert span <= 30, f"{module}.{fn.name} is {span} lines; extract a helper"

    @pytest.mark.parametrize("module", MODULES)
    def test_parameter_lists_stay_manageable(self, module):
        for fn in _functions(module):
            count = len(fn.args.args) + len(fn.args.kwonlyargs)
            assert count <= 8, f"{module}.{fn.name} takes {count} parameters"


class TestIntentionRevealingNames:
    @pytest.mark.parametrize("module", MODULES)
    def test_public_functions_are_documented(self, module):
        """A public function without a docstring makes the reader guess."""
        for fn in _functions(module):
            if fn.name.startswith("_"):
                continue
            assert ast.get_docstring(fn), f"{module}.{fn.name} has no docstring"

    @pytest.mark.parametrize("module", MODULES)
    def test_modules_declare_their_purpose(self, module):
        assert ast.get_docstring(_tree(module)), f"{module}.py has no module docstring"

    @pytest.mark.parametrize("module", MODULES)
    def test_public_functions_carry_type_hints(self, module):
        for fn in _functions(module):
            if fn.name.startswith("_"):
                continue
            assert fn.returns is not None, f"{module}.{fn.name} has no return annotation"
            for arg in fn.args.args:
                assert arg.annotation is not None, f"{module}.{fn.name}({arg.arg}) unannotated"


# ===========================================================================
# CLEAN ARCHITECTURE — the dependency rule
# ===========================================================================

class TestDependencyRule:
    """Inner layers know nothing about outer ones.

        oklab, noise        pure leaves — depend on nothing in v19
        palette             depends on nothing in v19
        contraction         pure geometry — depends on nothing in v19
        field               may use oklab, noise, palette, contraction
        renderer            may use field, oklab

    An arrow pointing the other way (field importing renderer) would make the
    engine impossible to reason about or reuse.
    """

    ALLOWED = {
        "oklab": set(),
        "noise": set(),
        "palette": set(),
        "contraction": set(),
        "field": {"oklab", "noise", "palette", "contraction"},
        "renderer": {"field", "oklab", "palette"},
    }

    @pytest.mark.parametrize("module", MODULES)
    def test_module_only_depends_on_inner_layers(self, module):
        illegal = _imported_names(module) - self.ALLOWED[module]
        assert not illegal, f"{module}.py depends outward on {sorted(illegal)}"

    def test_no_import_cycles(self):
        graph = {m: _imported_names(m) & set(MODULES) for m in MODULES}
        for start in MODULES:
            seen, stack = set(), [start]
            while stack:
                node = stack.pop()
                for nxt in graph.get(node, ()):
                    assert nxt != start, f"import cycle through {start} -> {node} -> {nxt}"
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)

    def test_the_leaves_import_nothing_from_v19(self):
        for leaf in ("oklab", "noise", "palette", "contraction"):
            assert not _imported_names(leaf), f"{leaf}.py should be a pure leaf"


class TestNamedConstants:
    """Tuning values are named at module level with a comment saying WHY.

    A bare 0.36 buried in an expression tells the next reader nothing, and it
    is the reason a previous version's calm target and its measurement used two
    different colour metrics without anybody noticing.
    """

    def test_the_contraction_radius_is_named(self):
        assert any(
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "RADIUS" for t in n.targets)
            for n in _tree("contraction").body
        ), "contraction.RADIUS must be a named module constant"

    def test_the_state_names_are_declared_once(self):
        assert any(
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "STATES" for t in n.targets)
            for n in _tree("renderer").body
        ), "renderer.STATES must be a named module constant"

    @pytest.mark.parametrize("module", ("field", "renderer"))
    def test_tuning_constants_are_hoisted(self, module):
        """At least a handful of module-level named constants must exist: a
        field module with zero of them has its tuning scattered inline."""
        named = [
            t.id
            for n in _tree(module).body
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Name) and t.id.isupper()
        ]
        assert len(named) >= 3, f"{module}.py hoists only {named}; name its tuning values"
