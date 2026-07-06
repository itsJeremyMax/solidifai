"""Render-agnostic drawing primitives.

A ``Drawing`` is a sheet (mm) plus a flat list of primitives in page-mm
coordinates (origin top-left, +y down, matching SVG/PDF). The projection,
layout and dimensioning build a ``Drawing``; the SVG/PDF backends render it.
Keeping one geometry model behind both formats means the layout logic lives in
exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    dashed: bool = False
    width: float = 0.18  # mm stroke
    color: str | None = None  # hex; None = default ink


@dataclass
class Text:
    x: float
    y: float
    s: str
    size: float = 2.5  # mm cap height
    anchor: str = "start"  # start | middle | end
    bold: bool = False
    mono: bool = False  # monospace (technical values)
    color: str | None = None  # hex; None = default ink


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    width: float = 0.18
    color: str | None = None  # stroke hex; None = default ink
    fill: str | None = None  # fill hex; None = no fill


@dataclass
class Drawing:
    width: float  # sheet width (mm)
    height: float  # sheet height (mm)
    items: list = field(default_factory=list)

    def add(self, item):
        self.items.append(item)
        return item

    def extend(self, items) -> None:
        self.items.extend(items)

    def lines(self) -> list:
        return [it for it in self.items if isinstance(it, Line)]

    def texts(self) -> list:
        return [it for it in self.items if isinstance(it, Text)]
