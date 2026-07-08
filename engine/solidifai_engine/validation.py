"""First-order validation: geometric stress-concentration hot-spots and 1-D
tolerance stack math. Advisory only; never mutates geometry.

The stress check flags *where* stress concentrates (sharp re-entrant corners,
abrupt section changes), not a solved stress field. The tolerance stack does
worst-case and statistical (RSS) math over an agent-supplied dimension chain,
resolving common ISO 286 fits.
"""

from __future__ import annotations

import math
from typing import Any

from build123d import Edge, Face, GeomType
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

# --- stress hot-spots: geometric concentration finder ------------------------
STRESS_DEFAULTS = {
    "min_fillet_mm": 1.0,  # suggested transition radius (the threshold shown)
    "sharp_min_deg": 25.0,  # re-entrant angle below this is too gentle to flag
    "warn_deg": 55.0,  # at/above this re-entrant angle -> warning, else advisory
    "min_edge_len_mm": 1.0,  # ignore tiny slivers
    "max_edges": 6000,  # responsiveness cap per solid
}


def _vec(p):
    return (p.X, p.Y, p.Z) if hasattr(p, "X") else (p[0], p[1], p[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _edge_face_map(solid):
    m = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(solid.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
    return m


def _is_concave(n1, t, c1, mid, n2) -> bool:
    """Re-entrant edge test: step from the edge into face1's interior; if that
    direction points to the OUTWARD side of face2, the material wraps around the
    edge (interior angle > 180) -- a concave, stress-concentrating corner."""
    m1 = _norm(_cross(n1, t))
    if _dot(m1, (c1[0] - mid[0], c1[1] - mid[1], c1[2] - mid[2])) < 0:
        m1 = (-m1[0], -m1[1], -m1[2])  # orient into face1's interior
    return _dot(m1, n2) > 1e-6


def stress_hotspots(shape, config: dict | None = None) -> list[dict]:
    """Flag sharp re-entrant corners between planar faces, where stress
    concentrates. Geometric heuristic (not a solved stress field). Only
    planar-planar edges are considered, so holes and existing fillets do not
    create noise -- a filleted corner has tangent (smooth) edges and is skipped.
    """
    cfg = {**STRESS_DEFAULTS, **(config or {})}
    out, seen = [], set()
    for solid in shape.solids():
        m = _edge_face_map(solid)
        for i in range(1, min(m.Extent(), cfg["max_edges"]) + 1):
            faces = m.FindFromIndex(i)
            if faces.Extent() != 2:
                continue
            edge = Edge(m.FindKey(i))
            if edge.length < cfg["min_edge_len_mm"]:
                continue
            f1, f2 = Face(faces.First()), Face(faces.Last())
            if f1.geom_type != GeomType.PLANE or f2.geom_type != GeomType.PLANE:
                continue
            try:
                mid = _vec(edge.position_at(0.5))
                t = _norm(_vec(edge.tangent_at(0.5)))
                n1 = _norm(_vec(f1.normal_at(edge.position_at(0.5))))
                n2 = _norm(_vec(f2.normal_at(edge.position_at(0.5))))
                c1 = _vec(f1.center())
            except Exception:
                continue
            if not _is_concave(n1, t, c1, mid, n2):
                continue
            alpha = math.degrees(math.acos(max(-1.0, min(1.0, _dot(n1, n2)))))
            if alpha < cfg["sharp_min_deg"]:
                continue  # too gentle to matter
            key = (round(mid[0], 1), round(mid[1], 1), round(mid[2], 1))
            if key in seen:
                continue
            seen.add(key)
            severity = "warning" if alpha >= cfg["warn_deg"] else "advisory"
            out.append(
                {
                    "rule": "sharp_internal_corner",
                    "severity": severity,
                    "message": "Sharp inside corner (no fillet) concentrates stress.",
                    "measured": {"value": 0.0, "unit": "mm"},
                    "threshold": {"value": cfg["min_fillet_mm"], "unit": "mm"},
                    "location": [round(mid[0], 4), round(mid[1], 4), round(mid[2], 4)],
                    "source": "stress-concentration heuristic",
                    "hint": f"Add a fillet of >= {cfg['min_fillet_mm']:.0f} mm to spread the load.",
                }
            )
    return out


# --- tolerance: ISO 286 fundamental deviations (micrometres) -----------------
# Indexed by nominal-size band (mm, upper-inclusive). Common fits only; anything
# outside the table errors rather than inventing a number.
_BANDS = [3, 6, 10, 18, 30, 50, 80, 120, 180, 250]

# Hole H fits: lower deviation 0, upper = IT grade (micrometres).
_HOLE = {
    "H7": [10, 12, 15, 18, 21, 25, 30, 35, 40, 46],
    "H8": [14, 18, 22, 27, 33, 39, 46, 54, 63, 72],
    "H9": [25, 30, 36, 43, 52, 62, 74, 87, 100, 115],
    "H11": [60, 75, 90, 110, 130, 160, 190, 220, 250, 290],
}
# Shaft fits as (upper, lower) micrometres.
_SHAFT = {
    "g6": [
        (-2, -8),
        (-4, -12),
        (-5, -14),
        (-6, -17),
        (-7, -20),
        (-9, -25),
        (-10, -29),
        (-12, -34),
        (-14, -39),
        (-15, -44),
    ],
    "h6": [
        (0, -6),
        (0, -8),
        (0, -9),
        (0, -11),
        (0, -13),
        (0, -16),
        (0, -19),
        (0, -22),
        (0, -25),
        (0, -29),
    ],
    "h7": [
        (0, -10),
        (0, -12),
        (0, -15),
        (0, -18),
        (0, -21),
        (0, -25),
        (0, -30),
        (0, -35),
        (0, -40),
        (0, -46),
    ],
    "f7": [
        (-6, -16),
        (-10, -22),
        (-13, -28),
        (-16, -34),
        (-20, -41),
        (-25, -50),
        (-30, -60),
        (-36, -71),
        (-43, -83),
        (-50, -96),
    ],
    "k6": [(6, 0), (9, 1), (10, 1), (12, 1), (15, 2), (18, 2), (21, 2), (25, 3), (28, 3), (33, 4)],
    "p6": [
        (12, 6),
        (20, 12),
        (24, 15),
        (29, 18),
        (35, 22),
        (42, 26),
        (51, 32),
        (59, 37),
        (68, 43),
        (79, 50),
    ],
}


def _band(nominal: float) -> int:
    if nominal <= 0:
        raise ValueError(f"nominal {nominal} mm outside ISO 286 table (>0..{_BANDS[-1]} mm)")
    for i, hi in enumerate(_BANDS):
        if nominal <= hi:
            return i
    raise ValueError(f"nominal {nominal} mm outside ISO 286 table (>0..{_BANDS[-1]} mm)")


def _resolve(link: dict) -> dict:
    """Return a link with explicit plus/minus (mm). Raises ValueError on bad fit."""
    if "fit" in link:
        fit = link["fit"]
        i = _band(float(link["nominal"]))
        if fit in _HOLE:
            plus, minus = _HOLE[fit][i] / 1000.0, 0.0
        elif fit in _SHAFT:
            up, lo = _SHAFT[fit][i]
            plus, minus = up / 1000.0, lo / 1000.0
        else:
            raise ValueError(f"unknown ISO fit {fit!r}")
        return {**link, "plus": plus, "minus": minus, "resolvedFrom": f"fit:{fit}"}
    return {**link, "plus": float(link["plus"]), "minus": float(link["minus"])}


def tolerance_stack(chain: list[dict]) -> dict:
    """Worst-case + RSS stack over an ordered chain. Each link is
    ``{label, nominal, plus, minus, direction}`` or ``{label, nominal, fit,
    direction}``. A chain with both +1 and -1 directions is treated as a mating
    pair and classified clearance / transition / interference."""
    if not chain:
        return {"ok": False, "error": "empty tolerance chain"}
    try:
        links = [_resolve(dict(link)) for link in chain]
    except (ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": f"bad tolerance chain: {exc}"}

    nominal = mid = wc_lo = wc_hi = rss_sq = 0.0
    for link in links:
        s = int(link.get("direction", 1))
        nominal += s * float(link["nominal"])
        mid += s * (link["plus"] + link["minus"]) / 2.0
        lo, hi = s * link["minus"], s * link["plus"]
        wc_lo += min(lo, hi)
        wc_hi += max(lo, hi)
        half = (link["plus"] - link["minus"]) / 2.0
        rss_sq += half * half
    rss = math.sqrt(rss_sq)

    out: dict[str, Any] = {
        "ok": True,
        "nominal": round(nominal, 4),
        "worstCase": {
            "min": round(nominal + wc_lo, 4),
            "max": round(nominal + wc_hi, 4),
            "range": round(wc_hi - wc_lo, 4),
        },
        "rss": {
            "min": round(nominal + mid - rss, 4),
            "max": round(nominal + mid + rss, 4),
            "range": round(2 * rss, 4),
        },
        "links": links,
    }
    dirs = {int(link.get("direction", 1)) for link in links}
    if dirs == {1, -1}:
        # gap = hole - shaft (positive = clearance, negative = interference).
        # Clearance: the loosest case still has a gap. Interference: the loosest
        # case still overlaps. Otherwise the range straddles zero (transition).
        gmin, gmax = out["worstCase"]["min"], out["worstCase"]["max"]
        kind = "clearance" if gmin >= 0 else "interference" if gmax <= 0 else "transition"
        out["fit"] = {"type": kind, "minGap": gmin, "maxGap": gmax}
    return out
