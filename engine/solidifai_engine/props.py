"""Geometric properties of a build123d shape, plus the mass formula.

All floats are rounded to 4 decimal places so the JSON artifact is stable and
readable. Per-object mass (volume x material density) is assembled in render.py
using ``mass_grams`` and the resolved material density.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from build123d import CenterOf
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps


def _round4(values) -> list[float]:
    return [round(float(v), 4) for v in values]


def _resolve_bool(value) -> bool:
    """build123d exposes is_valid/is_manifold as bool properties, but older
    versions used methods. Accept either form."""
    if callable(value):
        value = value()
    return bool(value)


def mass_grams(volume_mm3: float, density: float) -> float:
    """grams = mm^3 * (g/cm^3) / 1000  (since 1 cm^3 = 1000 mm^3)."""
    return round(volume_mm3 * density / 1000.0, 4)


def properties(shape: Any) -> dict:
    """Return compound-level geometry of ``shape``.

    Keys: ``bbox`` (size/min/max), ``volume``, ``centerOfMass``, ``valid``,
    ``manifold``. Mass is intentionally NOT included — it is per-object.
    """
    bb = shape.bounding_box()
    com = shape.center(CenterOf.MASS)
    return {
        "bbox": {
            "size": _round4((bb.size.X, bb.size.Y, bb.size.Z)),
            "min": _round4((bb.min.X, bb.min.Y, bb.min.Z)),
            "max": _round4((bb.max.X, bb.max.Y, bb.max.Z)),
        },
        "volume": round(float(shape.volume), 4),
        "centerOfMass": _round4((com.X, com.Y, com.Z)),
        "valid": _resolve_bool(shape.is_valid),
        "manifold": _resolve_bool(shape.is_manifold),
    }


def build_volume_com(shapes) -> tuple[float, list[float]]:
    """Build-level volume and center of mass aggregated per solid.

    A Compound's own volume/CoM come from OCC's SIGNED volume integration, which
    cancels mirrored (negative-determinant) solids to a wrong total and a garbage
    center. Each solid's own ``.volume`` is unsigned and correct, so sum those and
    take the volume-weighted mean of the per-solid centers of mass instead.
    """
    total = 0.0
    weighted = np.zeros(3)
    for s in shapes:
        v = float(s.volume)
        c = s.center(CenterOf.MASS)
        total += v
        weighted += v * np.array([c.X, c.Y, c.Z], float)
    if total <= 0:
        return round(total, 4), [0.0, 0.0, 0.0]
    return round(total, 4), _round4((weighted / total).tolist())


def _gprops(shape):
    """Volume + surface GProp_GProps for a build123d shape (about the origin)."""
    vol = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, vol)
    surf = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape.wrapped, surf)
    return vol, surf


def _matrix_of_inertia(vprops) -> np.ndarray:
    # OCC GProp returns the geometric matrix of inertia (unit density) already
    # about the center of mass, in model X/Y/Z.
    m = vprops.MatrixOfInertia()
    return np.array([[m.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)], float)


def _eigh(tensor: np.ndarray) -> tuple[list, list]:
    """Principal moments (ascending) + orthonormal principal axes (as rows)."""
    moments, axes = np.linalg.eigh((tensor + tensor.T) / 2.0)
    return moments.tolist(), axes.T.tolist()


def mass_properties(shape: Any, density: float) -> dict:
    """Exact mass properties of a build123d shape at ``density`` (g/cm^3).

    The inertia tensor is about the center of mass in model X/Y/Z (units g*mm^2);
    principal moments/axes are its eigen-decomposition. Exact (straight from the
    B-rep via OCC GProp), not sampled.
    """
    vprops, sprops = _gprops(shape)
    volume = float(vprops.Mass())  # unit density -> Mass == volume (mm^3)
    scale = density / 1000.0  # g per mm^3
    mass = volume * scale
    c = vprops.CentreOfMass()
    com = np.array([c.X(), c.Y(), c.Z()], float)

    tensor = _matrix_of_inertia(vprops) * scale  # g*mm^2, about the CoM
    moments, axes = _eigh(tensor)

    bb = shape.bounding_box()
    return {
        "volume": round(volume, 4),
        "surfaceArea": round(float(sprops.Mass()), 4),
        "mass": round(mass, 4),
        "density": round(float(density), 4),
        "centerOfMass": _round4((com[0], com[1], com[2])),
        "bbox": {
            "size": _round4((bb.size.X, bb.size.Y, bb.size.Z)),
            "min": _round4((bb.min.X, bb.min.Y, bb.min.Z)),
            "max": _round4((bb.max.X, bb.max.Y, bb.max.Z)),
        },
        "inertia": {
            "frame": "centerOfMass",
            "tensor": [_round4(row) for row in tensor.tolist()],
            "principalMoments": _round4(moments),
            "principalAxes": [_round4(axis) for axis in axes],
        },
        "valid": _resolve_bool(shape.is_valid),
        "manifold": _resolve_bool(shape.is_manifold),
    }


def aggregate(per_part: list[dict]) -> dict:
    """Combine per-part ``mass_properties`` into an assembly total: summed
    mass/volume, mass-weighted CoM, and each part's inertia translated to the
    assembly CoM (parallel-axis) and summed."""
    solids = [p for p in per_part if p.get("mass", 0)]
    total_vol = sum(p["volume"] for p in per_part)
    total_mass = sum(p["mass"] for p in solids)
    if total_mass <= 0:
        return {
            "mass": 0.0,
            "volume": round(total_vol, 4),
            "centerOfMass": [0.0, 0.0, 0.0],
            "inertia": None,
        }

    coms = np.array([p["centerOfMass"] for p in solids], float)
    masses = np.array([p["mass"] for p in solids], float)
    com = (coms.T @ masses) / total_mass

    tensor = np.zeros((3, 3))
    for p, c in zip(solids, coms, strict=True):
        r = c - com
        tensor += np.array(p["inertia"]["tensor"], float)
        tensor += p["mass"] * (float(r @ r) * np.eye(3) - np.outer(r, r))
    moments, axes = _eigh(tensor)
    return {
        "mass": round(total_mass, 4),
        "volume": round(total_vol, 4),
        "centerOfMass": _round4(com.tolist()),
        "inertia": {
            "frame": "centerOfMass",
            "tensor": [_round4(row) for row in tensor.tolist()],
            "principalMoments": _round4(moments),
            "principalAxes": [_round4(axis) for axis in axes],
        },
    }
