"""Plane-cut sectioning for capture_views.

Boolean-cuts shapes against a half-space box and extracts the planar faces the
cut created (the "caps"), so the renderer can fill the exposed cross-section in
a distinct color. Imports build123d but NEVER vtkmodules (views.py is the only
VTK module, and it never imports build123d -- keep that boundary).

Non-destructive by construction: an OCC boolean returns NEW geometry, so the
inputs (the session's live shapes) are never mutated.
"""

from __future__ import annotations

from build123d import Box, Pos

AXES = {"x": 0, "y": 1, "z": 2}
_CAP_NORMAL_DOT = 0.999  # |face normal . axis| above this counts as plane-parallel
_CAP_PLANE_TOL = 1e-3  # mm distance from the cut plane to count as a cap
_PAD = 1.0  # mm of cutting-box overhang so the boolean never grazes a face


def cut_with_caps(shapes: list, axis: str, offset_mm: float) -> tuple[list, list]:
    """Cut every shape with the half-space ``<axis> > offset_mm`` removed.

    Returns ``(cut_shapes, cap_faces)``: ``cut_shapes`` aligns 1:1 with the
    input (a shape fully on the kept side comes back geometrically unchanged;
    a shape fully on the removed side comes back empty), ``cap_faces`` is the
    flat list of planar faces lying ON the cut plane across all results.
    Raises ValueError for an unknown axis or an offset outside the union
    bounds (a cut that would change nothing is a caller mistake worth naming).

    Known false positive: a pre-existing planar face that happens to lie
    exactly on the cut plane is indistinguishable from a boolean-created cap
    and gets cap-colored too. Rendering artifact only; geometry is unaffected.
    """
    if axis not in AXES:
        valid = ", ".join(sorted(AXES))
        raise ValueError(f"unknown section axis {axis!r}; expected one of: {valid}")
    i = AXES[axis]
    offset = float(offset_mm)

    bbs = [s.bounding_box() for s in shapes]
    mins = [min(b.min.X for b in bbs), min(b.min.Y for b in bbs), min(b.min.Z for b in bbs)]
    maxs = [max(b.max.X for b in bbs), max(b.max.Y for b in bbs), max(b.max.Z for b in bbs)]
    lo, hi = mins[i], maxs[i]
    if not (lo + 1e-6 < offset < hi - 1e-6):
        raise ValueError(
            f"section offset {offset:g} mm misses the model: {axis} spans {lo:.1f}..{hi:.1f} mm"
        )

    # One padded box covering everything on the removed (+axis) side.
    size = [maxs[k] - mins[k] + 2 * _PAD for k in range(3)]
    center = [(mins[k] + maxs[k]) / 2 for k in range(3)]
    size[i] = (hi - offset) + 2 * _PAD
    center[i] = offset + size[i] / 2
    tool = Pos(*center) * Box(*size)

    cut_shapes: list = []
    cap_faces: list = []
    for s in shapes:
        cut = s - tool  # NEW shape; `s` is untouched
        cut_shapes.append(cut)
        for f in cut.faces():
            if "PLANE" not in str(f.geom_type):
                continue
            n = f.normal_at()
            if abs((n.X, n.Y, n.Z)[i]) < _CAP_NORMAL_DOT:
                continue
            c = f.center()
            if abs((c.X, c.Y, c.Z)[i] - offset) <= _CAP_PLANE_TOL:
                cap_faces.append(f)
    return cut_shapes, cap_faces
