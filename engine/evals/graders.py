"""Programmatic graders for produced workspaces.

A fresh engine ``Session`` is opened ON the workspace dir (model.py or
assembly.json — ``Session.startup()`` handles both) and only the rebuilt
ARTIFACTS are measured. The agent transcript is never an input.

Dev-harness note: ``GradingSession`` reads ``session._objects`` (the last-good
shown objects) on purpose; this package is repo-only tooling, not app code.
Module imports stay light — heavy engine/build123d imports happen inside
functions so spec-only tests don't pay the OCC startup cost.
"""

from __future__ import annotations

import itertools
import math
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field


@dataclass
class GraderResult:
    name: str
    passed: bool | None  # None = grader could not run (unknown name)
    score: float  # 0..1
    detail: str = ""
    data: dict = field(default_factory=dict)


class GradingSession:
    """A read-only engine session over an existing workspace dir, with its own
    throwaway artifacts dir (never the workspace's live artifacts)."""

    def __init__(self, workspace: str):
        from solidifai_engine.session import Session

        self.workspace = os.path.abspath(workspace)
        # The engine derives a workspace root from ``artifacts_dir``. Keep this
        # throwaway publication store under the evaluated workspace so model.py
        # stays a safe workspace-relative input, then remove it on close.
        grade_root = os.path.join(self.workspace, ".solidifai")
        os.makedirs(grade_root, exist_ok=True)
        self._artifacts = tempfile.mkdtemp(prefix="sf-grade-", dir=grade_root)
        try:
            self.session = Session(
                self._artifacts, model_path=os.path.join(self.workspace, "model.py")
            )
            self.session.startup()
        except BaseException:
            # No close() will ever run on a half-built session; reap the tmpdir.
            shutil.rmtree(self._artifacts, ignore_errors=True)
            raise

    def objects(self) -> list:
        return list(self.session._objects or [])

    def designed(self) -> list:
        return [o for o in self.objects() if getattr(o, "role", "part") != "reference"]

    def references(self) -> list:
        return [o for o in self.objects() if getattr(o, "role", "part") == "reference"]

    @property
    def has_model(self) -> bool:
        return bool(self.designed())

    def close(self) -> None:
        shutil.rmtree(self._artifacts, ignore_errors=True)


def open_grading_session(workspace: str) -> GradingSession:
    return GradingSession(workspace)


# -- core graders -------------------------------------------------------------


def grade_requirements(gs: GradingSession, spec: dict) -> GraderResult:
    """Pass-rate of the spec's requirements (engine predicate schema), evaluated
    by the engine's own check_requirements."""
    reqs = spec.get("requirements") or []
    gs.session.set_requirements(reqs)
    res = gs.session.check_requirements()
    rows = res.get("requirements", [])
    countable = [r for r in rows if r.get("pass") is not None]
    met = sum(1 for r in countable if r["pass"] is True)
    failed = [str(r.get("id")) for r in countable if r["pass"] is False]
    # Zero countable requirements is vacuous (nothing to fail), not a hard fail.
    score = met / len(countable) if countable else 1.0
    detail = f"{met}/{len(countable)} met" if countable else "no requirements"
    if failed:
        detail += "; failed: " + ", ".join(failed)
    return GraderResult(
        "requirements",
        passed=None if not countable else not failed,
        score=round(score, 4),
        detail=detail,
        data={"requirements": rows},
    )


def grade_dfm(gs: GradingSession, spec: dict) -> GraderResult:
    rep = gs.session.analyze_dfm()
    if not rep.get("ok"):
        return GraderResult("dfm", False, 0.0, rep.get("error", "dfm failed"))
    crit = rep["summary"]["critical"]
    return GraderResult(
        "dfm",
        crit == 0,
        1.0 if crit == 0 else 0.0,
        f"{crit} critical / {rep['summary']['warning']} warning DFM issue(s)",
        data={"summary": rep["summary"]},
    )


def grade_watertight(gs: GradingSession, spec: dict) -> GraderResult:
    manifold = gs.session.get_model_info().get("manifold")
    ok = manifold is True
    return GraderResult("watertight", ok, 1.0 if ok else 0.0, f"manifold={manifold}")


def grade_interference(gs: GradingSession, spec: dict) -> GraderResult:
    rep = gs.session.check_interferences()
    if not rep.get("ok"):
        return GraderResult("interference", False, 0.0, rep.get("error", "check failed"))
    s = rep["summary"]
    ok = s["overlaps"] == 0 and s["disjoint"] == 0
    return GraderResult(
        "interference",
        ok,
        1.0 if ok else 0.0,
        "; ".join(s["flags"]) or "no overlaps, nothing floating",
        data={"summary": s},
    )


def grade_stress(gs: GradingSession, spec: dict) -> GraderResult:
    rep = gs.session.stress_check()
    if not rep.get("ok"):
        return GraderResult("stress", False, 0.0, rep.get("error", "check failed"))
    warn = rep["summary"].get("warning", 0)
    return GraderResult(
        "stress",
        warn == 0,
        1.0 if warn == 0 else 0.0,
        f"{warn} stress warning hot-spot(s)",
        data={"summary": rep["summary"]},
    )


# -- dim-match ----------------------------------------------------------------


def _sorted_bbox(gs: GradingSession) -> list[float]:
    """Pose-invariant overall size: sorted union-bbox extents of the DESIGNED
    parts (reference fixtures excluded, unlike model.json's bbox)."""
    boxes = [o.shape.bounding_box() for o in gs.designed()]
    mins = [min(b.min.X for b in boxes), min(b.min.Y for b in boxes), min(b.min.Z for b in boxes)]
    maxs = [max(b.max.X for b in boxes), max(b.max.Y for b in boxes), max(b.max.Z for b in boxes)]
    return sorted(maxs[i] - mins[i] for i in range(3))


def _holes(gs: GradingSession) -> list[dict]:
    """Geometric hole detection over every designed part (no naming required):
    the same cylindrical-feature analysis behind analyze_import."""
    from solidifai_engine import reverse as reverse_mod

    out = []
    for o in gs.designed():
        for f in reverse_mod.analyze_shape(o.shape)["features"]:
            if f["kind"] == "hole":
                out.append({**f, "part": o.name})
    return out


def _named_part(gs: GradingSession, name: str):
    return next((part for part in gs.designed() if part.name.lower() == name.lower()), None)


def _cylindrical_faces(shape) -> list:
    from build123d import GeomType

    return [face for face in shape.faces() if face.geom_type == GeomType.CYLINDER]


def _axis_components(face) -> list[float]:
    if face.axis_of_rotation is not None:
        direction = face.axis_of_rotation.direction
        return [float(direction.X), float(direction.Y), float(direction.Z)]
    size = face.bounding_box().size
    values = [float(size.X), float(size.Y), float(size.Z)]
    axis = max(range(3), key=lambda index: values[index])
    return [1.0 if index == axis else 0.0 for index in range(3)]


def _face_axis_center(face) -> list[float]:
    """Center of a cylindrical face's bounding axis, not a point on its wall."""
    box = face.bounding_box()
    return [
        (box.min.X + box.max.X) / 2,
        (box.min.Y + box.max.Y) / 2,
        (box.min.Z + box.max.Z) / 2,
    ]


def _box_center_and_size(lo: list[float], hi: list[float]) -> tuple[list[float], list[float]]:
    size = [hi[i] - lo[i] for i in range(3)]
    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    return center, size


def _radial_tooth_count(shape, pitch_radius: float) -> int:
    """Count separated radial excursions in the XY silhouette.

    The root cylinder establishes the pitch geometry; a tooth must protrude at
    least a quarter module beyond it.  Sampling the actual tessellation avoids
    accepting a high face count from fillets or arbitrary decorative cuts.
    """
    vertices, _ = shape.tessellate(0.4)
    bins = [0.0] * 720
    for point in vertices:
        angle = (math.atan2(point.Y, point.X) + 2 * math.pi) % (2 * math.pi)
        index = min(len(bins) - 1, int(angle / (2 * math.pi) * len(bins)))
        bins[index] = max(bins[index], math.hypot(point.X, point.Y))
    raised = [radius > pitch_radius for radius in bins]
    # Join the circular endpoint before counting contiguous radial regions.
    if raised and raised[0] and raised[-1]:
        first_false = next((i for i, value in enumerate(raised) if not value), None)
        if first_false is not None:
            raised = raised[first_false:] + raised[:first_false]
    return sum(value and not raised[index - 1] for index, value in enumerate(raised))


def _axis_line_distance(p1, u1, p2, u2) -> float:
    """Perpendicular distance between two 3D lines (robust to where along the
    axis each location point sits)."""

    def norm(v):
        n = math.sqrt(sum(c * c for c in v)) or 1.0
        return [c / n for c in v]

    u1, u2 = norm(u1), norm(u2)
    d = [p2[i] - p1[i] for i in range(3)]
    cross = [
        u1[1] * u2[2] - u1[2] * u2[1],
        u1[2] * u2[0] - u1[0] * u2[2],
        u1[0] * u2[1] - u1[1] * u2[0],
    ]
    cn = math.sqrt(sum(c * c for c in cross))
    if cn < 1e-6:  # parallel axes: offset of d perpendicular to u1
        t = sum(d[i] * u1[i] for i in range(3))
        perp = [d[i] - t * u1[i] for i in range(3)]
        return math.sqrt(sum(c * c for c in perp))
    return abs(sum(d[i] * cross[i] for i in range(3))) / cn


def _part_spin_axes(gs: GradingSession, names: list[str]) -> list[tuple[list, list]]:
    """(center-of-mass, symmetry axis) per named part. A disc-like part's
    symmetry axis is its max-principal-moment axis. Returns [] when any named
    part lacks inertia (degenerate/zero-volume solid) — the caller degrades to
    a clean miss."""
    m = gs.session.measure()
    out = []
    for nm in names:
        p = next((p for p in m["parts"] if p.get("partName") == nm and p.get("inertia")), None)
        if p is None:
            return []
        i = max(range(3), key=lambda k: p["inertia"]["principalMoments"][k])
        out.append((p["centerOfMass"], p["inertia"]["principalAxes"][i]))
    return out


def _match_parts(gs: GradingSession, name_contains: str | None) -> list:
    parts = gs.designed()
    if name_contains:
        named = [o for o in parts if name_contains.lower() in o.name.lower()]
        if len(named) >= 2:
            return named[:2]
    # Fallback: gears/wheels are the face-densest parts in the scene.
    return sorted(parts, key=lambda o: len(o.shape.faces()), reverse=True)[:2]


def _center_distance(gs: GradingSession, e: dict) -> float | None:
    expected = float(e["expected"])
    if e.get("between") == "holes":
        dia, dtol = float(e["diameter"]), float(e.get("diameter_tol", 0.3))
        hs = [h for h in _holes(gs) if abs(h["diameter"] - dia) <= dtol]
        if len(hs) < 2:
            return None
        dists = [
            _axis_line_distance(a["location"], a["axis"], b["location"], b["axis"])
            for a, b in itertools.combinations(hs, 2)
        ]
        return min(dists, key=lambda d: abs(d - expected))
    parts = _match_parts(gs, e.get("name_contains"))
    if len(parts) < 2:
        return None
    axes = _part_spin_axes(gs, [parts[0].name, parts[1].name])
    if len(axes) < 2:
        return None
    (p1, u1), (p2, u2) = axes
    return _axis_line_distance(p1, u1, p2, u2)


def _feature_metric(gs: GradingSession, e: dict) -> float | None:
    feats = gs.session.inspect_features().get("features", [])
    sub = (e.get("name_contains") or "").lower()
    for f in feats:
        if sub and sub not in f["name"].lower():
            continue
        val = (f.get("metrics") or {}).get(e["metric"])
        if isinstance(val, int | float):
            return float(val)
    return None


def grade_dim_match(gs: GradingSession, spec: dict) -> GraderResult:
    entries = spec.get("expected_dims") or []
    checks = []
    for e in entries:
        kind, expected, tol = e["kind"], float(e["expected"]), float(e["tol"])
        measured: float | None = None
        ok = False
        if kind == "bbox_sorted":
            idx = {"min": 0, "mid": 1, "max": 2}[e["axis"]]
            measured = round(_sorted_bbox(gs)[idx], 3)
            ok = abs(measured - expected) <= tol
        elif kind == "mass":
            measured = gs.session.measure()["total"]["mass"]
            ok = abs(measured - expected) <= tol
        elif kind == "hole":
            matches = [h for h in _holes(gs) if abs(h["diameter"] - expected) <= tol]
            need = int(e.get("count", 1))
            ok = len(matches) >= need
            measured = matches[0]["diameter"] if matches else None
        elif kind == "center_distance":
            measured = _center_distance(gs, e)
            ok = measured is not None and abs(measured - expected) <= tol
        elif kind == "feature":
            measured = _feature_metric(gs, e)
            ok = measured is not None and abs(measured - expected) <= tol
        extra = {k: v for k, v in e.items() if k not in ("kind", "expected", "tol")}
        checks.append(
            {
                "kind": kind,
                "expected": expected,
                "tol": tol,
                "measured": measured,
                "pass": ok,
                **extra,
            }
        )
    n_pass = sum(1 for c in checks if c["pass"])
    misses = [
        f"{c['kind']}={c['measured']} (want {c['expected']}±{c['tol']})"
        for c in checks
        if not c["pass"]
    ]
    return GraderResult(
        "dim_match",
        bool(checks) and n_pass == len(checks),
        round(n_pass / len(checks), 4) if checks else 0.0,
        "; ".join(misses) or f"{len(checks)} dim(s) within tolerance",
        data={"checks": checks},
    )


# -- containment + stability ---------------------------------------------------


def _union_bbox(parts) -> tuple[list[float], list[float]]:
    boxes = [o.shape.bounding_box() for o in parts]
    lo = [min(b.min.X for b in boxes), min(b.min.Y for b in boxes), min(b.min.Z for b in boxes)]
    hi = [max(b.max.X for b in boxes), max(b.max.Y for b in boxes), max(b.max.Z for b in boxes)]
    return lo, hi


def _bbox_inside(inner_lo, inner_hi, outer_lo, outer_hi, tol: float = 0.1) -> bool:
    return all(
        inner_lo[i] >= outer_lo[i] - tol and inner_hi[i] <= outer_hi[i] + tol for i in range(3)
    )


def _match_reference(refs, size_mm, used: set[int]):
    """First unused reference part whose sorted bbox matches size_mm within
    max(2 mm, 20%) per axis, or None."""
    want = sorted(float(v) for v in size_mm)
    for o in refs:
        if id(o) in used:
            continue
        bb = o.shape.bounding_box()
        have = sorted([bb.size.X, bb.size.Y, bb.size.Z])
        if all(abs(have[i] - want[i]) <= max(2.0, 0.2 * want[i]) for i in range(3)):
            used.add(id(o))
            return o
    return None


def _probe_clear(probe_shape, designed, lo, hi) -> bool:
    """True when the probe sits inside the designed union bbox AND intersects no
    designed solid (boolean common via the engine's interference machinery)."""
    from solidifai_engine import interference as itf

    bb = probe_shape.bounding_box()
    if not _bbox_inside([bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z], lo, hi):
        return False
    return all(
        itf.classify_pair(probe_shape, o.shape).get("relation") != "overlap" for o in designed
    )


def grade_containment(gs: GradingSession, spec: dict) -> GraderResult:
    """Reference matching is GREEDY: spec volumes are processed most-constrained
    first (descending volume) so a large reference can't be claimed by a smaller
    spec entry that happens to fit its tolerance band; checks are reported in
    that order."""
    from build123d import Box, Pos

    volumes = (spec.get("containment") or {}).get("volumes") or []
    designed, refs = gs.designed(), gs.references()
    if not designed:
        return GraderResult("containment", False, 0.0, "no geometry", data={"checks": []})
    lo, hi = _union_bbox(designed)
    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    used: set[int] = set()
    checks = []
    for v in sorted(volumes, key=lambda v: -math.prod(float(x) for x in v["size_mm"])):
        size = [float(x) for x in v["size_mm"]]
        if min(size) <= 0:
            checks.append(
                {
                    "name": v.get("name"),
                    "via": "degenerate",
                    "pass": False,
                    "score": 0.0,
                    "detail": "degenerate size_mm",
                }
            )
            continue
        ref = _match_reference(refs, size, used)
        if ref is not None:
            ok = _probe_clear(ref.shape, designed, lo, hi)
            checks.append(
                {"name": v.get("name"), "via": "reference", "pass": ok, "score": 1.0 if ok else 0.0}
            )
        else:
            ok = any(
                _probe_clear(Pos(*center) * Box(perm[0], perm[1], perm[2]), designed, lo, hi)
                for perm in set(itertools.permutations(size))
            )
            checks.append(
                {
                    "name": v.get("name"),
                    "via": "centered-box-fallback",
                    "pass": ok,
                    "score": 0.5 if ok else 0.0,
                }
            )
    score = sum(c["score"] for c in checks) / len(checks) if checks else 0.0
    bad = [str(c["name"]) for c in checks if not c["pass"]]
    detail = ("does not fit inside: " + ", ".join(bad)) if bad else "all contents contained"
    if any(c["via"] == "centered-box-fallback" for c in checks):
        detail += " (no matching reference volume shown; weak centered-box fallback, score capped)"
    return GraderResult(
        "containment", bool(checks) and not bad, round(score, 4), detail, data={"checks": checks}
    )


def grade_stability(gs: GradingSession, spec: dict) -> GraderResult:
    """CoM must project inside the bottom-contact footprint SCALED DOWN to
    footprint_margin about its center (margin 0.9 = inner 90% of the footprint,
    a strictness factor, not a grace band) — the won't-tip-when-tapped
    heuristic."""
    cfg = spec.get("stability") or {}
    margin = float(cfg.get("footprint_margin", 0.9))
    verts: list[tuple] = []
    for o in gs.designed():
        pv, _tris = o.shape.tessellate(0.5)
        verts.extend(tuple(p) for p in pv)
    if not verts:
        return GraderResult("stability", False, 0.0, "no geometry")
    zmin = min(v[2] for v in verts)
    bottom = [v for v in verts if v[2] <= zmin + 1.0]
    xs, ys = [v[0] for v in bottom], [v[1] for v in bottom]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    hx = max((max(xs) - min(xs)) / 2 * margin, 1.0)
    hy = max((max(ys) - min(ys)) / 2 * margin, 1.0)
    com = gs.session.measure()["total"]["centerOfMass"]
    ok = abs(com[0] - cx) <= hx and abs(com[1] - cy) <= hy
    return GraderResult(
        "stability",
        ok,
        1.0 if ok else 0.0,
        f"CoM ({round(com[0], 1)}, {round(com[1], 1)}) vs footprint "
        f"±({round(hx, 1)}, {round(hy, 1)}) about ({round(cx, 1)}, {round(cy, 1)})",
        data={"com": list(com), "footprint": {"cx": cx, "cy": cy, "hx": hx, "hy": hy}},
    )


# -- motion ---------------------------------------------------------------------


def _bbox_volume(o) -> float:
    bb = o.shape.bounding_box()
    return bb.size.X * bb.size.Y * bb.size.Z


def _select_moving(gs: GradingSession, sel: dict):
    parts = gs.designed()
    sub = (sel or {}).get("name_contains")
    if sub:
        named = [o for o in parts if sub.lower() in o.name.lower()]
        if named:
            return max(named, key=_bbox_volume)
    fb = (sel or {}).get("fallback", "largest")
    if fb == "max_faces":
        return max(parts, key=lambda o: len(o.shape.faces()))
    if fb == "smallest":
        return min(parts, key=_bbox_volume)
    return max(parts, key=_bbox_volume)


def _pair_seam_axis(moving, other, inflate: float = 2.0):
    """Center + longest axis of the inflated bbox intersection of the two parts
    (the knuckle/seam region of a hinge). None when they are too far apart."""
    a, b = moving.shape.bounding_box(), other.shape.bounding_box()
    amin, amax = [a.min.X, a.min.Y, a.min.Z], [a.max.X, a.max.Y, a.max.Z]
    bmin, bmax = [b.min.X, b.min.Y, b.min.Z], [b.max.X, b.max.Y, b.max.Z]
    lo = [max(amin[i], bmin[i]) - inflate for i in range(3)]
    hi = [min(amax[i], bmax[i]) + inflate for i in range(3)]
    if any(lo[i] >= hi[i] for i in range(3)):
        return None, None
    origin = [(lo[i] + hi[i]) / 2 for i in range(3)]
    longest = max(range(3), key=lambda i: hi[i] - lo[i])
    direction = [0.0, 0.0, 0.0]
    direction[longest] = 1.0
    return origin, direction


def grade_motion(gs: GradingSession, spec: dict) -> GraderResult:
    cfg = spec.get("motion") or {}
    parts = gs.designed()
    if len(parts) < 2:
        return GraderResult("motion", False, 0.0, "motion check needs at least two parts")
    moving = _select_moving(gs, cfg.get("part") or {})
    if cfg.get("axis") == "self_spin":
        axes = _part_spin_axes(gs, [moving.name])
        if not axes:
            return GraderResult(
                "motion", False, 0.0, f"'{moving.name}' has no inertia; cannot derive spin axis"
            )
        ((origin, direction),) = axes
    else:
        other = max((o for o in parts if o is not moving), key=_bbox_volume)
        origin, direction = _pair_seam_axis(moving, other)
        if origin is None:
            return GraderResult(
                "motion",
                False,
                0.0,
                f"no seam between '{moving.name}' and '{other.name}' (bboxes too far apart)",
            )
    res = gs.session.check_motion(
        part=moving.name,
        kind=cfg.get("kind", "revolute"),
        axis_origin=origin,
        axis_dir=direction,
        start=float(cfg.get("start", 0.0)),
        stop=float(cfg.get("stop", 90.0)),
        steps=int(cfg.get("steps", 12)),
    )
    if not res.get("ok"):
        return GraderResult("motion", False, 0.0, res.get("error", "check_motion failed"))
    expect = cfg.get("expect", "clear_to")
    thr = float(cfg.get("threshold_deg", cfg.get("stop", 90.0)))
    if expect == "collides_within":
        ok = bool(res["collides"]) and res["firstCollision"]["at"] <= thr
        if ok:
            detail = f"'{moving.name}' engages at {res['firstCollision']['at']} deg"
        elif res["collides"]:
            detail = (
                f"'{moving.name}' engages at {res['firstCollision']['at']} deg,"
                f" outside threshold {thr} deg"
            )
        else:
            detail = f"'{moving.name}' never engages within {thr} deg (parts do not actually mesh)"
    else:
        clear_through = res["clearThrough"]
        ok = (not res["collides"]) or (clear_through is not None and clear_through >= thr)
        detail = (
            f"'{moving.name}' swings clear through {clear_through} deg"
            if ok
            else f"'{moving.name}' collides at {res['firstCollision']['at']} deg (needs {thr})"
        )
    return GraderResult(
        "motion",
        ok,
        1.0 if ok else 0.0,
        detail,
        data={
            "axis_origin": origin,
            "axis_dir": direction,
            "result": {k: res[k] for k in ("collides", "firstCollision", "clearThrough", "range")},
        },
    )


# -- typed semantic requirements ----------------------------------------------


def _semantic_check(gs: GradingSession, req: dict) -> dict:
    """Measure a semantic criterion from rebuilt geometry. Names select targets;
    they never substitute for a geometric observation."""
    kind = req["kind"]
    parts = gs.designed()
    if kind == "part_count":
        count = len(parts)
        ok = (
            count == req["count"]
            if "count" in req
            else req.get("min", 0) <= count <= req.get("max", float("inf"))
        )
        return {"id": req["id"], "kind": kind, "pass": ok, "measured": count}
    if kind == "part_name":
        count = sum(o.name.lower() == req["name"].lower() for o in parts)
        ok = count >= req.get("count", 1)
        return {"id": req["id"], "kind": kind, "pass": ok, "measured": count}
    if kind == "part_faces":
        part = next((o for o in parts if o.name.lower() == req["name"].lower()), None)
        faces = len(part.shape.faces()) if part is not None else 0
        return {"id": req["id"], "kind": kind, "pass": faces >= req["min"], "measured": faces}
    if kind == "feature":
        features = gs.session.inspect_features().get("features", [])
        matches = [f for f in features if f.get("name", "").lower() == req["name"].lower()]
        value = None
        if matches and req.get("metric"):
            value = (matches[0].get("metrics") or {}).get(req["metric"])
        ok = bool(matches) and (
            not req.get("metric")
            or isinstance(value, (int, float))
            and req["range"][0] <= value <= req["range"][1]
        )
        return {
            "id": req["id"],
            "kind": kind,
            "pass": ok,
            "measured": value if req.get("metric") else len(matches),
        }
    if kind == "hole_pattern":
        holes = [
            h for h in _holes(gs) if abs(h["diameter"] - req["diameter_mm"]) <= req["tolerance_mm"]
        ]
        return {
            "id": req["id"],
            "kind": kind,
            "pass": len(holes) >= req["count"],
            "measured": len(holes),
        }
    if kind == "radial_gear":
        part = _named_part(gs, req["name"])
        if part is None:
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing part"}
        pitch_radius = req["tooth_count"] * req["module_mm"] / 2
        tolerance = req["module_tolerance_mm"]
        roots = [
            face
            for face in _cylindrical_faces(part.shape)
            if abs(face.radius - pitch_radius) <= tolerance
            and abs(_axis_components(face)[2]) >= 0.99
        ]
        # Boolean-unioned tooth flanks split the pitch cylinder into one exposed
        # cylindrical arc per tooth. Unlike total face count, this is the radial
        # contact topology and cannot be supplied by a smooth blank disc.
        teeth = len(roots)
        return {
            "id": req["id"],
            "kind": kind,
            "pass": teeth == req["tooth_count"],
            "measured": {"pitch_radius_mm": pitch_radius, "teeth": teeth, "root_faces": len(roots)},
        }
    if kind == "gopro_two_prong":
        part = _named_part(gs, req["name"])
        if part is None:
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing part"}
        expected_radius = req["pin_hole_diameter_mm"] / 2
        prong_holes = [
            face
            for face in _cylindrical_faces(part.shape)
            if abs(face.radius - expected_radius) <= req["tolerance_mm"] / 2
            and abs(_axis_components(face)[1]) >= 0.99
        ]
        centers = sorted(face.center().Y for face in prong_holes)
        thicknesses = [face.bounding_box().size.Y for face in prong_holes]
        spacing = centers[1] - centers[0] if len(centers) == 2 else None
        thickness = sum(thicknesses) / len(thicknesses) if thicknesses else None
        gap = spacing - thickness if spacing is not None and thickness is not None else None
        tol = req["tolerance_mm"]
        return {
            "id": req["id"],
            "kind": kind,
            "pass": (
                len(prong_holes) == 2
                and thickness is not None
                and gap is not None
                and abs(thickness - req["prong_thickness_mm"]) <= tol
                and abs(gap - req["prong_gap_mm"]) <= tol
            ),
            "measured": {
                "hole_faces": len(prong_holes),
                "thickness_mm": thickness,
                "gap_mm": gap,
            },
        }
    if kind == "hinge_topology":
        leaf_a, leaf_b = (_named_part(gs, name) for name in req["leaves"])
        pin = _named_part(gs, req["pin"])
        if leaf_a is None or leaf_b is None or pin is None:
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing hinge part"}
        pin_faces = _cylindrical_faces(pin.shape)
        if not pin_faces:
            return {
                "id": req["id"],
                "kind": kind,
                "pass": False,
                "measured": "pin is not cylindrical",
            }
        pin_face = max(pin_faces, key=lambda face: face.area)
        pin_axis = _axis_components(pin_face)
        axis = max(range(3), key=lambda index: abs(pin_axis[index]))
        tolerance = req["tolerance_mm"]

        def knuckles(part, label):
            out = []
            for face in _cylindrical_faces(part.shape):
                direction = _axis_components(face)
                if abs(direction[axis]) < 0.99:
                    continue
                if (
                    _axis_line_distance(
                        _face_axis_center(face), direction, _face_axis_center(pin_face), pin_axis
                    )
                    <= tolerance
                ):
                    out.append((_face_axis_center(face)[axis], label))
            return out

        ordered = sorted(knuckles(leaf_a, "a") + knuckles(leaf_b, "b"))
        labels = [label for _, label in ordered]
        interleaved = bool(labels) and all(
            left != right for left, right in zip(labels, labels[1:], strict=False)
        )
        expected = req["knuckles_per_leaf"]
        counts = {label: labels.count(label) for label in ("a", "b")}
        return {
            "id": req["id"],
            "kind": kind,
            "pass": counts == {"a": expected, "b": expected} and interleaved,
            "measured": {"knuckles": counts, "order": labels, "axis": axis},
        }
    if kind == "wall_hook":
        part = _named_part(gs, req["name"])
        if part is None:
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing part"}
        tol = req["tolerance_mm"]
        mounting = []
        wall_thickness = req.get("wall_thickness_mm")
        if "mount_hole_diameter_mm" in req and "mount_hole_count" in req:
            radius = req["mount_hole_diameter_mm"] / 2
            mounting = [
                face
                for face in _cylindrical_faces(part.shape)
                if abs(face.radius - radius) <= tol / 2 and abs(_axis_components(face)[0]) >= 0.99
            ]
            wall_thickness = max((face.bounding_box().size.X for face in mounting), default=0.0)
        box = part.shape.bounding_box()
        projection = box.size.X - wall_thickness
        vertices, _ = part.shape.tessellate(0.5)
        terminal = [
            point.Z for point in vertices if box.max.X - req["min_projection_mm"] / 2 <= point.X
        ]
        rise = max(terminal) - min(terminal) if terminal else 0.0
        mounting_ok = True
        if "mount_hole_count" in req:
            mounting_ok = len(mounting) >= req["mount_hole_count"]
        return {
            "id": req["id"],
            "kind": kind,
            "pass": (
                mounting_ok
                and projection >= req["min_projection_mm"]
                and rise >= req["min_retaining_rise_mm"]
            ),
            "measured": {
                "mount_holes": len(mounting),
                "wall_thickness_mm": wall_thickness,
                "projection_mm": projection,
                "retaining_rise_mm": rise,
            },
        }
    if kind == "l_bracket":
        from build123d import Box, Pos

        from solidifai_engine import interference as itf

        part = _named_part(gs, req["name"])
        if part is None:
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing part"}
        axis_index = {"x": 0, "y": 1, "z": 2}
        mount_axis = axis_index[req["mount_axis"]]
        span_axis = axis_index[req["span_axis"]]
        rise_axis = axis_index[req["rise_axis"]]
        box = part.shape.bounding_box()
        lo = [box.min.X, box.min.Y, box.min.Z]
        hi = [box.max.X, box.max.Y, box.max.Z]
        span = hi[span_axis] - lo[span_axis]
        rise = hi[rise_axis] - lo[rise_axis]
        projection = hi[mount_axis] - lo[mount_axis] - req["min_mount_thickness_mm"]

        holes = [h for h in _holes(gs) if abs(h["axis"][mount_axis]) >= 0.99]
        hole_center = (
            sum(h["location"][mount_axis] for h in holes) / len(holes)
            if holes
            else (lo[mount_axis] + hi[mount_axis]) / 2
        )
        mount_side = (
            "min"
            if abs(hole_center - lo[mount_axis]) <= abs(hole_center - hi[mount_axis])
            else "max"
        )
        mount_sign = 1.0 if mount_side == "min" else -1.0
        mount_anchor = lo[mount_axis] if mount_side == "min" else hi[mount_axis]
        mount_lo = lo.copy()
        mount_hi = hi.copy()
        mount_hi[mount_axis] = mount_anchor + mount_sign * req["min_mount_thickness_mm"]
        if mount_side == "max":
            mount_lo[mount_axis] = mount_hi[mount_axis]
            mount_hi[mount_axis] = mount_anchor
        mount_center, mount_size = _box_center_and_size(mount_lo, mount_hi)
        mount_probe = Pos(*mount_center) * Box(
            *[max(0.5, value - req["tolerance_mm"]) for value in mount_size]
        )
        has_mount_leg = itf.classify_pair(mount_probe, part.shape).get("relation") != "disjoint"

        def shelf_probe_at(rise_side: str):
            shelf_lo = lo.copy()
            shelf_hi = hi.copy()
            if mount_side == "min":
                shelf_lo[mount_axis] = lo[mount_axis] + req["min_mount_thickness_mm"]
                shelf_hi[mount_axis] = shelf_lo[mount_axis] + req["min_projection_mm"]
            else:
                shelf_hi[mount_axis] = hi[mount_axis] - req["min_mount_thickness_mm"]
                shelf_lo[mount_axis] = shelf_hi[mount_axis] - req["min_projection_mm"]
            if rise_side == "max":
                shelf_lo[rise_axis] = hi[rise_axis] - req["min_mount_thickness_mm"]
            else:
                shelf_hi[rise_axis] = lo[rise_axis] + req["min_mount_thickness_mm"]
            center, size = _box_center_and_size(shelf_lo, shelf_hi)
            probe = Pos(*center) * Box(*[max(0.5, value - req["tolerance_mm"]) for value in size])
            return itf.classify_pair(probe, part.shape).get("relation") != "disjoint"

        has_shelf_leg = shelf_probe_at("min") or shelf_probe_at("max")
        return {
            "id": req["id"],
            "kind": kind,
            "pass": (
                has_mount_leg
                and has_shelf_leg
                and span >= req["min_span_mm"]
                and rise >= req["min_rise_mm"]
                and projection >= req["min_projection_mm"]
            ),
            "measured": {
                "mount_side": mount_side,
                "span_mm": span,
                "rise_mm": rise,
                "projection_mm": projection,
                "mount_leg": has_mount_leg,
                "shelf_leg": has_shelf_leg,
            },
        }
    if kind == "reference_port_pattern":
        from build123d import Box, Pos

        from solidifai_engine import interference as itf

        reference = next(
            (part for part in gs.references() if part.name.lower() == req["reference"].lower()),
            None,
        )
        if reference is None:
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing reference"}
        axis = {"x": 0, "y": 1, "z": 2}[req["axis"]]
        other = [index for index in range(3) if index != axis]
        ref_box = reference.shape.bounding_box()
        ref_center = [
            (ref_box.min.X + ref_box.max.X) / 2,
            (ref_box.min.Y + ref_box.max.Y) / 2,
            (ref_box.min.Z + ref_box.max.Z) / 2,
        ]
        ref_edge = [ref_box.min.X, ref_box.min.Y, ref_box.min.Z][axis]
        if req["side"] == "max":
            ref_edge = [ref_box.max.X, ref_box.max.Y, ref_box.max.Z][axis]
        designed = gs.designed()
        lo, hi = _union_bbox(designed)
        checks = []
        for opening in req["openings"]:
            center = ref_center.copy()
            center[axis] = ref_edge
            center[other[0]] += opening["offset_mm"][0]
            center[other[1]] += opening["offset_mm"][1]
            size = [0.0, 0.0, 0.0]
            size[axis] = opening["size_mm"][0]
            size[other[0]] = opening["size_mm"][1]
            size[other[1]] = opening["size_mm"][2]
            probe = Pos(*center) * Box(size[0], size[1], size[2])
            clear = all(
                itf.classify_pair(probe, part.shape).get("relation") != "overlap"
                for part in designed
            )
            probe_box = probe.bounding_box()
            outer = [probe_box.min.X, probe_box.min.Y, probe_box.min.Z][axis]
            if req["side"] == "max":
                outer = [probe_box.max.X, probe_box.max.Y, probe_box.max.Z][axis]
            checks.append(
                clear
                and (
                    outer >= hi[axis] - req["tolerance_mm"]
                    if req["side"] == "max"
                    else outer <= lo[axis] + req["tolerance_mm"]
                )
            )
        return {"id": req["id"], "kind": kind, "pass": all(checks), "measured": checks}
    if kind == "vent_open_area":
        axis = {"x": 0, "y": 1, "z": 2}[req["axis"]]
        vents = [
            face
            for part in gs.designed()
            for face in _cylindrical_faces(part.shape)
            if face.radius is not None and abs(_axis_components(face)[axis]) >= 0.99
        ]
        area = sum(math.pi * face.radius**2 for face in vents)
        return {
            "id": req["id"],
            "kind": kind,
            "pass": len(vents) >= req["min_count"] and area >= req["min_open_area_mm2"],
            "measured": {"count": len(vents), "open_area_mm2": area},
        }
    if kind == "cavity":
        from build123d import Box, Pos

        lo, hi = _union_bbox(parts)
        center = [(lo[i] + hi[i]) / 2 for i in range(3)]
        size = [v - 2 * req["tolerance_mm"] for v in req["size_mm"]]
        ok = min(size) > 0 and _probe_clear(
            Pos(*center) * Box(size[0], size[1], size[2]), parts, lo, hi
        )
        return {"id": req["id"], "kind": kind, "pass": ok, "measured": size}
    if kind == "cavity_pattern":
        from build123d import Box, Pos

        from solidifai_engine import interference as itf

        centers = req["centers_mm"]
        raw_sizes = req["size_mm"]
        if raw_sizes and isinstance(raw_sizes[0], list):
            sizes = [[v - 2 * req["tolerance_mm"] for v in size] for size in raw_sizes]
        else:
            shared = [v - 2 * req["tolerance_mm"] for v in raw_sizes]
            sizes = [shared for _ in centers]
        slots = [
            _probe_clear(Pos(*center) * Box(size[0], size[1], size[2]), parts, *_union_bbox(parts))
            for center, size in zip(centers, sizes, strict=True)
        ]
        # A single oversize void must not satisfy a multi-cell compartment
        # claim. Each adjacent requested slot needs a real solid divider at its
        # midpoint, measured with a thin probe rather than object names/bboxes.
        separators = []
        for index, (left, right) in enumerate(zip(centers[:-1], centers[1:], strict=True)):
            delta = [right[i] - left[i] for i in range(3)]
            axis = max(range(3), key=lambda i: abs(delta[i]))
            local = [min(sizes[index][i], sizes[index + 1][i]) for i in range(3)]
            cross = [max(1.0, local[i] / 3) for i in range(3)]
            cross[axis] = max(0.5, abs(delta[axis]) / 5)
            midpoint = [(left[i] + right[i]) / 2 for i in range(3)]
            separator = Pos(*midpoint) * Box(cross[0], cross[1], cross[2])
            separators.append(
                any(
                    itf.classify_pair(separator, part.shape).get("relation") == "overlap"
                    for part in parts
                )
            )
        return {
            "id": req["id"],
            "kind": kind,
            "pass": all(min(size) > 0 for size in sizes) and all(slots) and all(separators),
            "measured": {"slots": sum(slots), "separators": sum(separators)},
        }
    if kind == "interface":
        selected = [
            next((o for o in parts if o.name.lower() == name.lower()), None)
            for name in req["parts"]
        ]
        if any(p is None for p in selected):
            return {"id": req["id"], "kind": kind, "pass": False, "measured": "missing part"}
        a, b = selected
        assert a is not None and b is not None
        from solidifai_engine import interference as itf

        relation = itf.classify_pair(a.shape, b.shape)["relation"]
        # Use OCC's closest-point distance, not bbox proximity: unrelated
        # geometry can overlap in a bounding box without forming an interface.
        gap = float(a.shape.distance_to(b.shape))
        return {
            "id": req["id"],
            "kind": kind,
            "pass": relation != "overlap" and gap <= req.get("tolerance_mm", 0.1),
            "measured": {"gap": gap, "relation": relation},
        }
    # Motion reuses the engine-backed motion grader; the named component and
    # requested angular span are still the source of truth.
    start, stop = req["range_deg"]
    result = grade_motion(
        gs,
        {
            "motion": {
                "part": {"name_contains": req["part"]},
                "start": start,
                "stop": stop,
                "threshold_deg": stop,
                "expect": "clear_to",
            }
        },
    )
    return {"id": req["id"], "kind": kind, "pass": result.passed is True, "measured": result.detail}


def grade_semantic(gs: GradingSession, spec: dict) -> GraderResult:
    checks = [_semantic_check(gs, req) for req in spec.get("semantic_requirements", [])]
    passed = bool(checks) and all(c["pass"] for c in checks)
    misses = [c["id"] for c in checks if not c["pass"]]
    return GraderResult(
        "semantic",
        passed,
        1.0 if passed else (sum(c["pass"] for c in checks) / len(checks) if checks else 0.0),
        "all semantic requirements met" if passed else "failed: " + ", ".join(misses),
        data={"checks": checks},
    )


GRADERS: dict[str, Callable[[GradingSession, dict], GraderResult]] = {
    "requirements": grade_requirements,
    "dfm": grade_dfm,
    "watertight": grade_watertight,
    "interference": grade_interference,
    "stress": grade_stress,
    "dim_match": grade_dim_match,
    "containment": grade_containment,
    "stability": grade_stability,
    "motion": grade_motion,
    "semantic": grade_semantic,
}


def grade_workspace(gs: GradingSession, spec: dict) -> dict:
    """Run the spec's graders; programmatic_score = mean of per-grader scores.
    A workspace with no designed geometry scores 0 on every requested grader."""
    results: list[GraderResult] = []
    for name in spec.get("graders", []):
        fn = GRADERS.get(name)
        if fn is None:
            results.append(GraderResult(name, None, 0.0, f"unknown grader {name!r}"))
        elif not gs.has_model:
            results.append(GraderResult(name, False, 0.0, "no model produced"))
        else:
            try:
                results.append(fn(gs, spec))
            except Exception as exc:  # noqa: BLE001 - one broken grader never sinks the run
                results.append(
                    GraderResult(name, False, 0.0, f"grader crashed: {type(exc).__name__}: {exc}")
                )
    score = round(sum(r.score for r in results) / len(results), 4) if results else 0.0
    return {"graders": [asdict(r) for r in results], "programmatic_score": score}
