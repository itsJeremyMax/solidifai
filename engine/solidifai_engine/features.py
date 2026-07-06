"""Interpret the raw build123d faces a ``feature()`` block captured.

Pure functions over a feature's ``faces`` (build123d ``Face`` objects): a JSON
summary (center/bbox/metrics), a tessellation for highlight rendering, and a
nearest-feature point hit-test for ``feature_at``. Imports build123d (engine
side only — never the MCP bridge).
"""

from __future__ import annotations

import contextlib
import math

from build123d import Compound

from solidifai import FeatureRecord

TESS_TOLERANCE = 0.1
FEATURE_AT_TOLERANCE = 1.0  # mm — a point within this of a feature's mesh "hits" it
INFERENCE_CONFIDENCE = 0.5  # flat heuristic for auto-detected features (low-trust, flagged)


def _classify_cylinder(face) -> tuple:
    """Return (kind, confidence) for a cylindrical face.

    A hole's surface normal points toward the face's OWN cylinder axis; a
    boss's points away (classifying against the solid's center misreads
    off-center holes, e.g. bolt holes near a plate edge). Sample an on-surface
    point, drop a perpendicular to the axis, and dot the normal with the unit
    surface->axis vector: dot > 0 => hole (concave), dot < 0 => boss (convex).
    |dot| sets confidence in [0.4, 0.9]; an ambiguous/failed sample =>
    ("cylindrical", 0.4).
    """
    try:
        axis = face.axis_of_rotation
        if axis is None:
            return ("cylindrical", 0.4)
        p = face.position_at(0.5, 0.5)
        n = face.normal_at(0.5, 0.5)
        t = (p - axis.position).dot(axis.direction)
        v = axis.position + axis.direction * t - p  # surface point -> axis
        mag = v.length
        if mag == 0:
            return ("cylindrical", 0.4)
        dot = n.dot(v) / mag
        kind = "hole" if dot > 0 else "boss"
        confidence = round(min(0.9, 0.4 + abs(dot) * 0.5), 3)
        return (kind, confidence)
    except Exception:  # noqa: BLE001 - classification is best-effort
        return ("cylindrical", 0.4)


def _compound(faces: list):
    return Compound(children=list(faces))


def summarize(faces: list) -> dict:
    """Return ``{center, bbox, metrics}`` for the captured faces.

    ``center`` is the bbox midpoint, ``bbox`` the size (W,D,H) — both in
    build123d Z-up mm. ``metrics`` is best-effort: face count + geom types.
    All ``None`` when there are no faces.
    """
    if not faces:
        return {"center": None, "bbox": None, "metrics": None}
    bb = _compound(faces).bounding_box()
    center = [
        round((bb.min.X + bb.max.X) / 2, 4),
        round((bb.min.Y + bb.max.Y) / 2, 4),
        round((bb.min.Z + bb.max.Z) / 2, 4),
    ]
    size = [round(bb.size.X, 4), round(bb.size.Y, 4), round(bb.size.Z, 4)]
    geom_types = sorted({str(f.geom_type) for f in faces})
    return {
        "center": center,
        "bbox": size,
        "metrics": {"faces": len(faces), "geom_types": geom_types},
    }


def tessellate(faces: list, tol: float = TESS_TOLERANCE):
    """Tessellate the faces -> ``(vertices, triangles)`` (lists of 3-tuples)."""
    if not faces:
        return [], []
    verts, tris = _compound(faces).tessellate(tol)
    return [tuple(v) for v in verts], [tuple(t) for t in tris]


def infer(compound) -> list:
    """Best-effort detection of feature-like geometry in an UNTAGGED model.

    Returns inferred ``FeatureRecord``s (``inferred=True``, ``confidence`` set,
    ``driven_by=[]``, ``source_line=None``) — one per cylindrical face (holes,
    bores, round features). Coarse by design and explicitly low-trust; the
    caller invokes this only when there are no declared ``feature()`` tags
    (declared always wins). Never raises — returns ``[]`` on any problem.
    """
    records: list = []
    try:
        faces = list(compound.faces())
    except Exception:  # noqa: BLE001 - inference is best-effort, never fatal
        return []
    kind_counts: dict = {}
    for f in faces:
        try:
            is_cyl = "CYLINDER" in str(f.geom_type)
        except Exception:  # noqa: BLE001
            continue
        if is_cyl:
            kind, confidence = _classify_cylinder(f)
            prefix = "cyl" if kind == "cylindrical" else kind
            kind_counts[prefix] = kind_counts.get(prefix, 0) + 1
            records.append(
                FeatureRecord(
                    name=f"{prefix}_{kind_counts[prefix]}",
                    kind=kind,
                    driven_by=[],
                    source_line=None,
                    faces=[f],
                    inferred=True,
                    confidence=confidence,
                )
            )
    return records


def _cached_tess(rec):
    """Tessellate a record's faces once, memoized on the record (per-build)."""
    cache = getattr(rec, "_tess_cache", None)
    if cache is None:
        cache = tessellate(getattr(rec, "faces", []) or [])
        # Record may be slotted/immutable; caching is best-effort.
        with contextlib.suppress(Exception):
            rec._tess_cache = cache
    return cache


def _point_tri_dist(p, a, b, c) -> float:
    """Euclidean distance from point ``p`` to triangle ``(a, b, c)``.

    Closest-point-on-triangle via barycentric region classification (Ericson,
    *Real-Time Collision Detection*): project ``p`` onto the triangle plane and
    clamp to the triangle's voronoi regions (3 vertices, 3 edges, interior).
    All args are plain 3-tuples. Returns ``inf`` for a degenerate triangle.
    """
    ax, ay, az = a
    bx, by, bz = b
    cx, cy, cz = c
    px, py, pz = p
    abx, aby, abz = bx - ax, by - ay, bz - az
    acx, acy, acz = cx - ax, cy - ay, cz - az
    apx, apy, apz = px - ax, py - ay, pz - az
    d1 = abx * apx + aby * apy + abz * apz
    d2 = acx * apx + acy * apy + acz * apz
    if d1 <= 0.0 and d2 <= 0.0:  # vertex region A
        return math.dist(p, a)
    bpx, bpy, bpz = px - bx, py - by, pz - bz
    d3 = abx * bpx + aby * bpy + abz * bpz
    d4 = acx * bpx + acy * bpy + acz * bpz
    if d3 >= 0.0 and d4 <= d3:  # vertex region B
        return math.dist(p, b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:  # edge region AB
        denom = d1 - d3
        if denom == 0.0:
            return float("inf")
        v = d1 / denom
        return math.dist(p, (ax + v * abx, ay + v * aby, az + v * abz))
    cpx, cpy, cpz = px - cx, py - cy, pz - cz
    d5 = abx * cpx + aby * cpy + abz * cpz
    d6 = acx * cpx + acy * cpy + acz * cpz
    if d6 >= 0.0 and d5 <= d6:  # vertex region C
        return math.dist(p, c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:  # edge region AC
        denom = d2 - d6
        if denom == 0.0:
            return float("inf")
        w = d2 / denom
        return math.dist(p, (ax + w * acx, ay + w * acy, az + w * acz))
    va = d3 * d6 - d5 * d4
    if va <= 0.0 and (d4 - d3) >= 0.0 and (d5 - d6) >= 0.0:  # edge region BC
        denom = (d4 - d3) + (d5 - d6)
        if denom == 0.0:
            return float("inf")
        w = (d4 - d3) / denom
        qx = bx + w * (cx - bx)
        qy = by + w * (cy - by)
        qz = bz + w * (cz - bz)
        return math.dist(p, (qx, qy, qz))
    # interior region — barycentric coordinates
    denom = va + vb + vc
    if denom == 0.0:
        return float("inf")
    inv = 1.0 / denom
    v = vb * inv
    w = vc * inv
    qx = ax + abx * v + acx * w
    qy = ay + aby * v + acy * w
    qz = az + abz * v + acz * w
    return math.dist(p, (qx, qy, qz))


def nearest(features_list: list, point, tol: float = FEATURE_AT_TOLERANCE):
    """Return the feature whose tessellated SURFACE is closest to ``point``
    (build123d Z-up mm), or ``None`` if none is within ``tol``.

    Uses point-to-triangle distance over each feature's tessellated triangles
    (not nearest vertex) so a click on a smooth/flat face — which tessellates
    with sparse interior vertices — still resolves the feature.
    """
    p = (float(point[0]), float(point[1]), float(point[2]))
    best = None
    best_d = float("inf")
    for rec in features_list:
        verts, tris = _cached_tess(rec)
        if not verts or not tris:
            continue
        n = len(verts)
        for tri in tris:
            i, j, k = tri[0], tri[1], tri[2]
            if i >= n or j >= n or k >= n:  # guard against bad indices
                continue
            d = _point_tri_dist(p, verts[i], verts[j], verts[k])
            if d < best_d:
                best_d = d
                best = rec
    return best if best is not None and best_d <= tol else None
