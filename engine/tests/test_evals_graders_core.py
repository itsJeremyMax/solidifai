"""Core graders against fixture models built in-test through the engine."""

import os

import pytest

from evals import graders
from evals.graders import grade_workspace, open_grading_session
from solidifai_engine.session import Session

GOOD_WASHER = """
from build123d import Cylinder
from solidifai import show

washer = Cylinder(8, 1.6) - Cylinder(4.2, 4)
show(washer, name="washer")
"""

# Deliberately bad: a critically thin wall (0.4 mm < FDM 0.8 minimum), an
# interpenetrating pair, and a part with disconnected floating geometry.
BAD_MODEL = """
from build123d import Box, Compound, Pos
from solidifai import show

show(Box(20, 20, 0.4), name="thin_plate")
show(Pos(5, 0, 0) * Box(10, 10, 0.4), name="overlapper")
show(Compound(children=[Box(5, 5, 5), Pos(40, 0, 0) * Box(5, 5, 5)]), name="broken_lump")
"""

SPEC = {
    "schema": 1,
    "graders": ["requirements", "dfm", "watertight", "interference"],
    "requirements": [
        {"id": "watertight", "quantity": "watertight", "op": "==", "bound": True},
        {"id": "printable", "quantity": "dfm_critical", "op": "<=", "bound": 0},
        {"id": "no-overlap", "quantity": "overlaps", "op": "<=", "bound": 0},
    ],
}


def make_workspace(base, code):
    ws = base / "ws"
    ws.mkdir()
    (ws / "model.py").write_text(code, encoding="utf-8")
    return str(ws)


@pytest.fixture(scope="module")
def good_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("good"), GOOD_WASHER)


@pytest.fixture(scope="module")
def bad_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("bad"), BAD_MODEL)


def _grade(ws, spec=SPEC):
    gs = open_grading_session(ws)
    try:
        return grade_workspace(gs, spec)
    finally:
        gs.close()


def test_good_model_passes_core_graders(good_ws):
    out = _grade(good_ws)
    by = {g["name"]: g for g in out["graders"]}
    assert by["watertight"]["passed"] is True
    assert by["dfm"]["passed"] is True
    assert by["interference"]["passed"] is True
    assert by["requirements"]["passed"] is True
    assert out["programmatic_score"] == 1.0


def test_bad_model_fails_the_right_graders(bad_ws):
    out = _grade(bad_ws)
    by = {g["name"]: g for g in out["graders"]}
    assert by["dfm"]["passed"] is False  # 0.4 mm wall is critical
    assert by["interference"]["passed"] is False  # overlap + floating lump
    assert by["requirements"]["passed"] is False
    assert 0.0 < out["programmatic_score"] < 1.0


def test_empty_workspace_scores_zero(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    out = _grade(str(ws))
    assert out["programmatic_score"] == 0.0
    assert all(g["detail"] == "no model produced" for g in out["graders"])


def test_watertight_grader_fails_on_nonmanifold_report(good_ws, monkeypatch):
    gs = open_grading_session(good_ws)
    try:
        monkeypatch.setattr(gs.session, "get_model_info", lambda: {"manifold": False})
        res = graders.grade_watertight(gs, SPEC)
    finally:
        gs.close()
    assert res.passed is False and res.score == 0.0


def test_stress_grader_flags_sharp_reentrant_corner(tmp_path):
    bracket = """
from build123d import Box, Pos
from solidifai import show
show(Box(40, 20, 4) + Pos(-18, 0, 12) * Box(4, 20, 20), name="l_bracket")
"""
    ws = make_workspace(tmp_path, bracket)
    gs = open_grading_session(ws)
    try:
        res = graders.grade_stress(gs, {"graders": ["stress"]})
    finally:
        gs.close()
    assert res.passed is False  # unfilleted internal corner concentrates stress
    assert "warning" in res.detail


def test_unknown_grader_is_reported_not_crashed(good_ws):
    out = _grade(good_ws, {"schema": 1, "graders": ["watertight", "made_up"]})
    by = {g["name"]: g for g in out["graders"]}
    assert by["made_up"]["passed"] is None
    assert "unknown grader" in by["made_up"]["detail"]


def test_zero_requirements_is_vacuous_not_a_failure(good_ws):
    out = _grade(good_ws, {"schema": 1, "graders": ["requirements"], "requirements": []})
    by = {g["name"]: g for g in out["graders"]}
    assert by["requirements"]["passed"] is None
    assert by["requirements"]["score"] == 1.0
    assert by["requirements"]["detail"] == "no requirements"


def test_semantic_grader_checks_geometry_not_brief_claims(good_ws):
    out = _grade(
        good_ws,
        {
            "schema": 2,
            "graders": ["semantic"],
            "semantic_requirements": [
                {"id": "one-part", "kind": "part_count", "count": 1},
                {"id": "named", "kind": "part_name", "name": "washer"},
                {
                    "id": "bore",
                    "kind": "hole_pattern",
                    "count": 1,
                    "diameter_mm": 8.4,
                    "tolerance_mm": 0.2,
                },
            ],
        },
    )
    semantic = out["graders"][0]
    assert semantic["passed"] is True
    assert all(check["pass"] for check in semantic["data"]["checks"])


def test_semantic_cavity_pattern_requires_distinct_geometric_slots(tmp_path):
    workspace = make_workspace(
        tmp_path,
        """
from build123d import Box
from solidifai import show

show(Box(80, 24, 24) - Box(72, 16, 20), name="battery_box")
""",
    )
    spec = {
        "schema": 2,
        "graders": ["semantic"],
        "semantic_requirements": [
            {
                "id": "four-cell-slots",
                "kind": "cavity_pattern",
                "size_mm": [18, 18, 18],
                "centers_mm": [[-27, 0, 0], [-9, 0, 0], [9, 0, 0], [27, 0, 0]],
                "tolerance_mm": 0.2,
            }
        ],
    }
    result = _grade(workspace, spec)["graders"][0]
    assert result["passed"] is False
    assert result["data"], result["detail"]
    assert result["data"]["checks"][0]["measured"]["separators"] == 0


def test_semantic_cavity_pattern_supports_distinct_region_sizes(tmp_path):
    workspace = make_workspace(
        tmp_path,
        """
from build123d import Box, Pos
from solidifai import show

organizer = Box(104, 44, 42)
organizer -= Pos(-32, 0, 5) * Box(20, 20, 30)
organizer -= Pos(0, 0, 0) * Box(14, 34, 26)
organizer -= Pos(30, 0, 11) * Box(28, 28, 8)
show(organizer, name="organizer")
""",
    )
    spec = {
        "schema": 2,
        "graders": ["semantic"],
        "semantic_requirements": [
            {
                "id": "desk-regions",
                "kind": "cavity_pattern",
                "size_mm": [[18, 18, 28], [12, 30, 24], [26, 26, 6]],
                "centers_mm": [[-32, 0, 5], [0, 0, 0], [30, 0, 11]],
                "tolerance_mm": 0.2,
            }
        ],
    }
    result = _grade(workspace, spec)["graders"][0]
    assert result["passed"] is True
    assert result["data"]["checks"][0]["measured"] == {"slots": 3, "separators": 2}


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

bracket = Box(6, 46, 52) + Pos(16, 0, 17) * Box(32, 46, 6)
bracket -= Pos(0, -20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
bracket -= Pos(0, 20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
show(bracket, name="bracket")
""",
            True,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

plate = Box(6, 46, 52)
plate -= Pos(0, -20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
plate -= Pos(0, 20, 0) * Cylinder(2.75, 10, rotation=(0, 90, 0))
show(plate, name="bracket")
""",
            False,
        ),
    ],
)
def test_semantic_l_bracket_requires_two_load_bearing_legs(tmp_path, code, expected):
    result = _grade(
        make_workspace(tmp_path, code),
        {
            "schema": 2,
            "graders": ["semantic"],
            "semantic_requirements": [
                {
                    "id": "load-bracket",
                    "kind": "l_bracket",
                    "name": "bracket",
                    "mount_axis": "x",
                    "span_axis": "y",
                    "rise_axis": "z",
                    "min_mount_thickness_mm": 5,
                    "min_span_mm": 40,
                    "min_rise_mm": 45,
                    "min_projection_mm": 20,
                    "tolerance_mm": 0.5,
                }
            ],
        },
    )["graders"][0]
    assert result["passed"] is expected


def test_constructor_failure_cleans_up_temp_artifacts_dir(tmp_path, monkeypatch):
    import tempfile

    made = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        made.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)

    import solidifai_engine.session as session_mod

    def boom(*args, **kwargs):
        raise RuntimeError("engine startup failed")

    monkeypatch.setattr(session_mod, "Session", boom)

    with pytest.raises(RuntimeError, match="engine startup failed"):
        open_grading_session(str(tmp_path))
    assert made, "expected GradingSession to create an artifacts tmpdir"
    assert not any(os.path.exists(p) for p in made), "artifacts tmpdir leaked"


@pytest.mark.parametrize(
    ("code", "requirement", "expected"),
    [
        (
            """
from build123d import Box, Cylinder, Pos, Rot
from solidifai import show

gear = Cylinder(20, 6)
for i in range(20):
    gear += Rot(0, 0, i * 18) * Pos(20, 0, 0) * Box(4, 3, 6)
show(gear, name="gear")
""",
            {
                "id": "gear",
                "kind": "radial_gear",
                "name": "gear",
                "tooth_count": 20,
                "module_mm": 2,
                "module_tolerance_mm": 0.3,
            },
            True,
        ),
        (
            """
from build123d import Cylinder
from solidifai import show
show(Cylinder(22, 6), name="gear")
""",
            {
                "id": "gear",
                "kind": "radial_gear",
                "name": "gear",
                "tooth_count": 20,
                "module_mm": 2,
                "module_tolerance_mm": 0.3,
            },
            False,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

mount = Box(36, 20, 4)
mount += Pos(0, -6, 7) * Box(18, 4, 12) + Pos(0, 6, 7) * Box(18, 4, 12)
mount -= Pos(0, 0, 7) * Cylinder(2.6, 30, rotation=(90, 0, 0))
show(mount, name="gopro_mount")
""",
            {
                "id": "mount",
                "kind": "gopro_two_prong",
                "name": "gopro_mount",
                "prong_thickness_mm": 4,
                "prong_gap_mm": 8,
                "pin_hole_diameter_mm": 5.2,
                "tolerance_mm": 0.35,
            },
            True,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

mount = Box(36, 20, 4) + Pos(0, 0, 7) * Box(18, 16, 12)
mount -= Pos(0, 0, 7) * Cylinder(2.6, 30, rotation=(90, 0, 0))
show(mount, name="gopro_mount")
""",
            {
                "id": "mount",
                "kind": "gopro_two_prong",
                "name": "gopro_mount",
                "prong_thickness_mm": 4,
                "prong_gap_mm": 8,
                "pin_hole_diameter_mm": 5.2,
                "tolerance_mm": 0.35,
            },
            False,
        ),
    ],
)
def test_topology_semantics_reject_deceptive_geometry(tmp_path, code, requirement, expected):
    workspace = make_workspace(tmp_path, code)
    result = _grade(
        workspace,
        {"schema": 2, "graders": ["semantic"], "semantic_requirements": [requirement]},
    )["graders"][0]
    assert result["passed"] is expected


def test_schema_rejects_incomplete_topology_requirement():
    from evals.run import validate_spec

    problems = validate_spec(
        {
            "schema": 2,
            "graders": ["semantic"],
            "semantic_requirements": [{"id": "gear", "kind": "radial_gear", "name": "gear"}],
        }
    )
    assert problems == ["semantic requirement 'gear' needs tooth_count and module geometry"]


@pytest.mark.parametrize(
    ("code", "requirement", "expected"),
    [
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

leaf_a = Pos(-10, 0, 0) * Box(20, 60, 3)
leaf_b = Pos(10, 0, 0) * Box(20, 60, 3)
for y in (-20, 10): leaf_a += Pos(0, y, 0) * Cylinder(3, 12, rotation=(90, 0, 0))
for y in (-5, 20): leaf_b += Pos(0, y, 0) * Cylinder(3, 10, rotation=(90, 0, 0))
show(leaf_a, name="leaf_a")
show(leaf_b, name="leaf_b")
show(Cylinder(2, 64, rotation=(90, 0, 0)), name="pin")
""",
            {
                "id": "hinge",
                "kind": "hinge_topology",
                "leaves": ["leaf_a", "leaf_b"],
                "pin": "pin",
                "knuckles_per_leaf": 2,
                "tolerance_mm": 0.5,
            },
            True,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show
show(Pos(-10, 0, 0) * Box(20, 60, 3), name="leaf_a")
show(Pos(10, 0, 0) * Box(20, 60, 3), name="leaf_b")
show(Cylinder(2, 64, rotation=(90, 0, 0)), name="pin")
""",
            {
                "id": "hinge",
                "kind": "hinge_topology",
                "leaves": ["leaf_a", "leaf_b"],
                "pin": "pin",
                "knuckles_per_leaf": 2,
                "tolerance_mm": 0.5,
            },
            False,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

hook = Box(4, 40, 60) + Pos(16, 0, -16) * Box(32, 20, 6) + Pos(28, 0, -5) * Box(8, 20, 28)
hook -= Pos(0, -12, 15) * Cylinder(2.5, 10, rotation=(0, 90, 0))
hook -= Pos(0, 12, 15) * Cylinder(2.5, 10, rotation=(0, 90, 0))
show(hook, name="hook")
""",
            {
                "id": "hook",
                "kind": "wall_hook",
                "name": "hook",
                "mount_hole_diameter_mm": 5,
                "mount_hole_count": 2,
                "min_projection_mm": 25,
                "min_retaining_rise_mm": 15,
                "tolerance_mm": 0.5,
            },
            True,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

hook = Box(4, 40, 60)
hook -= Pos(0, -12, 15) * Cylinder(2.5, 10, rotation=(0, 90, 0))
hook -= Pos(0, 12, 15) * Cylinder(2.5, 10, rotation=(0, 90, 0))
show(hook, name="hook")
""",
            {
                "id": "hook",
                "kind": "wall_hook",
                "name": "hook",
                "mount_hole_diameter_mm": 5,
                "mount_hole_count": 2,
                "min_projection_mm": 25,
                "min_retaining_rise_mm": 15,
                "tolerance_mm": 0.5,
            },
            False,
        ),
    ],
)
def test_assembly_topology_semantics_reject_deceptive_geometry(
    tmp_path, code, requirement, expected
):
    result = _grade(
        make_workspace(tmp_path, code),
        {"schema": 2, "graders": ["semantic"], "semantic_requirements": [requirement]},
    )["graders"][0]
    assert result["passed"] is expected


@pytest.mark.parametrize(
    ("code", "requirement", "expected"),
    [
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

case = Box(100, 70, 30) - Pos(43, 0, 0) * Box(24, 28, 14)
for x in (-20, -7, 7, 20): case -= Pos(x, 0, 0) * Cylinder(2, 40)
show(case, name="case")
show(Box(85, 56, 18), name="board", role="reference")
""",
            {
                "id": "ports",
                "kind": "reference_port_pattern",
                "reference": "board",
                "axis": "x",
                "side": "max",
                "openings": [{"offset_mm": [0, 0], "size_mm": [20, 24, 10]}],
                "tolerance_mm": 0.2,
            },
            True,
        ),
        (
            """
from build123d import Box
from solidifai import show
show(Box(100, 70, 30), name="case")
show(Box(85, 56, 18), name="board", role="reference")
""",
            {
                "id": "ports",
                "kind": "reference_port_pattern",
                "reference": "board",
                "axis": "x",
                "side": "max",
                "openings": [{"offset_mm": [0, 0], "size_mm": [20, 24, 10]}],
                "tolerance_mm": 0.2,
            },
            False,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

case = Box(100, 70, 30)
for x in (-20, -7, 7, 20): case -= Pos(x, 0, 0) * Cylinder(2, 40)
show(case, name="case")
""",
            {
                "id": "vents",
                "kind": "vent_open_area",
                "min_open_area_mm2": 45,
                "axis": "z",
                "min_count": 4,
                "tolerance_mm": 0.2,
            },
            True,
        ),
        (
            """
from build123d import Box, Cylinder, Pos
from solidifai import show

case = Box(100, 70, 30) - Pos(0, 0, 0) * Cylinder(2, 40)
show(case, name="case")
""",
            {
                "id": "vents",
                "kind": "vent_open_area",
                "min_open_area_mm2": 45,
                "axis": "z",
                "min_count": 4,
                "tolerance_mm": 0.2,
            },
            False,
        ),
    ],
)
def test_enclosure_semantics_require_reference_access_and_vent_area(
    tmp_path, code, requirement, expected
):
    result = _grade(
        make_workspace(tmp_path, code),
        {"schema": 2, "graders": ["semantic"], "semantic_requirements": [requirement]},
    )["graders"][0]
    assert result["passed"] is expected
