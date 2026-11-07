"""Unit: cuttlefish.register — exactly what the manifest declares."""

from __future__ import annotations

import yaml


class FakeCtx:
    def __init__(self):
        self.hooks = {}
        self.cli = {}

    def register_hook(self, name, callback, **_kw):
        self.hooks.setdefault(name, []).append(callback)

    def register_cli_command(self, name, help, setup_fn, handler_fn, **_kw):
        self.cli[name] = (help, setup_fn, handler_fn)


def test_register_wires_five_hooks_and_one_cli_command():
    from cuttlefish_theme.cuttlefish import hooks, register

    ctx = FakeCtx()
    register.register(ctx)
    manifest = yaml.safe_load(open("plugin.yaml").read())
    assert set(ctx.hooks) == set(manifest["provides_hooks"])
    for name, (cb,) in ctx.hooks.items():
        assert cb == getattr(hooks, name), name
    assert set(ctx.cli) == {"cuttlefish"}


def test_the_manifest_declares_only_what_exists():
    from cuttlefish_theme.cuttlefish import hooks

    manifest = yaml.safe_load(open("plugin.yaml").read())
    for name in manifest["provides_hooks"]:
        assert callable(getattr(hooks, name)), name
    assert not manifest.get("python_dependencies")
