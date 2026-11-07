"""The v2 Python half of cuttlefish-theme.

Kept import-free on purpose: the dashboard's ``plugin_api.py`` is loaded by the
web server via ``spec_from_file_location`` with no package context, and it loads
THIS package the same way (by path). Submodules:

- ``events``    the one door out: ``broadcast_plugin_event`` (public core door, lazy)
- ``hooks``     approval / human-input / api-error observers → desktop events
- ``settings``  the settings validator (shared vectors, pinned by the contract)
- ``liveconfig`` where settings live (config.yaml) and how to re-read them
- ``skin``      the static classic-CLI skin (explicit install only)
- ``cli``       ``hermes cuttlefish <doctor|skin|legend>``
- ``register``  what ``register(ctx)`` wires (the manifest declares exactly this)
"""
