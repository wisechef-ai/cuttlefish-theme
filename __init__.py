"""cuttlefish-theme 2.0 — the Python half of the desktop-first plugin.

Hermes loads this directory AS the package (plugins_loader slugifies the
manifest name to ``cuttlefish_theme``). The v2 entrypoint is ``register(ctx)``
re-exported from ``cuttlefish.register``: five observer hooks that turn
approval / human-input / api-error events into ``broadcast_plugin_event`` for
the desktop half (``desktop/``, the other half of this same plugin), plus the
settings validator, the live-config dashboard API and the classic-CLI skin.
"""

from .cuttlefish.register import register

__all__ = ["register"]
__version__ = "2.0.0"
