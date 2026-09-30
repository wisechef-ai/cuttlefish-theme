"""cf-spike agent half: intentionally inert. The P0 spikes only need the package
shape (plugin.yaml + desktop/ + dashboard/); hooks are measured in P0-TUI."""


def register(ctx):  # noqa: D401 - plugin entry point
    return None
