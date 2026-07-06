"""Advisory interference + connectivity geometry over shown objects.

Pure build123d helpers behind ``Session.check_interferences``. Every result is
a heuristic report, never a build gate. Kept separate from the session so the
geometry is unit-testable without an engine or socket.
"""

from __future__ import annotations

# Boolean-intersection volume (mm^3) at or below this counts as non-
# interpenetrating contact, not a real overlap -- guards against OCC fuzz.
TOLERANCE_MM3 = 1e-3
# Bounding boxes within this (mm) on every axis count as touching/adjacent.
BBOX_EPS = 1e-6


def _round4(values) -> list[float]:
    return [round(float(v), 4) for v in values]


def _bbox_tuple(shape) -> tuple[tuple, tuple]:
    bb = shape.bounding_box()
    return ((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))


def _bbox_report(shape) -> dict:
    mn, mx = _bbox_tuple(shape)
    return {
        "min": _round4(mn),
        "max": _round4(mx),
        "size": _round4((mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])),
    }


def bboxes_overlap(a: tuple, b: tuple, eps: float = BBOX_EPS) -> bool:
    """True when axis-aligned bounding boxes overlap or touch within ``eps``."""
    (amin, amax), (bmin, bmax) = a, b
    return all(amin[i] <= bmax[i] + eps and bmin[i] <= amax[i] + eps for i in range(3))


def _intersection(s1, s2):
    """Boolean intersection shape of two solids, or None when clearly disjoint.
    Bbox-prefiltered so the expensive boolean is skipped for separated boxes,
    and any intersection at/below ``TOLERANCE_MM3`` is treated as no overlap."""
    if not bboxes_overlap(_bbox_tuple(s1), _bbox_tuple(s2)):
        return None
    try:
        inter = s1 & s2
    except Exception:  # noqa: BLE001 - a failed boolean reports as 'no overlap'
        return None
    if inter is None:
        return None
    try:
        if float(inter.volume) <= TOLERANCE_MM3:
            return None
    except Exception:  # noqa: BLE001
        return None
    return inter


def _bbox_gap(a: tuple, b: tuple) -> float:
    """Minimum separation (mm) between two axis-aligned bounding boxes.
    Zero for touching/overlapping boxes; positive for clear/separated pairs.
    Uses per-axis gaps: gap_i = max(0, min_b_i - max_a_i, min_a_i - max_b_i)
    and takes the max across axes (the minimum over-all gap is the L-inf distance)."""
    (amin, amax), (bmin, bmax) = a, b
    gaps = [max(0.0, bmin[i] - amax[i], amin[i] - bmax[i]) for i in range(3)]
    return max(gaps)


def min_clearance_mm(shapes: list) -> float | None:
    """Minimum clearance (mm) between any non-overlapping pair of shapes.
    Returns None when fewer than two shapes are given. Uses bbox separation as
    a fast conservative lower-bound (actual clearance >= bbox clearance)."""
    if len(shapes) < 2:
        return None
    boxes = [_bbox_tuple(s) for s in shapes]
    best: float | None = None
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            inter = _intersection(shapes[i], shapes[j])
            if inter is not None:
                continue  # overlapping pair -- not a clearance
            gap = _bbox_gap(boxes[i], boxes[j])
            if best is None or gap < best:
                best = gap
    return best


def classify_pair(shape_a, shape_b) -> dict:
    """Classify two shapes: ``overlap`` (interpenetrating, with volume + bbox),
    ``adjacent`` (bboxes meet but solids do not interpenetrate), or ``clear``."""
    if not bboxes_overlap(_bbox_tuple(shape_a), _bbox_tuple(shape_b)):
        return {"relation": "clear"}
    inter = _intersection(shape_a, shape_b)
    if inter is None:
        return {"relation": "adjacent"}
    return {
        "relation": "overlap",
        "overlapVolume": round(float(inter.volume), 4),
        "overlapBbox": _bbox_report(inter),
    }


def _solid_com(solid) -> list[float]:
    from build123d import CenterOf

    c = solid.center(CenterOf.MASS)
    return _round4((c.X, c.Y, c.Z))


def _connected_components(solids: list) -> list[list[int]]:
    """Group solid indices into connected components, where two solids are
    'connected' when their bounding boxes overlap/touch. Heuristic: an exact
    shared-topology proof is not attempted (documented as advisory)."""
    boxes = [_bbox_tuple(s) for s in solids]
    n = len(solids)
    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if bboxes_overlap(boxes[i], boxes[j]):
                adj[i].add(j)
                adj[j].add(i)
    seen: set[int] = set()
    comps: list[list[int]] = []
    for i in range(n):
        if i in seen:
            continue
        stack, comp = [i], []
        while stack:
            k = stack.pop()
            if k in seen:
                continue
            seen.add(k)
            comp.append(k)
            stack.extend(adj[k] - seen)
        comps.append(sorted(comp))
    return comps


def classify_internal(shape) -> dict:
    """Classify the solids WITHIN one shown shape: ``single`` (one solid),
    ``overlap`` (>=2 solids interpenetrate), ``disjoint`` (>=2 connected
    components -> floating lumps), or ``touching`` (multiple solids, one
    connected body, no interpenetration)."""
    solids = list(shape.solids())
    n = len(solids)
    if n <= 1:
        return {"solids": n, "internal": "single", "components": [], "internalOverlaps": []}

    internal_overlaps = []
    for i in range(n):
        for j in range(i + 1, n):
            inter = _intersection(solids[i], solids[j])
            if inter is not None:
                internal_overlaps.append(
                    {"solids": [i, j], "overlapVolume": round(float(inter.volume), 4)}
                )

    comps = _connected_components(solids)
    if internal_overlaps:
        internal = "overlap"
    elif len(comps) > 1:
        internal = "disjoint"
    else:
        internal = "touching"

    components = []
    if internal == "disjoint":
        for comp in comps:
            members = [solids[k] for k in comp]
            boxes = [_bbox_tuple(m) for m in members]
            mn = [min(b[0][a] for b in boxes) for a in range(3)]
            mx = [max(b[1][a] for b in boxes) for a in range(3)]
            components.append(
                {
                    "solids": comp,
                    "bbox": {
                        "min": _round4(mn),
                        "max": _round4(mx),
                        "size": _round4((mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])),
                    },
                    # first member's center of mass localizes the lump
                    "centerOfMass": _solid_com(members[0]),
                }
            )

    return {
        "solids": n,
        "internal": internal,
        "components": components,
        "internalOverlaps": internal_overlaps,
    }
