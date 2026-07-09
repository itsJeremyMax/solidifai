"""Standard hardware + reference dims for model scripts: ``from solidifai import std``.

A thin facade over ``solidifai_engine.standards`` (the data SSOT). Functions
return plain numbers/dicts in mm; geometry builders (screw solids, hole cutters)
live in ``solidifai.hardware``. ``clearance_hole``/``pilot_hole`` resolve the
workspace manufacturing profile's fit setting automatically::

    from solidifai import show, std
    dia = std.clearance_hole("M3")           # 3.4 under the default normal fit
    boss_hole = std.insert("M3")["hole_dia"]  # 4.0 heat-set install hole

The engine import is lazy so ``import solidifai`` stays light and cycle-free.
"""

from __future__ import annotations

from .imports import workspace_root

__all__ = [
    "sizes",
    "screw",
    "nut",
    "washer",
    "insert",
    "bearing",
    "clearance_hole",
    "pilot_hole",
    "thread_pitch",
    "lookup",
    "lookup_reference",
]


def _standards():
    from solidifai_engine import standards

    return standards


def sizes() -> list[str]:
    return _standards().sizes()


def screw(size: str, head: str = "cap") -> dict:
    return _standards().screw(size, head=head)


def nut(size: str) -> dict:
    return _standards().nut(size)


def washer(size: str) -> dict:
    return _standards().washer(size)


def insert(size: str) -> dict:
    return _standards().insert(size)


def bearing(code: str) -> dict:
    return _standards().bearing(code)


def clearance_hole(size: str, fit: str | None = None) -> float:
    return _standards().clearance_hole(size, fit, workspace_root=workspace_root())


def pilot_hole(size: str) -> float:
    return _standards().pilot_hole(size)


def thread_pitch(size: str) -> float:
    return _standards().thread_pitch(size)


def lookup(query: str) -> dict:
    return _standards().lookup_standard(query, workspace_root=workspace_root())


def lookup_reference(object_name: str) -> dict:
    return _standards().lookup_reference(object_name)
