"""cuttlefish-theme v22 — the Python (agent) half.

Hermes imports this directory as the plugin module and calls ``register(ctx)``. The v19 root modules
(plugin.py, mantle.py, field.py, chrome.py, ...) stay on disk until P7 tombstones them; this entry no
longer imports them.
"""

__version__ = "0.22.0"


def register(ctx):
    from .python.plugin_entry import detect_valid_hooks, register_cli, register_hooks

    register_hooks(ctx, detect_valid_hooks())
    register_cli(ctx)


__all__ = ["register"]
