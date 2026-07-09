"""Place node results at their attach frame and stitch them into one flat
object list. Placement is a rigid transform applied to a copy of each shape;
the part geometry itself is never re-kerneled here."""

from __future__ import annotations

from dataclasses import replace

from solidifai import ShownObject


def place_features(features: list, *, at, path_prefix: str) -> list:
    """Namespace + place a child's declared features onto the parent frame,
    mirroring place() for objects: move each feature's faces by the attach frame
    ``at`` (so its geometry lands in composed coordinates) and prefix its name
    with the child id. ``part`` accumulates the owning child path so a nested
    feature reads "hinge/pin/<name>". The faces move via Shape.moved() (COMPOSE),
    exactly like a part's own placement, so nesting composes to arbitrary depth."""
    placed: list = []
    for f in features:
        name = f"{path_prefix}/{f.name}" if path_prefix else f.name
        moved_faces = [face.moved(at) for face in (getattr(f, "faces", []) or [])]
        owner = getattr(f, "part", None)
        part = f"{path_prefix}/{owner}" if owner else path_prefix
        placed.append(
            replace(
                f,
                name=name,
                faces=moved_faces,
                part=part,
                _tess_cache=None,  # geometry moved: drop any stale per-build tess cache
            )
        )
    return placed


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
