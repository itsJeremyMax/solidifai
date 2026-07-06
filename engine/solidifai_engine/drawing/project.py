"""Hidden-line projection of a 3D shape to 2D view polylines (OCC HLR).

For each named view we set up an HLR projector along the view direction, run
hidden-line removal, then discretize the visible (and hidden) edges and project
their 3D points onto the view's screen axes (u = right, v = up) to get 2D mm
polylines. Everything is wrapped defensively: a bad edge or an empty view yields
no polylines rather than raising, so one odd face never breaks a drawing.
"""

from __future__ import annotations

import math

# Screen frame per view (model is Z-up): zdir points toward the viewer, updir is
# screen-up; the right axis is zdir x updir. u = P.xdir, v = P.updir.
_ISO = 1.0 / math.sqrt(3.0)
VIEWS = {
    "front": {"zdir": (0.0, 1.0, 0.0), "updir": (0.0, 0.0, 1.0)},
    "top": {"zdir": (0.0, 0.0, 1.0), "updir": (0.0, -1.0, 0.0)},
    "right": {"zdir": (1.0, 0.0, 0.0), "updir": (0.0, 0.0, 1.0)},
    "iso": {"zdir": (_ISO, _ISO, _ISO), "updir": (0.0, 0.0, 1.0)},
}


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    m = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


def _frame(view: str):
    """Return orthonormal (xdir, updir, zdir) screen axes for a view."""
    spec = VIEWS[view]
    zdir = _norm(spec["zdir"])
    up0 = spec["updir"]
    # Re-orthogonalize up against z (matters for iso), then x = z x up.
    up = _norm(
        (
            up0[0] - _dot(up0, zdir) * zdir[0],
            up0[1] - _dot(up0, zdir) * zdir[1],
            up0[2] - _dot(up0, zdir) * zdir[2],
        )
    )
    xdir = _norm(_cross(zdir, up))
    return xdir, up, zdir


def view_axes(view: str):
    """Public orthonormal screen axes (xdir=u, updir=v, zdir=toward viewer)."""
    return _frame(view)


def project_point(view: str, xyz) -> tuple:
    """Project a 3D model point to this view's 2D (u, v) mm, using the SAME frame
    the HLR edges are projected with -- so located marks land on drawn geometry.

    The HLR projector is set up as ``gp_Ax2(origin, zdir, xdir)``, so OCC derives
    the edges' screen-Y as ``zdir x xdir`` (which equals ``-updir``). v therefore
    grows downward, matching the rendered view -- not the math-up ``updir``."""
    xdir, _up, zdir = _frame(view)
    vdir = _cross(zdir, xdir)
    return (_dot(xyz, xdir), _dot(xyz, vdir))


def _edges_to_polylines(compound, deflection: float) -> list:
    """Discretize each edge of an HLR output compound. The edges are already in
    the projector's local 2D frame (its X/Y are the screen axes, Z is depth), so
    we read X()/Y() directly -- the view's orientation came from the ax2 frame."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_UniformDeflection
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    polylines = []
    exp = TopExp_Explorer(compound, TopAbs_EDGE)
    while exp.More():
        try:
            edge = TopoDS.Edge_s(exp.Current())
            disc = GCPnts_UniformDeflection(BRepAdaptor_Curve(edge), deflection)
            if disc.IsDone() and disc.NbPoints() >= 2:
                pts = [
                    (disc.Value(i).X(), disc.Value(i).Y()) for i in range(1, disc.NbPoints() + 1)
                ]
                polylines.append(pts)
        except Exception:  # noqa: BLE001 - skip a degenerate edge, never fail the view
            pass
        exp.Next()
    return polylines


def project_view(shape, view: str, deflection: float = 0.1) -> dict:
    """Project ``shape`` for ``view`` -> ``{"visible": [...], "hidden": [...]}``
    where each entry is a polyline (list of (u, v) mm points in view space).
    Returns empty lists (never raises) when the view yields nothing."""
    if view not in VIEWS:
        raise ValueError(f"unknown view {view!r}; expected one of {', '.join(VIEWS)}")
    try:
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        from OCP.HLRAlgo import HLRAlgo_Projector
        from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
    except Exception:  # noqa: BLE001 - HLR unavailable -> no geometry
        return {"visible": [], "hidden": []}

    xdir, updir, zdir = _frame(view)
    try:
        ax2 = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*zdir), gp_Dir(*xdir))
        algo = HLRBRep_Algo()
        algo.Add(shape.wrapped)
        algo.Projector(HLRAlgo_Projector(ax2))
        algo.Update()
        algo.Hide()
        hlr = HLRBRep_HLRToShape(algo)
    except Exception:  # noqa: BLE001
        return {"visible": [], "hidden": []}

    def _compound(getter):
        try:
            comp = getter()
            return _edges_to_polylines(comp, deflection) if comp is not None else []
        except Exception:  # noqa: BLE001
            return []

    return {
        "visible": _compound(hlr.VCompound),
        "hidden": _compound(hlr.HCompound),
    }


def polylines_bbox(polylines: list):
    """(min_u, min_v, max_u, max_v) over all polylines, or None when empty."""
    pts = [p for pl in polylines for p in pl]
    if not pts:
        return None
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return (min(us), min(vs), max(us), max(vs))
