"""Pure-OCC auto-orient: choose the rotation that minimises support burden.

Scoring (per candidate orientation):
  - support burden = total area of elevated downward-facing faces whose surface
    angle from horizontal is less than ``overhang_deg`` (they would need
    support in FDM). Uses the same face-normal idiom as ``dfm.py``.
  - bed contact = area of downward faces resting on the build plate
    (the face's max-Z equals model min-Z within a small tolerance).

The best orientation minimises support area, with bed contact as the
tie-breaker (more is better — more stable on the bed).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from build123d import Rot

if TYPE_CHECKING:
    pass

# Tolerance (mm): a face whose max-Z is within this of the model's min-Z
# is considered to be resting on the build plate.
_PLATE_TOL_MM = 0.05

# Default candidate orientations as [rx, ry, rz] Euler angles (degrees).
# The 6 axis-aligned "face down" positions cover every flat-face orientation;
# the 4 diagonals catch parts that do better at 45 deg tilts.
_DEFAULT_CANDIDATES: list[list[float]] = [
    [0.0, 0.0, 0.0],  # natural / identity
    [90.0, 0.0, 0.0],  # front face down
    [180.0, 0.0, 0.0],  # top face down
    [270.0, 0.0, 0.0],  # back face down
    [0.0, 90.0, 0.0],  # right face down
    [0.0, 270.0, 0.0],  # left face down
    [45.0, 0.0, 0.0],  # diagonal about X
    [0.0, 45.0, 0.0],  # diagonal about Y
    [45.0, 45.0, 0.0],  # compound diagonal
    [315.0, 0.0, 0.0],  # -45 about X
]


def _face_normal_z(face) -> float | None:
    """Z-component of the outward unit normal at the face centre, or None.

    Reuses the same idiom as dfm._face_normal — call normal_at the center,
    skip degenerate faces that raise.
    """
    try:
        c = face.center()
        n = face.normal_at(c)
        return float(n.Z)
    except Exception:  # noqa: BLE001 - degenerate face; skip it
        return None


def _score(shape, overhang_deg: float) -> tuple[float, float]:
    """Return (support_area, contact_area) for a shape in its current orientation."""
    try:
        min_z = float(shape.bounding_box().min.Z)
    except Exception:  # noqa: BLE001
        return 0.0, 0.0

    support = 0.0
    contact = 0.0

    try:
        faces = list(shape.faces())
    except Exception:  # noqa: BLE001
        return 0.0, 0.0

    for f in faces:
        nz = _face_normal_z(f)
        if nz is None or nz >= 0.0:
            # Upward or horizontal-up faces cannot be overhangs.
            continue

        try:
            face_max_z = float(f.bounding_box().max.Z)
            area = float(f.area)
        except Exception:  # noqa: BLE001
            continue

        if face_max_z <= min_z + _PLATE_TOL_MM:
            # Face sits on the build plate — contributes to bed contact.
            contact += area
        else:
            # Elevated downward face: check overhang angle.
            # phi = surface angle from horizontal = acos(|nz|), matching dfm.py.
            phi = math.degrees(math.acos(max(-1.0, min(1.0, abs(nz)))))
            if phi < overhang_deg:
                support += area

    return support, contact


def _rotate(shape, rx: float, ry: float, rz: float):
    """Return the shape rotated by (rx, ry, rz) degrees; identity is a no-op."""
    if rx == 0.0 and ry == 0.0 and rz == 0.0:
        return shape
    return Rot(rx, ry, rz) * shape


def best_orientation(
    shape,
    overhang_deg: float = 45.0,
    candidates: list[list[float]] | None = None,
) -> dict:
    """Find the rotation that minimises support material for ``shape``.

    Parameters
    ----------
    shape:
        A build123d ``Shape`` (Box, Solid, CompoundSolid, etc.) in its default
        coordinate frame. Accepts the same types as ``dfm.analyze_part``.
    overhang_deg:
        Overhang threshold in degrees from horizontal. Downward faces whose
        surface angle from horizontal is less than this need support.
    candidates:
        List of ``[rx, ry, rz]`` Euler-angle rotations to try. Defaults to the
        6 axis-aligned face-down orientations plus 4 diagonal positions.

    Returns
    -------
    dict with keys:
        rotation       — [rx, ry, rz] of the best candidate
        supportArea    — support-needing face area (mm²) in that orientation
        contactArea    — bed-contact face area (mm²) in that orientation
        worstSupportArea — maximum support area across all candidates (context
                           for the caller to show the improvement)
    """
    if candidates is None:
        candidates = _DEFAULT_CANDIDATES

    best_rot: list[float] = [0.0, 0.0, 0.0]
    best_support = float("inf")
    best_contact = 0.0
    worst_support = 0.0

    for cand in candidates:
        rx, ry, rz = float(cand[0]), float(cand[1]), float(cand[2])
        try:
            rotated = _rotate(shape, rx, ry, rz)
            sup, con = _score(rotated, overhang_deg)
        except Exception:  # noqa: BLE001 - skip a candidate that errors
            continue

        if sup > worst_support:
            worst_support = sup

        # Prefer lower support; break ties by larger bed contact.
        if sup < best_support or (sup == best_support and con > best_contact):
            best_support = sup
            best_contact = con
            best_rot = [rx, ry, rz]

    return {
        "rotation": best_rot,
        "supportArea": best_support if best_support != float("inf") else 0.0,
        "contactArea": best_contact,
        "worstSupportArea": worst_support,
    }
