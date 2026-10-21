"""Registers the Python half with core, feature-detecting hooks (G0 contract 6)."""
import logging

from . import bus, hooks, paths

log = logging.getLogger("cuttlefish")
_runtime = None


def detect_valid_hooks():
    """The running core's VALID_HOOKS, or None when it cannot be read (then register optimistically)."""
    try:
        from hermes_cli.plugins import VALID_HOOKS
        return set(VALID_HOOKS)
    except Exception:
        return None


def default_runtime():
    global _runtime
    if _runtime is None:
        _runtime = hooks.Runtime()
    return _runtime


def register_hooks(ctx, valid_hooks=None, runtime=None):
    rt = runtime or default_runtime()
    cbs = rt.callbacks()
    registered, unavailable = [], []
    for name in hooks.SUBSCRIBED:
        if valid_hooks is not None and name not in valid_hooks:
            unavailable.append(name)
            log.warning("cuttlefish-theme: hook %s is not in this core's VALID_HOOKS; skipped", name)
            continue
        ctx.register_hook(name, cbs[name])
        registered.append(name)
    status = {"schema": "cf2909.hooks/1", "registered": sorted(registered), "unavailable": sorted(unavailable)}
    try:  # for `hermes cuttlefish doctor`; written by the Python half only
        if bus.read_json(paths.hooks_file(rt.home)) != status:
            bus.atomic_write_json(paths.hooks_file(rt.home), status)
    except Exception as e:  # noqa: BLE001
        log.warning("cuttlefish-theme: could not record hook status: %r", e)
    return status


def register_cli(ctx):
    """``hermes cuttlefish ...``. Guarded on its own: an older core without register_cli_command loses only this."""
    try:
        from . import cli
        cli.register(ctx)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("cuttlefish-theme: CLI command not registered: %r", e)
        return False
