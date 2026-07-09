"""Spatial measure/query geometry behind the read-only measure_between /
query_faces / thickness_at tools.

Pure geometry over the session's last-good snapshot (``self.s._objects`` and
``self.s._features``): distance between two targets (features, parts,
occurrences, faces, or literal points), a filtered enumeration of the model's
faces with stable per-build ids, and (via ``dfm.thickness_at``) local wall
thickness. Read-only — never mutates the model. Kept in its own module so the
geometry is unit-testable without an engine or socket.

Operates per-face (never on compound-level GProps) so mirrored / negative-
determinant occurrences measure correctly.
"""

from __future__ import annotations

import contextlib
import math
import re
from typing import TYPE_CHECKING

from solidifai_engine import dfm

if TYPE_CHECKING:
    from solidifai_engine.session import Session

# Face id form: "<object>:f<index>". Object names carry letters/digits/@/-/_//;
# never a colon, so the trailing ":f<n>" is an unambiguous suffix.
_FACE_ID_RE = re.compile(r"^(.+):f(\d+)$")

# Default half-angle (deg) for the query_faces ``axis`` alignment filter.
DEFAULT_AXIS_TOL_DEG = 5.0

_KIND_BY_GEOM = {
    "PLANE": "planar",
    "CYLINDER": "cylindrical",
    "CONE": "conical",
    "SPHERE": "spherical",
    "TORUS": "toroidal",
}


class SpatialError(Exception):
    """A user-facing spatial error (unknown target, bad face id). Carries a plain
    message with no em dashes; the session turns it into an ``ok=False`` envelope."""


def _round3(v) -> list[float]:
    return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(v[2]), 4)]


def _vlen(v) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v):
    n = _vlen(v)
    if n == 0:
        return None
    return (v[0] / n, v[1] / n, v[2] / n)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _line_line_distance(p1, d1, p2, d2) -> float:
    """Shortest distance between two infinite lines (point + unit direction).

    Parallel lines fall back to the perpendicular component of the offset; skew
    lines use ``|(p2-p1) . (d1 x d2)| / |d1 x d2|``."""
    w = _sub(p2, p1)
    n = _cross(d1, d2)
    nlen = _vlen(n)
    if nlen < 1e-9:  # parallel: reject the component along the shared direction
        along = _dot(w, d1)
        perp = (w[0] - along * d1[0], w[1] - along * d1[1], w[2] - along * d1[2])
        return _vlen(perp)
    return abs(_dot(w, n)) / nlen


def _axis_angle_deg(d1, d2) -> float:
    """Acute angle (deg) between two axis directions; antiparallel reads 0."""
    c = max(-1.0, min(1.0, abs(_dot(d1, d2))))
    return round(math.degrees(math.acos(c)), 4)


def _surface_kind(face) -> str:
    try:
        geom = str(face.geom_type).rsplit(".", 1)[-1]
    except Exception:  # noqa: BLE001
        return "other"
    return _KIND_BY_GEOM.get(geom, "other")


def _cyl_axis_radius(face, kind: str):
    """Return ``(axis_pos, axis_dir_unit, radius)`` for a cylindrical/conical face
    via build123d's per-face axis of rotation, or ``None`` when unavailable."""
    if kind not in ("cylindrical", "conical"):
        return None
    try:
        ax = face.axis_of_rotation
        if ax is None:
            return None
        pos = (float(ax.position.X), float(ax.position.Y), float(ax.position.Z))
        d = _unit((float(ax.direction.X), float(ax.direction.Y), float(ax.direction.Z)))
        if d is None:
            return None
        try:
            radius = round(float(face.radius), 4)
        except Exception:  # noqa: BLE001 - a cone has no single radius
            radius = None
        return (pos, d, radius)
    except Exception:  # noqa: BLE001
        return None


def _describe_face(face, face_id: str, object_name: str) -> dict:
    """Stable descriptor for one face. Per-face center/area/bbox (mirror-safe),
    plane normal or rotation axis, and radius for round surfaces."""
    kind = _surface_kind(face)
    desc: dict = {"id": face_id, "object": object_name, "type": kind}
    try:
        c = face.center()
        desc["center"] = _round3((c.X, c.Y, c.Z))
    except Exception:  # noqa: BLE001
        desc["center"] = None
    try:
        desc["area"] = round(float(face.area), 4)
    except Exception:  # noqa: BLE001
        desc["area"] = None
    try:
        bb = face.bounding_box()
        desc["bbox"] = [round(bb.size.X, 4), round(bb.size.Y, 4), round(bb.size.Z, 4)]
    except Exception:  # noqa: BLE001
        desc["bbox"] = None

    cyl = _cyl_axis_radius(face, kind)
    if cyl is not None:
        pos, d, radius = cyl
        desc["normal_or_axis"] = _round3(d)
        desc["_axis_pos"] = pos  # private: point on the axis line, for measure_between
        if radius is not None:
            desc["radius"] = radius
    else:
        try:
            n = face.normal_at()
            desc["normal_or_axis"] = _round3((n.X, n.Y, n.Z))
        except Exception:  # noqa: BLE001
            desc["normal_or_axis"] = None
        if kind in ("spherical", "toroidal"):
            with contextlib.suppress(Exception):  # a torus radius may not resolve
                desc["radius"] = round(float(face.radius), 4)
    return desc


class _Target:
    """A resolved measure target: a shape (or a literal point), a representative
    center, an optional cylinder axis, and a display label."""

    def __init__(self, kind, label, shape, center, cyl=None):
        self.kind = kind
        self.label = label
        self.shape = shape  # build123d shape, or None for a literal point
        self.center = center  # [x,y,z] or None
        self.cyl = cyl  # (axis_pos, axis_dir, radius) or None


class Spatial:
    def __init__(self, s: Session):
        self.s = s
        self._cache_build: int | None = None
        self._cache: dict | None = None  # object_key -> list[(descriptor, face_shape)]

    # -- face enumeration (memoized per build) ------------------------------

    def _object_keys(self) -> list[str]:
        """Display key per object, aligned to ``self.s._objects``. Uses the raw
        name; a duplicate name is disambiguated with a ``_2`` suffix (feature
        convention) so every face id stays unique within a build."""
        keys: list[str] = []
        used: set[str] = set()
        counts: dict[str, int] = {}
        for o in self.s._objects or []:
            base = o.name
            key = base
            while key in used:
                counts[base] = counts.get(base, 1) + 1
                key = f"{base}_{counts[base]}"
            used.add(key)
            keys.append(key)
        return keys

    def _faces(self) -> dict:
        """``{object_key: [(descriptor, face_shape), ...]}`` for the current build,
        memoized so a query and a follow-up face-id measure reuse one enumeration."""
        if self._cache is not None and self._cache_build == self.s.build_id:
            return self._cache
        cache: dict = {}
        keys = self._object_keys()
        for o, key in zip(self.s._objects or [], keys, strict=True):
            entries: list = []
            try:
                faces = list(o.shape.faces())
            except Exception:  # noqa: BLE001 - a non-face object contributes nothing
                faces = []
            for idx, face in enumerate(faces):
                entries.append((_describe_face(face, f"{key}:f{idx}", key), face))
            cache[key] = entries
        self._cache = cache
        self._cache_build = self.s.build_id
        return cache

    # -- target resolution --------------------------------------------------

    @staticmethod
    def _is_point(t) -> bool:
        return (
            isinstance(t, (list, tuple))
            and len(t) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in t)
        )

    def _feature_cyl(self, faces):
        """Axis of the first cylindrical/conical face in a feature's faces, if any."""
        for f in faces or []:
            got = _cyl_axis_radius(f, _surface_kind(f))
            if got is not None:
                return got
        return None

    def _resolve(self, t) -> _Target:
        if self._is_point(t):
            pt = [float(t[0]), float(t[1]), float(t[2])]
            return _Target("point", f"[{pt[0]}, {pt[1]}, {pt[2]}]", None, pt)
        if not isinstance(t, str):
            raise SpatialError(
                "target must be a name (feature/part/occurrence/face id) or a [x, y, z] point"
            )

        # Face id: "<object>:f<index>"
        m = _FACE_ID_RE.match(t)
        if m:
            return self._resolve_face(t, m.group(1), int(m.group(2)))

        # Feature name (single-model "bore" or namespaced "wheel@2/bore").
        by_feature = {f.name: f for f in self.s._features}
        if t in by_feature:
            rec = by_feature[t]
            faces = getattr(rec, "faces", []) or []
            shape = self._compound_of(faces)
            center = self._faces_center(faces)
            return _Target("feature", t, shape, center, self._feature_cyl(faces))

        # Object / part / occurrence name (raw name, disambiguated key, or node id).
        obj = self._resolve_object(t)
        if obj is not None:
            o, key = obj
            center = self._shape_center(o.shape)
            return _Target("object", key, o.shape, center)

        # An occurrence prefix ("wheel@2") names every body placed under it
        # ("wheel@2/Wheel", ...). Treat them as one target (union of shapes).
        prefix_objs = self._prefix_objects(t)
        if prefix_objs:
            shape = self._compound_of([o.shape for o in prefix_objs])
            return _Target("object", t, shape, self._shape_center(shape))

        raise SpatialError(self._unknown_target_msg(t))

    def _resolve_face(self, face_id: str, prefix: str, idx: int) -> _Target:
        faces = self._faces()
        if prefix not in faces:
            raise SpatialError(
                f"unknown face id {face_id!r}: no object named {prefix!r}. "
                f"{self._available_objects_msg()}"
            )
        entries = faces[prefix]
        if idx < 0 or idx >= len(entries):
            raise SpatialError(
                f"face index {idx} out of range for {prefix!r} "
                f"(0..{len(entries) - 1}). Face ids are only valid until the next "
                f"rebuild; re-run query_faces."
            )
        desc, face = entries[idx]
        cyl = _cyl_axis_radius(face, desc["type"])
        return _Target("face", face_id, self._compound_of([face]), desc.get("center"), cyl)

    def _resolve_object(self, name: str):
        from solidifai_engine.render import _node_ids

        objs = self.s._objects or []
        keys = self._object_keys()
        for o, key in zip(objs, keys, strict=True):
            if name in (o.name, key):
                return (o, key)
        # Fall back to the collision-safe node id (matches model.json ids).
        node_ids = _node_ids(objs)
        for o, key, nid in zip(objs, keys, node_ids, strict=True):
            if name == nid:
                return (o, key)
        return None

    def _prefix_objects(self, name: str) -> list:
        """Objects placed under an occurrence prefix: name matches the leading
        path segment, e.g. ``wheel@2`` selects ``wheel@2/Wheel``."""
        objs = self.s._objects or []
        keys = self._object_keys()
        pref = name + "/"
        return [o for o, key in zip(objs, keys, strict=True) if key.startswith(pref)]

    def _keys_for_object_filter(self, name: str) -> list[str] | None:
        """Object keys a query_faces ``object`` filter selects: an exact key/name/
        node id, or every key under an occurrence prefix. ``None`` if nothing matches."""
        faces = self._faces()
        if name in faces:
            return [name]
        resolved = self._resolve_object(name)
        if resolved is not None:
            return [resolved[1]]
        keys = self._object_keys()
        pref = name + "/"
        matched = [k for k in keys if k.startswith(pref)]
        return matched or None

    # -- geometry helpers ---------------------------------------------------

    @staticmethod
    def _compound_of(faces):
        if not faces:
            return None
        from solidifai_engine.render import compound_of

        return compound_of(faces)

    @staticmethod
    def _faces_center(faces):
        if not faces:
            return None
        from solidifai_engine.render import compound_of

        try:
            bb = compound_of(faces).bounding_box()
            return _round3(
                ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
            )
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _shape_center(shape):
        try:
            bb = shape.bounding_box()
            return _round3(
                ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
            )
        except Exception:  # noqa: BLE001
            return None

    def _available_names(self) -> tuple[list[str], list[str], list[str]]:
        features = sorted(f.name for f in self.s._features)
        objects = self._object_keys()
        face_hint = [f"{k}:f0" for k in objects[:3]]
        return features, objects, face_hint

    def _available_objects_msg(self) -> str:
        objs = ", ".join(self._object_keys()) or "(none)"
        return f"available objects: {objs}"

    def _unknown_target_msg(self, t: str) -> str:
        features, objects, faces = self._available_names()
        feats = ", ".join(features) or "(none)"
        objs = ", ".join(objects) or "(none)"
        face_hint = ", ".join(faces) or "(run query_faces)"
        return (
            f"unknown target {t!r}. Features: {feats}. Objects: {objs}. "
            f"Face ids look like {face_hint} (from query_faces). Or pass an "
            f"[x, y, z] point."
        )

    # -- public API ---------------------------------------------------------

    def measure_between(self, a, b, mode: str = "min") -> dict:
        if mode not in ("min", "center", "axis"):
            return {"ok": False, "error": f"mode must be 'min', 'center', or 'axis'; got {mode!r}"}
        if not self.s._objects:
            return {"ok": False, "error": "no model -- run execute_script first"}
        try:
            ta = self._resolve(a)
            tb = self._resolve(b)
        except SpatialError as exc:
            return {"ok": False, "error": str(exc)}

        result: dict = {"ok": True, "a": ta.label, "b": tb.label, "mode": mode}

        min_d = self._min_distance(ta, tb)
        if min_d is not None:
            result["min_distance"] = round(min_d["distance"], 4)
            result["closest_points"] = {
                "a": _round3(min_d["p_a"]),
                "b": _round3(min_d["p_b"]),
            }
        else:
            result["min_distance"] = None
            result["closest_points"] = None

        if ta.center is not None and tb.center is not None:
            result["center_distance"] = round(_vlen(_sub(ta.center, tb.center)), 4)
        else:
            result["center_distance"] = None

        both_cyl = ta.cyl is not None and tb.cyl is not None
        if both_cyl:
            pos_a, dir_a, _ra = ta.cyl
            pos_b, dir_b, _rb = tb.cyl
            result["axis_distance"] = round(_line_line_distance(pos_a, dir_a, pos_b, dir_b), 4)
            result["axis_angle_deg"] = _axis_angle_deg(dir_a, dir_b)

        if mode == "axis" and not both_cyl:
            non_cyl = ta.label if ta.cyl is None else tb.label
            return {
                "ok": False,
                "error": f"axis mode needs two cylindrical targets; {non_cyl!r} is "
                f"not cylindrical (has no rotation axis). Use mode 'min' or 'center'.",
            }

        result["distance"] = {
            "min": result.get("min_distance"),
            "center": result.get("center_distance"),
            "axis": result.get("axis_distance"),
        }[mode]
        return result

    def _min_distance(self, ta: _Target, tb: _Target):
        """BRepExtrema min distance + closest-point pair between two targets. A
        literal point becomes a vertex. Returns ``None`` when a shape is missing."""
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.gp import gp_Pnt
        except Exception:  # noqa: BLE001
            return None

        def _occ(target: _Target):
            if target.kind == "point":
                p = target.center
                return BRepBuilderAPI_MakeVertex(gp_Pnt(p[0], p[1], p[2])).Vertex()
            if target.shape is None:
                return None
            return target.shape.wrapped

        wa, wb = _occ(ta), _occ(tb)
        if wa is None or wb is None:
            return None
        try:
            ext = BRepExtrema_DistShapeShape(wa, wb)
            if not ext.IsDone() or ext.NbSolution() < 1:
                return None
            pa = ext.PointOnShape1(1)
            pb = ext.PointOnShape2(1)
            return {
                "distance": ext.Value(),
                "p_a": (pa.X(), pa.Y(), pa.Z()),
                "p_b": (pb.X(), pb.Y(), pb.Z()),
            }
        except Exception:  # noqa: BLE001
            return None

    def query_faces(self, flt: dict | None = None) -> dict:
        if not self.s._objects:
            return {"ok": False, "error": "no model -- run execute_script first"}
        flt = flt or {}
        want_obj = flt.get("object")
        want_type = flt.get("type")
        want_axis = flt.get("axis")
        axis_tol = float(flt.get("axis_tol_deg", DEFAULT_AXIS_TOL_DEG))
        area_min = flt.get("area_min")
        area_max = flt.get("area_max")
        sort = flt.get("sort", "area_desc")
        limit = flt.get("limit", 20)

        if want_type is not None and want_type not in (
            "planar",
            "cylindrical",
            "conical",
            "spherical",
            "toroidal",
            "other",
        ):
            return {"ok": False, "error": f"unknown face type {want_type!r}"}

        axis_unit = None
        if want_axis is not None:
            if not self._is_point(want_axis):
                return {"ok": False, "error": "axis filter must be an [x, y, z] direction"}
            axis_unit = _unit((float(want_axis[0]), float(want_axis[1]), float(want_axis[2])))
            if axis_unit is None:
                return {"ok": False, "error": "axis filter direction must be non-zero"}

        faces = self._faces()
        allowed_keys: set[str] | None = None
        if want_obj is not None:
            object_keys = self._keys_for_object_filter(want_obj)
            if object_keys is None:
                return {
                    "ok": False,
                    "error": f"unknown object {want_obj!r}. {self._available_objects_msg()}",
                }
            allowed_keys = set(object_keys)

        hits: list[dict] = []
        for key, entries in faces.items():
            if allowed_keys is not None and key not in allowed_keys:
                continue
            for desc, _face in entries:
                if want_type is not None and desc["type"] != want_type:
                    continue
                area = desc.get("area")
                if area_min is not None and (area is None or area < area_min):
                    continue
                if area_max is not None and (area is None or area > area_max):
                    continue
                if axis_unit is not None and not self._axis_aligned(desc, axis_unit, axis_tol):
                    continue
                hits.append({k: v for k, v in desc.items() if not k.startswith("_")})

        reverse = sort != "area_asc"
        hits.sort(key=lambda d: (d.get("area") is None, d.get("area") or 0.0), reverse=reverse)
        total = len(hits)
        if isinstance(limit, int) and limit >= 0:
            hits = hits[:limit]
        return {
            "ok": True,
            "buildId": self.s.build_id,
            "count": len(hits),
            "total_matched": total,
            "note": "face ids are stable only until the next rebuild",
            "faces": hits,
        }

    @staticmethod
    def _axis_aligned(desc: dict, axis_unit, tol_deg: float) -> bool:
        v = desc.get("normal_or_axis")
        if not v:
            return False
        u = _unit((v[0], v[1], v[2]))
        if u is None:
            return False
        # A rotation axis is undirected (a cylinder's axis sign is arbitrary), so
        # match either orientation. A planar normal points OUT, so respect its
        # sign: an up-facing filter must not also catch the down-facing wall.
        c = _dot(u, axis_unit)
        if desc["type"] != "planar":
            c = abs(c)
        c = max(-1.0, min(1.0, c))
        return math.degrees(math.acos(c)) <= tol_deg

    def nearest_face(self, point) -> dict | None:
        """Descriptor of the model face whose surface is closest to ``point``
        (Z-up mm), or ``None``. Backs the feature_at face fallback."""
        if not point or len(point) != 3 or not self.s._objects:
            return None
        try:
            from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
            from OCP.BRepExtrema import BRepExtrema_DistShapeShape
            from OCP.gp import gp_Pnt
        except Exception:  # noqa: BLE001
            return None
        vertex = BRepBuilderAPI_MakeVertex(
            gp_Pnt(float(point[0]), float(point[1]), float(point[2]))
        ).Vertex()
        best = None
        best_d = float("inf")
        for entries in self._faces().values():
            for desc, face in entries:
                try:
                    ext = BRepExtrema_DistShapeShape(vertex, face.wrapped)
                    if not ext.IsDone() or ext.NbSolution() < 1:
                        continue
                    d = ext.Value()
                except Exception:  # noqa: BLE001
                    continue
                if d < best_d:
                    best_d = d
                    best = desc
        if best is None:
            return None
        out = {k: v for k, v in best.items() if not k.startswith("_")}
        out["distance"] = round(best_d, 4)
        return out

    def thickness_at(self, point, direction=None) -> dict:
        return dfm.thickness_at(self.s._objects or [], point, direction)
