"""Place node results at their attach frame and stitch them into one flat
object list. Placement is a rigid transform applied to a copy of each shape;
the part geometry itself is never re-kerneled here."""

from __future__ import annotations

from dataclasses import replace

from solidifai import ShownObject

# Map an occurrence mirror name to a build123d plane. "zx" aliases the XZ plane
# (build123d has no Plane.ZX). Lazy import keeps this module importable without
# build123d for pure-data callers.
_MIRROR_TO_PLANE = {"xy": "XY", "yz": "YZ", "zx": "XZ"}


def _mirror_plane(mirror: str | None):
    if mirror is None:
        return None
    from build123d import Plane

    return getattr(Plane, _MIRROR_TO_PLANE[mirror])


def occurrence_prefixes(child_id: str, count: int) -> list[str]:
    """Path-id prefixes for a child's occurrences: the first keeps the bare child
    id (so single-occurrence assemblies are byte-unchanged), the rest are
    ``<id>@2``, ``<id>@3`` ... The ``@`` slugs to ``_`` in render._node_ids, so the
    composed node ids read ``wheel``, ``wheel_2`` ..."""
    return [child_id if i == 0 else f"{child_id}@{i + 1}" for i in range(max(1, count))]


def place_features(features: list, *, at, path_prefix: str, mirror: str | None = None) -> list:
    """Namespace + place a child's declared features onto the parent frame,
    mirroring place() for objects: mirror each feature's faces about the local
    plane (for a mirrored occurrence), move them by the attach frame ``at`` (so
    the geometry lands in composed coordinates), and prefix its name with the
    child id. ``part`` accumulates the owning child path so a nested feature reads
    "hinge/pin/<name>". Faces move via Shape.moved() (COMPOSE), exactly like a
    part's own placement, so nesting composes to arbitrary depth."""
    plane = _mirror_plane(mirror)
    placed: list = []
    for f in features:
        name = f"{path_prefix}/{f.name}" if path_prefix else f.name
        faces = getattr(f, "faces", []) or []
        moved_faces = [
            (face.mirror(plane) if plane is not None else face).moved(at) for face in faces
        ]
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


def place(
    objects: list[ShownObject], *, at, path_prefix: str, mirror: str | None = None
) -> list[ShownObject]:
    """Apply the attach frame to each object and prefix its path id. For a mirrored
    occurrence, reflect the shape about the named LOCAL plane first, then place it.
    Uses Shape.moved() (COMPOSE) rather than .located() (REPLACE), so a child's own
    internal placement survives being placed inside its parent -- correct frame
    composition through arbitrary nesting depth. (Verified: located() would wipe
    a sub-part's internal offset; moved() composes it.)"""
    plane = _mirror_plane(mirror)
    placed: list[ShownObject] = []
    for o in objects:
        name = f"{path_prefix}/{o.name}" if path_prefix else o.name
        shape = o.shape.mirror(plane) if plane is not None else o.shape
        placed.append(replace(o, name=name, shape=shape.moved(at)))
    return placed


def path_ids(objects: list[ShownObject]) -> list[str]:
    """Stable ids for composed objects, identical to render._node_ids (one id
    scheme everywhere). Slugs each '/'-separated segment and dedupes."""
    from solidifai_engine.render import _node_ids

    return _node_ids(objects)
