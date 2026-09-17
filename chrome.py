"""The Hermes chrome-renderer seam.

One responsibility: hand Hermes' four chrome surfaces to whichever engine owns
them, failing closed — an exception here would disable the renderer for the
whole session, so a broken theme must never become a broken terminal: any
failure declines the surface instead.

The v17 mantle-palette coherence family (dominant hues, mantle classes,
readable darkening) now lives in `mantle_palette.py`; this module no longer
owns colour logic.
"""
from __future__ import annotations

from typing import Any

from .v19_adapter import render as _render_v19

# Re-exported: tests pin the v17 mantle ground through this module's historical
# import path.
from .mantle_palette import _MANTLE_GROUND  # noqa: F401

__all__ = ["chrome_renderer"]


def chrome_renderer(surface: str, width: int, ctx: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Render persistent chrome, failing closed on any repaint-path problem.

    Delegates to the v19 engine through `v19_adapter`. An exception here would
    disable the renderer for the whole session, so a broken theme must never
    become a broken terminal: any failure declines the surface instead.
    """
    try:
        return _render_v19(surface, width, ctx)
    except Exception:
        return None
