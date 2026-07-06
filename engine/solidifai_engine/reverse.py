"""Reverse engineering: measure an imported or shown shape into a structured
report (overall dimensions + detected cylindrical features) that the agent
rebuilds a clean parametric model from. Read-only; never mutates geometry."""

from __future__ import annotations

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane

from solidifai_engine import features as feat


def _surface_type(face):
    try:
        return BRepAdaptor_Surface(face.wrapped).GetType()
    except Exception:  # noqa: BLE001 - non-analytic faces are simply not classified
        return None


def _cyl_info(face) -> dict | None:
    """Radius / axis location / axis direction of a cylindrical face, or None."""
    try:
        s = BRepAdaptor_Surface(face.wrapped)
        if s.GetType() != GeomAbs_Cylinder:
            return None
        cyl = s.Cylinder()
        ax = cyl.Axis()
        loc, d = ax.Location(), ax.Direction()
        return {
            "radius": round(cyl.Radius(), 4),
            "location": [round(loc.X(), 3), round(loc.Y(), 3), round(loc.Z(), 3)],
            "axis": [round(d.X(), 4), round(d.Y(), 4), round(d.Z(), 4)],
        }
    except Exception:  # noqa: BLE001
        return None


def _dedupe(items: list, tol: float = 0.5) -> list:
    """OCC often splits one bore into two faces; collapse cylinders that share a
    radius and axis location within ``tol``."""
    out: list = []
    for it in items:
        dup = any(
            abs(it["diameter"] - o["diameter"]) < tol
            and all(abs(it["location"][i] - o["location"][i]) < tol for i in range(3))
            for o in out
        )
        if not dup:
            out.append(it)
    return out


def _primitive_guess(size: list, planar: int, cylindrical: int) -> str:
    smallest, largest = min(size), max(size)
    thin = smallest > 0 and smallest < largest / 4
    if cylindrical == 0 and planar <= 6:
        return "plate" if thin else "box"
    if cylindrical >= planar and planar <= 3:
        return "cylinder"
    return "compound"


def analyze_shape(shape) -> dict:
    """Measure a shape: bbox, volume, center of mass, face mix, a coarse primitive
    guess, and the detected cylindrical features (holes / bosses) with diameter,
    axis, and location."""
    try:
        faces = list(shape.faces())
    except Exception:  # noqa: BLE001
        faces = []
    planar = sum(1 for f in faces if _surface_type(f) == GeomAbs_Plane)
    cylindrical = sum(1 for f in faces if _surface_type(f) == GeomAbs_Cylinder)

    feats: list = []
    for f in faces:
        info = _cyl_info(f)
        if info is None:
            continue
        kind, conf = feat._classify_cylinder(f)
        feats.append(
            {
                "kind": kind,
                "diameter": round(info["radius"] * 2, 4),
                "location": info["location"],
                "axis": info["axis"],
                "confidence": conf,
            }
        )
    feats = _dedupe(feats)

    bb = shape.bounding_box()
    size = [round(bb.size.X, 4), round(bb.size.Y, 4), round(bb.size.Z, 4)]
    com = shape.center()
    return {
        "bbox": {
            "size": size,
            "min": [round(bb.min.X, 4), round(bb.min.Y, 4), round(bb.min.Z, 4)],
            "max": [round(bb.max.X, 4), round(bb.max.Y, 4), round(bb.max.Z, 4)],
        },
        "volume": round(float(shape.volume), 4),
        "centerOfMass": [round(com.X, 4), round(com.Y, 4), round(com.Z, 4)],
        "faceCount": len(faces),
        "planarFaces": planar,
        "cylindricalFaces": cylindrical,
        "primitiveGuess": _primitive_guess(size, planar, cylindrical),
        "features": feats,
    }
