"""The one door out: ``broadcast_plugin_event`` (contract/README.md "Python half").

Core forms the wire name itself — ``plugin.<plugin_id>.<event>`` — so we speak
the short event name and our plugin id. The default broadcaster is the public
core door ``hermes_cli.plugin_events.broadcast_plugin_event``, imported LAZILY:
a process without Hermes on the path (the test venv, ``plugins validate``) has
nobody to deliver to and the send is a silent no-op, never an ImportError.
"""

from __future__ import annotations

from typing import Any, Callable

#: Every event we emit is prefixed with this on the wire (formed by core).
EVENT_PREFIX = "plugin.cuttlefish-theme."

#: Our id on the wire; the catalog name, same as plugin.yaml's ``name``.
PLUGIN_ID = "cuttlefish-theme"

#: ``(plugin_id, event, payload=None) -> None``; the test seam replaces it.
Broadcaster = Callable[[str, str, "dict[str, Any] | None"], None]

_override: Broadcaster | None = None

#: Told whenever the broadcaster is (re)attached. Observer-owned state (the
#: pairing windows) registers here, so every observer starts from a clean
#: slate; production attaches once (or never) and never resets.
_change_listeners: list[Any] = []


def on_broadcaster_change(listener: Any) -> None:
    """Register a zero-arg callback run on every broadcaster (re)attach."""
    _change_listeners.append(listener)


def set_broadcaster(fn: Broadcaster | None) -> None:
    """Test seam: swap the door (``None`` restores the public core default).
    A re-attach also starts a fresh slate for observer-owned state."""
    global _override
    _override = fn
    for listener in tuple(_change_listeners):
        try:
            listener()
        except Exception:
            pass


def _core_door(plugin_id: str, event: str, payload: dict[str, Any] | None = None) -> None:
    from hermes_cli.plugin_events import broadcast_plugin_event  # the one public door, lazily
    broadcast_plugin_event(plugin_id, event, payload)


def emit(event: str, payload: dict[str, Any] | None = None) -> None:
    """Send one event. Never raises: an observer must not break its host."""
    try:
        broadcaster = _override if _override is not None else _core_door
        broadcaster(PLUGIN_ID, event, payload)
    except Exception:
        pass  # a dead gateway, a broken seam, a poisoned payload: all not our host's problem
