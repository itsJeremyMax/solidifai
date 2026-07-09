"""Geometry features for technical drawings: hole extraction + part grouping.

Pure geometry over build123d/OCP shapes -- no drawing/model imports, so it stays
independently testable. Holes are located (a point on the axis + axis direction +
diameter) for the hole chart; signatures are pose-invariant so identical parts
group regardless of placement.
"""

from __future__ import annotations

import re

import numpy as np

from solidifai_engine import dfm as _dfm

# Below this normalized third-moment magnitude a part is treated as having a
# mirror plane (achiral), so its reflection is a rotation and must still group.
# Set well above tessellation noise (~1e-4) and below a genuinely handed part's
# weakest skew (~1e-2), so rounding never flips a part's handedness build-to-build.
_HANDEDNESS_TOL = 3e-3


def extract_holes(shape) -> list[dict]:
    """Each hole as ``{"center": (x,y,z), "axis": (x,y,z), "dia": float}``.

    ``center`` is a point ON the cylinder axis (the circle center when viewed down
    the axis); ``axis`` is the unit cylinder direction. Deduped by rounded center +
    radius so a hole that is one periodic cylindrical face counts once. Best-effort:
    a face that fails extraction is skipped, never fatal."""
    out: list[dict] = []
    seen: set = set()
    try:
        faces = list(shape.faces())
    except Exception:  # noqa: BLE001
        return out
    for f in faces:
        try:
            if "CYLINDER" not in str(f.geom_type) or not _dfm._is_hole(f):
                continue
            r = _dfm._cylinder_radius(f)
            if not r:
                continue
            from OCP.BRepAdaptor import BRepAdaptor_Surface

            axis = BRepAdaptor_Surface(f.wrapped).Cylinder().Axis()
            ap, ad = axis.Location(), axis.Direction()
            center = (ap.X(), ap.Y(), ap.Z())
            adir = (ad.X(), ad.Y(), ad.Z())
            key = (round(center[0], 1), round(center[1], 1), round(center[2], 1), round(r, 2))
            if key in seen:
                continue
            seen.add(key)
            out.append({"center": center, "axis": adir, "dia": round(r * 2.0, 1)})
        except Exception:  # noqa: BLE001 - skip a bad face, never fail extraction
            continue
    return out


def _handedness(shape) -> int:
    """Chirality sign of ``shape``: -1 / +1 for the two enantiomers, 0 if achiral.

    Volume, area, counts and the inertia tensor are all reflection-invariant, so a
    handed part and its mirror are otherwise indistinguishable -- they must be told
    apart by an odd-order moment. We build a pose-canonical principal frame (axes
    ordered by principal moment, each oriented so its area-weighted third moment is
    positive) and take the sign of that frame's determinant: a proper rotation
    preserves it, a reflection flips it. A mirror plane forces a near-zero principal
    skew, so ``|skew| < tol`` (or a degenerate inertia spectrum) reads as achiral
    and both enantiomers land on 0. Best-effort: any failure returns 0."""
    try:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape.wrapped, props)
        c = props.CentreOfMass()
        com = np.array([c.X(), c.Y(), c.Z()])
        m = props.MatrixOfInertia()
        tensor = np.array([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)])
        moments, axes = np.linalg.eigh((tensor + tensor.T) / 2.0)  # ascending
        axes = axes.T  # rows are the unit principal axes

        # Near-degenerate moments -> the axes in the equal-eigenvalue plane are
        # arbitrary (a rotational symmetry); handedness is undefined, treat as achiral.
        span = (moments[2] - moments[0]) or 1.0
        if (moments[1] - moments[0]) / span < 1e-3 or (moments[2] - moments[1]) / span < 1e-3:
            return 0

        verts, tris = shape.tessellate(0.05)
        v = np.array([tuple(p) for p in verts])
        f = np.array(tris)
        a, b, d = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        centroids = (a + b + d) / 3.0
        area = 0.5 * np.linalg.norm(np.cross(b - a, d - a), axis=1)
        total = area.sum()
        if total <= 0:
            return 0

        q = (centroids - com) @ axes.T  # face centroids in the principal frame
        rg = np.sqrt((area * (q**2).sum(axis=1)).sum() / total)  # radius of gyration
        skew = np.array([(area * q[:, k] ** 3).sum() / total / rg**3 for k in range(3)])
        if np.abs(skew).min() < _HANDEDNESS_TOL:
            return 0  # a principal-plane mirror symmetry -> achiral

        for k in range(3):
            if skew[k] < 0:  # orient each axis to its skew, canonicalizing the frame
                axes[k] *= -1
        return 1 if np.linalg.det(axes) > 0 else -1
    except Exception:  # noqa: BLE001 - handedness is best-effort; never fail grouping
        return 0


def part_signature(shape) -> tuple:
    """Pose-invariant key for grouping identical parts: rounded volume, surface
    area, face count, edge count, and a chirality sign so a handed part and its
    mirror don't merge. Translation/rotation invariant. Best-effort: falls back to
    a coarse key if a metric is unavailable."""
    try:
        vol = round(float(shape.volume), 2)
    except Exception:  # noqa: BLE001
        vol = 0.0
    try:
        area = round(float(shape.area), 1)
    except Exception:  # noqa: BLE001
        area = 0.0
    try:
        nf = len(list(shape.faces()))
        ne = len(list(shape.edges()))
    except Exception:  # noqa: BLE001
        nf = ne = 0
    return (vol, area, nf, ne, _handedness(shape))


def _base_name(name: str) -> str:
    """Strip a trailing instance index: 'Foot 1' -> 'Foot', 'Bay_03' -> 'Bay'.

    Requires an explicit separator before the number so spec tokens glued to
    letters survive ('M3' and 'Panel v2' stay as-is)."""
    return re.sub(r"[ _-]+\d+$", "", (name or "part")).strip() or (name or "part")


def group_parts(objects) -> list[dict]:
    """Group objects by pose-invariant signature, preserving first-seen order.

    Returns one dict per unique shape:
    ``{"name", "qty", "rep", "members", "signature"}`` where ``rep`` is the first
    member (its shape is what gets projected) and ``name`` is the common base name.
    """
    order: list[tuple] = []
    groups: dict[tuple, dict] = {}
    for o in objects:
        sig = part_signature(o.shape)
        g = groups.get(sig)
        if g is None:
            g = {"name": _base_name(o.name), "qty": 0, "rep": o, "members": [], "signature": sig}
            groups[sig] = g
            order.append(sig)
        g["qty"] += 1
        g["members"].append(o)
    return [groups[s] for s in order]
