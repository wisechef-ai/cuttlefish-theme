"""The three surfaces and the artifact each one ships (D2). One table feeds ``setup``, ``uninstall`` and ``doctor``."""
from collections import namedtuple
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent

# artifact: file in the package that proves the surface is shipped; link_src: what gets symlinked;
# dest: <HOME>/<dest_dir>/<dest_name>
Surface = namedtuple("Surface", "id label artifact link_src dest_dir dest_name")

SURFACES = (
    Surface("tui", "TUI strip", "tui/cuttlefish.mjs", "tui/cuttlefish.mjs", "tui-widgets", "cuttlefish.mjs"),
    # the desktop half is a directory (desktop/plugin.js + assets); core materializes the same dir from
    # `hermes plugins install` as desktop-plugins/<pkg>/ with a marker, in which case we leave it alone
    Surface("desktop", "desktop field pane", "desktop/plugin.js", "desktop", "desktop-plugins", "cuttlefish"),
    Surface("classic-cli", "classic-CLI strip", "cli/cuttlefish_widget.py", "cli/cuttlefish_widget.py",
            "cli-widgets", "cuttlefish_widget.py"),
)


def by_id(sid):
    return next(s for s in SURFACES if s.id == sid)


def shipped(surface, root=PKG_ROOT):
    return (Path(root) / surface.artifact).is_file()


def dest(home, surface):
    return Path(home) / surface.dest_dir / surface.dest_name


def materialized_by_core(home):
    """A desktop half copied by core's reconcile: desktop-plugins/<name>/.hermes-package.json."""
    for n in ("cuttlefish-theme", "cuttlefish_theme", "cuttlefish"):
        d = Path(home) / "desktop-plugins" / n
        if (d / ".hermes-package.json").is_file():
            return d
    return None
