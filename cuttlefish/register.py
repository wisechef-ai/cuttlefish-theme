"""What ``register(ctx)`` wires — the manifest declares EXACTLY this (O1.2).

Five observer hooks (never raise, never block, no text payloads) and one CLI
command. Nothing else: no tools, no slash commands, no core overrides.
"""

from __future__ import annotations

from typing import Any

from . import cli, hooks

#: The hooks we register, in the manifest's ``provides_hooks`` order.
HOOKS = ("pre_approval_request", "post_approval_response", "on_human_input_request",
         "on_human_input_resolved", "api_request_error")


def register(ctx: Any) -> None:
    """Wire the plugin into Hermes (the entrypoint the loader looks for)."""
    for name in HOOKS:
        ctx.register_hook(name, getattr(hooks, name))
    ctx.register_cli_command("cuttlefish", help="cuttlefish-theme: doctor, skin, legend",
                             setup_fn=cli.setup_parser, handler_fn=cli.run)
