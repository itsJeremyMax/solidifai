"""Place node results at their attach frame and stitch them into one flat
object list. Placement is a rigid transform applied to a copy of each shape;
the part geometry itself is never re-kerneled here."""

from __future__ import annotations

from dataclasses import replace

from solidifai import ShownObject


def place(objects: list[ShownObject], *, at, path_prefix: str) -> list[ShownObject]:
    """Apply the attach frame to each object and prefix its path id. Uses
    Shape.moved() (COMPOSE) rather than .located() (REPLACE), so a child's own
    internal placement survives being placed inside its parent -- correct frame
    composition through arbitrary nesting depth. (Verified: located() would wipe
    a sub-part's internal offset; moved() composes it.)"""
    placed: list[ShownObject] = []
    for o in objects:
        name = f"{path_prefix}/{o.name}" if path_prefix else o.name
        placed.append(replace(o, name=name, shape=o.shape.moved(at)))
    return placed


def path_ids(objects: list[ShownObject]) -> list[str]:
    """Stable ids for composed objects, identical to render._node_ids (one id
    scheme everywhere). Slugs each '/'-separated segment and dedupes."""
    from solidifai_engine.render import _node_ids

    return _node_ids(objects)
