"""Dim-match grader: pose-invariant bbox, hole detection, center distances."""

import pytest

from evals.graders import grade_dim_match, open_grading_session
from solidifai_engine.session import Session

WASHER = """
from build123d import Cylinder
from solidifai import show

washer = Cylinder(8, 1.6) - Cylinder(4.2, 4)
show(washer, name="washer")
"""

PLATE_TWO_HOLES = """
from build123d import Box, Cylinder, Pos
from solidifai import show

plate = (
    Box(60, 20, 4)
    - Pos(-20, 0, 0) * Cylinder(2.75, 10)
    - Pos(20, 0, 0) * Cylinder(2.75, 10)
)
show(plate, name="plate")
"""

GEARS = """
from build123d import Box, Cylinder, Pos
from solidifai import show

show(Box(100, 60, 4), name="base")
show(Pos(-25, 0, 10) * Cylinder(20, 6), name="gear_a")
show(Pos(25, 0, 10) * Cylinder(15, 6), name="gear_b")
"""


def make_workspace(base, code):
    ws = base / "ws"
    ws.mkdir()
    s = Session(str(base / "art"), model_path=str(ws / "model.py"))
    res = s.execute_script(code)
    assert res.get("ok"), res
    return str(ws)


@pytest.fixture(scope="module")
def washer_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("washer"), WASHER)


@pytest.fixture(scope="module")
def plate_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("plate"), PLATE_TWO_HOLES)


@pytest.fixture(scope="module")
def gears_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("gears"), GEARS)


def _dim(ws, entries):
    gs = open_grading_session(ws)
    try:
        return grade_dim_match(gs, {"expected_dims": entries})
    finally:
        gs.close()


def test_bbox_sorted_and_hole_match(washer_ws):
    res = _dim(
        washer_ws,
        [
            {"kind": "bbox_sorted", "axis": "min", "expected": 1.6, "tol": 0.1},
            {"kind": "bbox_sorted", "axis": "mid", "expected": 16.0, "tol": 0.2},
            {"kind": "bbox_sorted", "axis": "max", "expected": 16.0, "tol": 0.2},
            {"kind": "hole", "expected": 8.4, "tol": 0.2},
        ],
    )
    assert res.passed is True and res.score == 1.0


def test_dim_mismatch_fails_with_detail(washer_ws):
    res = _dim(washer_ws, [{"kind": "bbox_sorted", "axis": "max", "expected": 20.0, "tol": 0.2}])
    assert res.passed is False and res.score == 0.0
    assert "20.0" in res.detail


def test_mass_dim(washer_ws):
    # PLA washer: pi/4*(16^2-8.4^2)*1.6 mm^3 * 1.24 g/cm^3 ~= 0.29 g
    res = _dim(washer_ws, [{"kind": "mass", "expected": 0.29, "tol": 0.1}])
    assert res.passed is True


def test_hole_count_and_center_distance(plate_ws):
    res = _dim(
        plate_ws,
        [
            {"kind": "hole", "expected": 5.5, "tol": 0.2, "count": 2},
            {
                "kind": "center_distance",
                "between": "holes",
                "diameter": 5.5,
                "diameter_tol": 0.2,
                "expected": 40.0,
                "tol": 0.5,
            },
        ],
    )
    assert res.passed is True, res.detail


def test_part_axis_center_distance(gears_ws):
    res = _dim(
        gears_ws,
        [
            {
                "kind": "center_distance",
                "between": "parts",
                "name_contains": "gear",
                "expected": 50.0,
                "tol": 0.5,
            }
        ],
    )
    assert res.passed is True, res.detail


def test_part_without_inertia_is_clean_miss(gears_ws, monkeypatch):
    # A degenerate/zero-volume part measures with inertia=None; the
    # center-distance check must report a miss, not crash the grader.
    gs = open_grading_session(gears_ws)
    try:
        payload = gs.session.measure()
        for p in payload["parts"]:
            if p.get("partName") == "gear_b":
                p["inertia"] = None
        monkeypatch.setattr(gs.session, "measure", lambda: payload)
        res = grade_dim_match(
            gs,
            {
                "expected_dims": [
                    {
                        "kind": "center_distance",
                        "between": "parts",
                        "name_contains": "gear",
                        "expected": 50.0,
                        "tol": 0.5,
                    }
                ]
            },
        )
    finally:
        gs.close()
    assert res.passed is False
    assert res.data["checks"][0]["measured"] is None


def test_missing_measurement_fails_cleanly(washer_ws):
    res = _dim(
        washer_ws,
        [
            {
                "kind": "center_distance",
                "between": "holes",
                "diameter": 30.0,
                "expected": 10.0,
                "tol": 0.5,
            }
        ],
    )
    assert res.passed is False
    assert res.data["checks"][0]["measured"] is None
