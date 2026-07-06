"""Geometry features for technical drawings: hole extraction + part grouping.

Pure geometry over build123d/OCP shapes -- no drawing/model imports, so it stays
independently testable. Holes are located (a point on the axis + axis direction +
diameter) for the hole chart; signatures are pose-invariant so identical parts
group regardless of placement.
"""

from __future__ import annotations

import re

from solidifai_engine import dfm as _dfm


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


def part_signature(shape) -> tuple:
    """Pose-invariant key for grouping identical parts: rounded volume, surface
    area, face count, edge count. Translation/rotation invariant. Best-effort:
    falls back to a coarse key if a metric is unavailable."""
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
    return (vol, area, nf, ne)


def _base_name(name: str) -> str:
    """Strip a trailing instance index: 'Foot 1' -> 'Foot', 'Bay_03' -> 'Bay'."""
    return re.sub(r"[ _-]*\d+$", "", (name or "part")).strip() or (name or "part")


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
