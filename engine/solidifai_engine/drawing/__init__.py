"""Technical-drawing generation: HLR projection -> sheet layout -> SVG/PDF.

``Session.create_drawing`` gathers the spec data and calls into here. The
geometry/layout lives in ``project`` + ``sheet``; the output formats in
``backends``. Submodules are imported lazily so importing one (e.g. ``project``)
never drags in the others.
"""

from __future__ import annotations

from solidifai_engine.drawing.model import Drawing, Line, Rect, Text

__all__ = ["Drawing", "Line", "Rect", "Text", "compose"]


def compose(compound, spec: dict, opts: dict | None = None) -> tuple:
    """Build a ``Drawing`` for ``compound`` with the gathered ``spec`` data.
    Returns ``(drawing, meta)`` where meta carries the chosen ``scale``."""
    from solidifai_engine.drawing import sheet

    return sheet.compose(compound, spec, opts or {})
