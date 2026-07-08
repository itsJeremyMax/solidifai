"""Advisory Design-for-Manufacturing geometry checks over a shown shape.

Pure build123d/OCP helpers behind ``Session.analyze_dfm``. Every result is a
heuristic, sourced report -- never a build gate. Kept separate from the session
so the geometry is unit-testable without an engine or socket. FDM is the only
process with a rule set; other processes are recognized but not evaluated
(so we never emit a threshold the design references do not actually state).

Sourced thresholds: references/dfm-additive.md (0.4 mm nozzle, 2-3 perimeters).
"""

from __future__ import annotations

import math

# FDM defaults -- every number except ``min_hole_diameter_mm`` is sourced from
# references/dfm-additive.md. ``min_hole_diameter_mm`` is a conservative tool
# default (the lens gives hole *compensation*, not a hard minimum); violations
# it raises are labeled ``source="tool_default"``.
FDM_DEFAULTS = {
    "min_wall_mm": 0.8,
    "min_wall_load_bearing_mm": 1.2,
    "max_overhang_deg": 45.0,  # surface angle from horizontal; below this = overhang
    "bridge_flat_deg": 10.0,  # downward face within this of horizontal = bridge, not overhang
    "max_bridge_warn_mm": 5.0,
    "max_bridge_crit_mm": 10.0,
    "min_hole_diameter_mm": 2.0,  # tool_default, NOT skill-sourced
    "plate_tol_mm": 0.05,  # a face entirely within this of model min-Z rests on the bed
    # Wall-thickness robustness -- numerical guards, not skill-sourced thresholds.
    # The far wall must be a near-parallel opposing wall: cos of the angle between
    # the cast and the far-wall outward normal >= this. ~0.7 (within ~45 deg of
    # parallel) rejects both grazing ridge skims and readings taken down an edge
    # or rim face, where the "opposite" surface is steeply angled, not a wall.
    "wall_parallel_min_cos": 0.7,
    "wall_min_violation_area_mm2": 8.0,  # contiguous thin area to assert a real thin wall
    "wall_cluster_slack_mm": 1.0,  # base proximity slack when linking adjacent thin samples
}

# Wall-thickness sampling budget -- cap ray casts so a dense mesh stays responsive.
WALL_TESS_MM = 1.0  # deflection for planar faces (a plane meshes exactly anyway)
WALL_TESS_CURVED_MM = 0.3  # finer on curved faces so a flat facet hugs the true surface
WALL_MAX_RAYS = 4000  # global cap; sample every Nth facet past this
WALL_EPS = 1e-3  # nudge the ray start off the origin facet


def analyze_part(shape, process: str = "fdm", config: dict | None = None) -> dict:
    """Return ``{process, evaluated, violations}`` for one shown shape.

    Only ``fdm`` is evaluated; any other process returns
    ``evaluated=False`` with no violations (the session adds an info note).
    """
    process = (process or "").strip().lower()
    if process != "fdm":
        return {"process": process, "evaluated": False, "violations": []}
    cfg = {**FDM_DEFAULTS, **(config or {})}
    violations: list[dict] = []
    min_z = _model_min_z(shape)
    violations += _check_downward_faces(shape, cfg, min_z)
    violations += _check_small_holes(shape, cfg)
    wall_violations, min_wall = _wall_report(shape, cfg)
    violations += wall_violations
    return {
        "process": process,
        "evaluated": True,
        "violations": violations,
        "metrics": {"minWallMm": round(min_wall, 3) if min_wall is not None else None},
    }


# -- shared geometry helpers ------------------------------------------------


def _model_min_z(shape) -> float:
    return float(shape.bounding_box().min.Z)


def _face_normal(face):
    """Representative outward unit normal at the face center, or None."""
    try:
        c = face.center()
        n = face.normal_at(c)
        return (float(n.X), float(n.Y), float(n.Z))
    except Exception:  # noqa: BLE001 - degenerate faces are skipped
        return None


def _face_max_z(face) -> float:
    return float(face.bounding_box().max.Z)


def _face_xy_narrow(face) -> float:
    """The narrower in-plane bbox dimension -- the most defensible single
    estimate of an unsupported bridge width for a flat downward face."""
    bb = face.bounding_box()
    return min(float(bb.size.X), float(bb.size.Y))


def _surface_angle_from_horizontal(nz: float) -> float:
    """Angle (deg) the surface makes with the build plate: 0 = horizontal
    ceiling, 90 = vertical wall. Equals the normal's acute angle from the Z
    axis (the normal is perpendicular to the surface)."""
    nz = max(-1.0, min(1.0, abs(nz)))
    return math.degrees(math.acos(nz))


def _loc(point) -> list[float]:
    return [round(float(point.X), 4), round(float(point.Y), 4), round(float(point.Z), 4)]


# -- overhang + bridge ------------------------------------------------------


def _check_downward_faces(shape, cfg, min_z) -> list[dict]:
    out: list[dict] = []
    try:
        faces = list(shape.faces())
    except Exception:  # noqa: BLE001
        return out
    for f in faces:
        n = _face_normal(f)
        if n is None or n[2] >= 0:  # only downward faces overhang
            continue
        if _face_max_z(f) <= min_z + cfg["plate_tol_mm"]:  # whole face rests on the bed
            continue
        phi = _surface_angle_from_horizontal(n[2])
        loc = _loc(f.center())
        if phi < cfg["bridge_flat_deg"]:
            span = _face_xy_narrow(f)
            if span > cfg["max_bridge_warn_mm"]:
                crit = span >= cfg["max_bridge_crit_mm"]
                out.append(
                    {
                        "rule": "bridge",
                        "severity": "critical" if crit else "warning",
                        "message": f"Flat unsupported span ~{span:.1f} mm exceeds the "
                        f"{cfg['max_bridge_warn_mm']:.0f} mm FDM bridge limit.",
                        "measured": {"value": round(span, 2), "unit": "mm"},
                        "threshold": {"value": cfg["max_bridge_warn_mm"], "unit": "mm"},
                        "location": loc,
                        "source": "dfm-additive.md",
                        "hint": "Add a support, reorient, or break it into shorter spans.",
                    }
                )
        elif phi < cfg["max_overhang_deg"]:
            out.append(
                {
                    "rule": "overhang",
                    "severity": "warning",
                    "message": f"Downward face at ~{phi:.0f} deg from horizontal is shallower "
                    f"than the {cfg['max_overhang_deg']:.0f} deg support-free limit.",
                    "measured": {"value": round(phi, 1), "unit": "deg"},
                    "threshold": {"value": cfg["max_overhang_deg"], "unit": "deg"},
                    "location": loc,
                    "source": "dfm-additive.md",
                    "hint": "Keep faces >= 45 deg from horizontal, add support, or reorient.",
                }
            )
    return out


# -- small holes ------------------------------------------------------------


def _cylinder_radius(face):
    """Radius of a cylindrical face via the OCP surface adaptor, or None."""
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        return float(BRepAdaptor_Surface(face.wrapped).Cylinder().Radius())
    except Exception:  # noqa: BLE001 - non-cylinder / adaptor failure
        return None


def _is_hole(face, solid_center=None) -> bool:
    """A concave cylindrical face = a hole. The face's outward normal (away from
    material) points radially TOWARD the cylinder axis for a hole and away from it
    for a boss. Testing against the cylinder *axis* (not the solid center) so
    off-center holes classify correctly. ``solid_center`` is accepted but unused."""
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        axis = BRepAdaptor_Surface(face.wrapped).Cylinder().Axis()
        ap, ad = axis.Location(), axis.Direction()
        c = face.center()
        n = face.normal_at(c)
        vx, vy, vz = c.X - ap.X(), c.Y - ap.Y(), c.Z - ap.Z()
        along = vx * ad.X() + vy * ad.Y() + vz * ad.Z()
        rx, ry, rz = vx - along * ad.X(), vy - along * ad.Y(), vz - along * ad.Z()
        # normal pointing inward (opposite the outward radial direction) = hole
        return (n.X * rx + n.Y * ry + n.Z * rz) < 0
    except Exception:  # noqa: BLE001
        return False


def _check_small_holes(shape, cfg) -> list[dict]:
    out: list[dict] = []
    try:
        faces = list(shape.faces())
        center = shape.center()
    except Exception:  # noqa: BLE001
        return out
    min_d = cfg["min_hole_diameter_mm"]
    # An intersecting feature (e.g. a slot) can bisect one hole into several arc-faces
    # on the *same* cylinder, so decide per axis, not per arc: group concave cylindrical
    # faces by their shared axis line + radius and sum the arc U-spans. A lone inner
    # fillet stays a single ~pi/2 arc (rejected); a whole or split hole reconstructs well
    # past that, so it is flagged exactly once -- neither dropped nor double-counted.
    groups: dict = {}
    for f in faces:
        try:
            if "CYLINDER" not in str(f.geom_type):
                continue
        except Exception:  # noqa: BLE001
            continue
        if not _is_hole(f, center):
            continue
        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.BRepTools import BRepTools

            cyl = BRepAdaptor_Surface(f.wrapped).Cylinder()
            axis = cyl.Axis()
            loc, direction = axis.Location(), axis.Direction()
            r = float(cyl.Radius())
            umin, umax, _vmin, _vmax = BRepTools.UVBounds_s(f.wrapped)
        except Exception:  # noqa: BLE001
            continue
        key = (
            round(loc.X(), 2),
            round(loc.Y(), 2),
            round(loc.Z(), 2),
            round(abs(direction.X()), 2),
            round(abs(direction.Y()), 2),
            round(abs(direction.Z()), 2),
            round(r, 3),
        )
        c = f.center()
        g = groups.setdefault(key, {"span": 0.0, "r": r, "x": 0.0, "y": 0.0, "z": 0.0, "n": 0})
        g["span"] += umax - umin
        g["x"] += c.X
        g["y"] += c.Y
        g["z"] += c.Z
        g["n"] += 1
    for g in groups.values():
        # a lone concave fillet spans ~pi/2; a hole (whole 2*pi, or split into arcs) sums well past.
        if g["span"] < 2.5:
            continue
        d = round(g["r"] * 2.0, 2)
        if d >= min_d:
            continue
        n = g["n"]
        loc = [round(g["x"] / n, 4), round(g["y"] / n, 4), round(g["z"] / n, 4)]
        out.append(
            {
                "rule": "small_hole",
                "severity": "advisory",
                "message": f"Hole diameter {d:.1f} mm is below the {min_d:.1f} mm "
                f"reliable-print minimum.",
                "measured": {"value": d, "unit": "mm"},
                "threshold": {"value": min_d, "unit": "mm"},
                "location": loc,
                "source": "tool_default",
                "hint": "Enlarge the hole, or drill it as a post-process.",
            }
        )
    return out


# -- wall thickness (sampled inward ray cast) -------------------------------
#
# From a point on a surface, cast a ray into the material; the wall thickness is
# where the ray *leaves the solid again* -- the first forward intersection whose
# transition is OUT and which is hit near-perpendicularly. Taking the nearest hit
# instead is the classic false positive: a flat tessellation facet on a curved
# face sits slightly inside the true surface (on the cavity side), so the nearest
# hit is the ray re-piercing the very surface it started on, reading ~0 mm. That
# self-hit is an entering (IN) transition, so keying on the first OUT skips it and
# lands on the real far wall. Per-face sampling with the exact B-rep normal (not
# the discrete facet normal) keeps the cast direction stable on slivers and seams.


def _face_outward_normal(face, x, y, z):
    """Exact outward unit normal of ``face`` at the surface point nearest (x,y,z),
    as a 3-tuple, or None when the projection is degenerate."""
    try:
        from build123d import Vector

        n = face.normal_at(Vector(x, y, z))
        return (float(n.X), float(n.Y), float(n.Z))
    except Exception:  # noqa: BLE001 - degenerate UV / projection failure
        return None


def _hit_outward_normal(hit_face, u, v):
    """Outward unit normal of a raw OCC hit face at (u, v), honoring orientation."""
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepLProp import BRepLProp_SLProps
        from OCP.TopAbs import TopAbs_REVERSED

        props = BRepLProp_SLProps(BRepAdaptor_Surface(hit_face), u, v, 1, 1e-7)
        if not props.IsNormalDefined():
            return None
        n = props.Normal()
        nx, ny, nz = n.X(), n.Y(), n.Z()
        if hit_face.Orientation() == TopAbs_REVERSED:
            nx, ny, nz = -nx, -ny, -nz
        return (nx, ny, nz)
    except Exception:  # noqa: BLE001
        return None


def _first_exit_distance(inter, sx, sy, sz, dx, dy, dz, min_cos):
    """Distance along (dx,dy,dz) to where the ray first *leaves the solid* through
    a near-parallel opposing wall, or None. Skips self re-piercing (an entering
    hit, the curved-facet false positive), grazing skims of a convex ridge, and
    exits through a steeply angled edge/rim face (not a real wall)."""
    try:
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
        from OCP.IntCurveSurface import IntCurveSurface_TransitionOnCurve as _Tr

        inter.Perform(gp_Lin(gp_Pnt(sx, sy, sz), gp_Dir(dx, dy, dz)), 0.0, 1e9)
        if not inter.IsDone() or inter.NbPnt() < 1:
            return None
        # Sort by distance only: the tuples carry OCC Face handles that aren't
        # comparable, so a tie on WParameter would otherwise raise.
        hits = sorted(
            (
                (
                    inter.WParameter(i),
                    inter.Transition(i),
                    inter.Face(i),
                    inter.UParameter(i),
                    inter.VParameter(i),
                )
                for i in range(1, inter.NbPnt() + 1)
                if inter.WParameter(i) > WALL_EPS
            ),
            key=lambda h: h[0],
        )
        for w, transition, face, u, v in hits:
            if transition != _Tr.IntCurveSurface_Out:  # not leaving the solid -> skip
                continue
            n = _hit_outward_normal(face, u, v)
            if n is None:  # can't judge the angle -> trust the topological exit
                return w
            if dx * n[0] + dy * n[1] + dz * n[2] >= min_cos:  # near-parallel opposing wall
                return w
        return None
    except Exception:  # noqa: BLE001 - a bad cast is skipped, never fatal
        return None


def _sample_walls(solid, cfg) -> list[dict]:
    """Per-face wall-thickness samples for one solid: one ray per tessellation
    facet, cast inward along the exact face normal and measured to the first wall
    exit. Each sample carries its facet area and originating face type so the
    caller can demand a real contiguous region and classify likely artifacts."""
    try:
        from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    except Exception:  # noqa: BLE001 - OCP layout differs -> skip the check
        return []
    try:
        faces = list(solid.faces())
    except Exception:  # noqa: BLE001
        return []
    # Gather every facet with its originating-face metadata first, then stride to
    # the ray budget so finely-meshed curved faces don't crowd out planar ones.
    facets: list[tuple] = []
    for face in faces:
        try:
            ftype = str(face.geom_type)
        except Exception:  # noqa: BLE001
            ftype = ""
        curved = "PLANE" not in ftype
        defl = WALL_TESS_CURVED_MM if curved else WALL_TESS_MM
        try:
            verts, tris = face.tessellate(defl)
            verts = [(float(p.X), float(p.Y), float(p.Z)) for p in verts]
        except Exception:  # noqa: BLE001
            continue
        for a, b, c in tris:
            ax, ay, az = verts[a]
            bx, by, bz = verts[b]
            cx, cy, cz = verts[c]
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx - ax, cy - ay, cz - az
            wx, wy, wz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            area = 0.5 * (wx * wx + wy * wy + wz * wz) ** 0.5
            if area <= 0:
                continue
            px, py, pz = (ax + bx + cx) / 3, (ay + by + cy) / 3, (az + bz + cz) / 3
            facets.append((px, py, pz, face, area, ftype, curved))
    if not facets:
        return []
    try:
        inter = IntCurvesFace_ShapeIntersector()
        inter.Load(solid.wrapped, 1e-6)
    except Exception:  # noqa: BLE001
        return []
    step = max(1, len(facets) // WALL_MAX_RAYS)
    min_cos = cfg["wall_parallel_min_cos"]
    samples: list[dict] = []
    for i in range(0, len(facets), step):
        px, py, pz, face, area, ftype, curved = facets[i]
        n = _face_outward_normal(face, px, py, pz)
        if n is None:
            continue
        dx, dy, dz = -n[0], -n[1], -n[2]  # inward
        dist = _first_exit_distance(
            inter, px + dx * WALL_EPS, py + dy * WALL_EPS, pz + dz * WALL_EPS, dx, dy, dz, min_cos
        )
        if dist is None:
            continue
        samples.append(
            {
                "t": dist + WALL_EPS,
                "point": [round(px, 4), round(py, 4), round(pz, 4)],
                "area": area,
                "face_type": ftype,
                "curved": curved,
            }
        )
    return samples


def _face_label(face_type: str) -> str:
    """'GeomType.CONE' -> 'cone' for the report payload."""
    return face_type.rsplit(".", 1)[-1].lower() if face_type else "unknown"


def _cluster_thin_samples(samples, slack_mm) -> list[list[dict]]:
    """Group thin samples into contiguous regions (union-find). Two samples link
    when they are within ``slack`` plus their facet radii, so a few large planar
    facets merge into one region while small curved facets stay tightly local."""
    n = len(samples)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    rad = [(s["area"] / math.pi) ** 0.5 for s in samples]
    pts = [s["point"] for s in samples]
    for i in range(n):
        xi, yi, zi = pts[i]
        for j in range(i + 1, n):
            xj, yj, zj = pts[j]
            d = ((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2) ** 0.5
            if d <= slack_mm + rad[i] + rad[j]:
                parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(samples[i])
    return list(groups.values())


def _violations_from_samples(samples, cfg) -> list[dict]:
    """Wall-thickness violations for one solid's samples. A sub-threshold region
    must span a real contiguous area to be asserted; an isolated tiny reading is
    downgraded to an advisory ``possibleArtifact`` (with its face classification)
    rather than a hard critical, so a lone grazing/sliver sample never gates."""
    if not samples:
        return []
    min_t = min(s["t"] for s in samples)
    lb = cfg["min_wall_load_bearing_mm"]
    thin = [s for s in samples if s["t"] < lb]
    out: list[dict] = []
    for cluster in _cluster_thin_samples(thin, cfg["wall_cluster_slack_mm"]):
        worst = min(cluster, key=lambda s: s["t"])
        ct = worst["t"]
        area = sum(s["area"] for s in cluster)
        artifact = area < cfg["wall_min_violation_area_mm2"]
        if ct < cfg["min_wall_mm"]:
            base_sev, thr = "critical", cfg["min_wall_mm"]
            base_msg = f"Wall ~{ct:.2f} mm is below the {thr:.1f} mm FDM minimum."
        else:
            base_sev, thr = "advisory", lb
            base_msg = f"Wall ~{ct:.2f} mm is thin for a load-bearing part (want >= {lb:.1f} mm)."
        if artifact:
            sev = "advisory"
            msg = (
                f"Possible thin wall ~{ct:.2f} mm at an isolated spot on a "
                f"{_face_label(worst['face_type'])} face (measured minimum wall {min_t:.2f} mm). "
                f"Likely a sampling artifact on a curved or edge region, not a real thin wall."
            )
        else:
            sev, msg = base_sev, base_msg
        out.append(
            {
                "rule": "wall_thickness",
                "severity": sev,
                "message": msg,
                "measured": {"value": round(ct, 2), "unit": "mm"},
                "threshold": {"value": thr, "unit": "mm"},
                "minWall": {"value": round(min_t, 2), "unit": "mm"},
                "location": worst["point"],
                "source": "dfm-additive.md",
                "sampled": True,
                "possibleArtifact": artifact,
                "classification": {
                    "faceType": _face_label(worst["face_type"]),
                    "curved": bool(worst["curved"]),
                    "areaMm2": round(area, 2),
                    "samples": len(cluster),
                },
                "hint": "Thicken to >= 0.8 mm (>= 1.2 mm if load-bearing).",
            }
        )
    # Critical first so callers that read walls[0] see the most severe finding.
    out.sort(key=lambda v: {"critical": 0, "warning": 1, "advisory": 2}.get(v["severity"], 3))
    return out


def _wall_report(shape, cfg) -> tuple[list[dict], float | None]:
    """All wall-thickness violations across a shape's solids plus the measured
    minimum wall (mm). The minimum is always returned, even when no violation is
    raised, so the report can state 'min wall 3.1 mm' instead of an outlier 0."""
    violations: list[dict] = []
    overall_min: float | None = None
    try:
        solids = list(shape.solids())
    except Exception:  # noqa: BLE001
        return [], None
    for solid in solids:
        samples = _sample_walls(solid, cfg)
        if not samples:
            continue
        smin = min(s["t"] for s in samples)
        overall_min = smin if overall_min is None else min(overall_min, smin)
        violations += _violations_from_samples(samples, cfg)
    return violations, overall_min


def min_wall_mm(shape) -> float | None:
    """Sampled minimum wall thickness (mm) across all solids, or None when the
    geometry can't be sampled. Shares the per-face sampler with the DFM check."""
    if shape is None:
        return None
    return _wall_report(shape, FDM_DEFAULTS)[1]
