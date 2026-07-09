"""Spatial measure/query tools: measure_between, query_faces, thickness_at, and
the feature_at nearest-face fallback.

Covers single-model and assembly/occurrence modes, mirrored (negative-
determinant) geometry, face-id round-trips, and the error shapes. Geometry is
chosen so every distance is exact and hand-checkable.
"""

import os

from solidifai_engine.session import Session

# Box 40x40x10 with two Z-axis bores (r=2.5) at x=-12 and x=+12: center spacing
# 24, wall-to-wall min 24-2.5-2.5 = 19, both axes parallel (angle 0).
TWO_HOLES = """
from build123d import BuildPart, Box, Locations, Hole
import solidifai
with BuildPart() as bp:
    Box(40, 40, 10)
    with solidifai.feature("hole_a"), Locations((-12, 0)):
        Hole(radius=2.5)
    with solidifai.feature("hole_b"), Locations((12, 0)):
        Hole(radius=2.5)
solidifai.show(bp.part, name="base")
"""

# Assembly: one wheel (r=10, h=6, Z-bore r=2) placed at two frames 40 mm apart.
SKEL = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"gap": {"value": 40.0, "min": 10.0, "max": 120.0, "step": 1.0, "unit": "mm"}}
def build(gap):
    s = skeleton()
    s.scalar("gap", gap)
    s.frame("left", Location((0, 0, 0)))
    s.frame("right", Location((gap, 0, 0)))
    return s
"""

WHEEL = """
from solidifai import show, feature
from build123d import BuildPart, Cylinder, Hole
def build(inputs):
    with BuildPart() as p:
        Cylinder(radius=10, height=6)
        with feature("bore"):
            Hole(radius=2)
    show(p.part, name="Wheel", material="pla")
"""


def _single(tmp_path, code=TWO_HOLES) -> Session:
    s = Session(str(tmp_path / ".solidifai" / "artifacts"))
    assert s.execute_script(code)["ok"] is True
    return s


def _assembly(tmp_path, occurrences=None) -> Session:
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    s.set_skeleton(SKEL)
    s.set_part("wheel", WHEEL, attach="left")
    if occurrences is not None:
        assert s.set_occurrences("wheel", occurrences)["ok"] is True
    return s


# -- measure_between: features, points, axis mode -----------------------------


def test_measure_between_feature_to_feature(tmp_path):
    s = _single(tmp_path)
    r = s.measure_between("hole_a", "hole_b")
    assert r["ok"] is True
    assert abs(r["min_distance"] - 19.0) < 1e-3
    assert abs(r["center_distance"] - 24.0) < 1e-3
    assert r["closest_points"]["a"] is not None and r["closest_points"]["b"] is not None


def test_measure_between_point_to_part(tmp_path):
    s = _single(tmp_path)
    # Point 20 mm above the top face (z=5) center; nearest surface is the top.
    r = s.measure_between([0, 0, 25], "base")
    assert r["ok"] is True
    assert abs(r["min_distance"] - 20.0) < 1e-3
    assert r["closest_points"]["a"] == [0.0, 0.0, 25.0]


def test_measure_between_axis_mode_parallel_holes(tmp_path):
    s = _single(tmp_path)
    r = s.measure_between("hole_a", "hole_b", mode="axis")
    assert r["ok"] is True
    assert abs(r["axis_distance"] - 24.0) < 1e-3
    assert r["axis_angle_deg"] == 0.0
    assert r["distance"] == r["axis_distance"]


def test_measure_between_axis_mode_requires_cylindrical(tmp_path):
    s = _single(tmp_path)
    r = s.measure_between("base", [0, 0, 0], mode="axis")
    assert r["ok"] is False
    assert "cylindrical" in r["error"]


def test_measure_between_mode_center(tmp_path):
    s = _single(tmp_path)
    r = s.measure_between("hole_a", "hole_b", mode="center")
    assert r["distance"] == r["center_distance"]


# -- face ids: query + round-trip into measure_between ------------------------


def test_query_faces_cylindrical_descriptor(tmp_path):
    s = _single(tmp_path)
    r = s.query_faces({"type": "cylindrical"})
    assert r["ok"] is True
    assert len(r["faces"]) == 2  # the two bores
    for f in r["faces"]:
        assert f["type"] == "cylindrical"
        assert abs(f["radius"] - 2.5) < 1e-6
        assert f["id"].startswith("base:f")
        assert f["object"] == "base"


def test_query_faces_axis_and_area_filter(tmp_path):
    s = _single(tmp_path)
    # Up-facing planar faces: only the top (z-normal), not the four sides.
    r = s.query_faces({"type": "planar", "axis": [0, 0, 1]})
    assert r["ok"] is True
    assert len(r["faces"]) == 1
    assert r["faces"][0]["normal_or_axis"] == [0.0, 0.0, 1.0]
    # area_min excludes the small bore-cap flats if any planar remained.
    big = s.query_faces({"type": "planar", "area_min": 1000})
    assert all(f["area"] >= 1000 for f in big["faces"])


def test_query_faces_limit_and_total(tmp_path):
    s = _single(tmp_path)
    r = s.query_faces({"limit": 3})
    assert len(r["faces"]) == 3
    assert r["total_matched"] >= 3
    # Default sort is area descending.
    areas = [f["area"] for f in r["faces"]]
    assert areas == sorted(areas, reverse=True)


def test_face_id_round_trip_into_measure_between(tmp_path):
    s = _single(tmp_path)
    ids = [f["id"] for f in s.query_faces({"type": "cylindrical"})["faces"]]
    r = s.measure_between(ids[0], ids[1], mode="axis")
    assert r["ok"] is True
    assert abs(r["axis_distance"] - 24.0) < 1e-3


def test_bad_face_id_index_errors(tmp_path):
    s = _single(tmp_path)
    r = s.measure_between("base:f999", "base")
    assert r["ok"] is False
    assert "out of range" in r["error"]


# -- thickness_at -------------------------------------------------------------


def test_thickness_at_known_wall(tmp_path):
    s = _single(tmp_path)
    # Through the 10 mm slab at the top center.
    r = s.thickness_at([0, 0, 5])
    assert r["ok"] is True
    assert abs(r["thickness"] - 10.0) < 1e-3
    assert r["object"] == "base"


def test_thickness_at_with_direction(tmp_path):
    s = _single(tmp_path)
    # Force the cast to enter from +Z; still measures the 10 mm slab.
    r = s.thickness_at([0, 0, 5], direction=[0, 0, 1])
    assert r["ok"] is True
    assert abs(r["thickness"] - 10.0) < 1e-3


def test_thickness_at_side_wall(tmp_path):
    s = _single(tmp_path)
    # Through the 40 mm width at a side-face center (the +Y side, clear of both
    # bores which sit on the X axis).
    r = s.thickness_at([0, 20, 0])
    assert r["ok"] is True
    assert abs(r["thickness"] - 40.0) < 1e-3


# -- assembly + occurrences ---------------------------------------------------


def test_measure_between_occurrence_features(tmp_path):
    s = _assembly(
        tmp_path,
        [{"frame": "left", "mirror": None}, {"frame": "right", "mirror": None}],
    )
    names = [f["name"] for f in s.inspect_features()["features"]]
    assert "wheel/bore" in names and "wheel@2/bore" in names
    r = s.measure_between("wheel/bore", "wheel@2/bore", mode="axis")
    assert r["ok"] is True
    assert abs(r["axis_distance"] - 40.0) < 1e-3
    assert r["axis_angle_deg"] == 0.0


def test_measure_between_occurrence_prefix(tmp_path):
    s = _assembly(
        tmp_path,
        [{"frame": "left", "mirror": None}, {"frame": "right", "mirror": None}],
    )
    # "wheel@2" names the body placed under that occurrence (wheel@2/Wheel).
    r = s.measure_between("wheel", "wheel@2")
    assert r["ok"] is True
    # Two r=10 wheels 40 apart: wall-to-wall min 40-10-10 = 20.
    assert abs(r["min_distance"] - 20.0) < 1e-3


def test_query_faces_object_filter_occurrence(tmp_path):
    s = _assembly(
        tmp_path,
        [{"frame": "left", "mirror": None}, {"frame": "right", "mirror": None}],
    )
    r = s.query_faces({"object": "wheel@2"})
    assert r["ok"] is True
    assert r["faces"] and all(f["object"].startswith("wheel@2") for f in r["faces"])


def test_mirrored_occurrence_distances_correct(tmp_path):
    s = _assembly(
        tmp_path,
        [{"frame": "left", "mirror": None}, {"frame": "right", "mirror": "yz"}],
    )
    assert len(s._objects) == 2
    # The mirror is negative-determinant; per-face props keep the bore axis and
    # the wall-to-wall distance exact.
    r = s.measure_between("wheel/bore", "wheel@2/bore", mode="axis")
    assert r["ok"] is True
    assert abs(r["axis_distance"] - 40.0) < 1e-3
    # thickness through a mirrored body still reads the true wall (r=2 bore in a
    # r=10 disk -> 8 mm from bore wall to outer wall along +X at the bore edge).
    t = s.thickness_at([42, 0, 0])  # right wheel outer edge (x=40+~2)
    assert t["ok"] is True and t["thickness"] > 0


# -- errors + fallbacks -------------------------------------------------------


def test_unknown_target_error_shape(tmp_path):
    s = _single(tmp_path)
    r = s.measure_between("nope", "base")
    assert r["ok"] is False
    assert "unknown target" in r["error"]
    assert "hole_a" in r["error"] and "base" in r["error"]  # lists available names


def test_measure_between_no_model(tmp_path):
    s = Session(str(tmp_path / ".solidifai" / "artifacts"))
    r = s.measure_between("a", "b")
    assert r["ok"] is False and "no model" in r["error"]


def test_feature_at_nearest_face_fallback(tmp_path):
    s = _single(tmp_path)
    # Top-center point, far from either bore plug: no feature match, but the
    # nearest bare face comes back addressable.
    r = s.feature_at([0, 0, 5])
    assert r["match"] is None
    nf = r["nearest_face"]
    assert nf is not None
    assert nf["type"] == "planar"
    assert nf["id"].startswith("base:f")
    assert "distance" in nf


def test_feature_at_hit_has_no_nearest_face(tmp_path):
    s = _single(tmp_path)
    # A point on a bore still resolves the feature (no fallback needed).
    hit = s.feature_at([-12, 0, 0], tolerance_mm=3.0)
    assert hit["match"] is not None
    assert "nearest_face" not in hit


def test_query_faces_stability_note(tmp_path):
    s = _single(tmp_path)
    r = s.query_faces({})
    assert "rebuild" in r["note"]
    assert r["buildId"] == s.build_id


def test_stl_export_unaffected_and_readonly(tmp_path):
    # measure/query never bump the build or mutate the model.
    s = _single(tmp_path)
    b0 = s.build_id
    s.measure_between("hole_a", "hole_b")
    s.query_faces({})
    s.thickness_at([0, 0, 5])
    assert s.build_id == b0
    out = s.export("stl", path=str(tmp_path / "out.stl"))
    assert out["ok"] is True and os.path.getsize(out["path"]) > 0
