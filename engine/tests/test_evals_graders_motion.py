"""Motion grader: derived axes + clear_to / collides_within expectations."""

from evals.graders import grade_motion, open_grading_session
from solidifai_engine.session import Session

# Two leaves with a 3 mm seam gap about x=0: rotating leaf_b about the derived
# Y seam axis swings it up and clear through 80 degrees.
HINGE_OK = """
from build123d import Box, Pos
from solidifai import show

show(Pos(-11.5, 0, 0) * Box(20, 40, 3), name="leaf_a")
show(Pos(11.5, 0, 0) * Box(20, 40, 3), name="leaf_b")
"""

# Leaves touching at x=0: rotating leaf_b immediately digs into leaf_a.
HINGE_BLOCKED = """
from build123d import Box, Pos
from solidifai import show

show(Pos(-10, 0, 0) * Box(20, 40, 3), name="leaf_a")
show(Pos(10, 0, 0) * Box(20, 40, 3), name="leaf_b")
"""

GEARS_APART = """
from build123d import Box, Cylinder, Pos
from solidifai import show

show(Box(100, 60, 4), name="base")
show(Pos(-25, 0, 10) * Cylinder(20, 6), name="gear_a")
show(Pos(30, 0, 10) * Cylinder(15, 6), name="gear_b")
"""

CLEAR_SPEC = {
    "motion": {
        "kind": "revolute",
        "part": {"name_contains": "leaf_b"},
        "axis": "pair_seam",
        "start": 5,
        "stop": 80,
        "steps": 16,
        "expect": "clear_to",
        "threshold_deg": 70,
    }
}

ENGAGE_SPEC = {
    "motion": {
        "kind": "revolute",
        "part": {"name_contains": "leaf_b"},
        "axis": "pair_seam",
        "start": 5,
        "stop": 80,
        "steps": 16,
        "expect": "collides_within",
        "threshold_deg": 20,
    }
}


def make_workspace(base, code):
    ws = base / "ws"
    ws.mkdir(parents=True)
    s = Session(str(base / "art"), model_path=str(ws / "model.py"))
    res = s.execute_script(code)
    assert res.get("ok"), res
    return str(ws)


def _motion(ws, spec):
    gs = open_grading_session(ws)
    try:
        return grade_motion(gs, spec)
    finally:
        gs.close()


def test_clear_swing_passes(tmp_path):
    res = _motion(make_workspace(tmp_path, HINGE_OK), CLEAR_SPEC)
    assert res.passed is True, res.detail
    assert res.data["axis_dir"] == [0.0, 1.0, 0.0]  # seam runs along Y


def test_blocked_swing_fails(tmp_path):
    res = _motion(make_workspace(tmp_path, HINGE_BLOCKED), CLEAR_SPEC)
    assert res.passed is False
    assert "collides" in res.detail


def test_collides_within_proves_engagement(tmp_path):
    # Blocked pair "engages" immediately -> collides_within passes...
    assert _motion(make_workspace(tmp_path / "a", HINGE_BLOCKED), ENGAGE_SPEC).passed is True
    # ...a clear pair never engages -> collides_within fails.
    assert _motion(make_workspace(tmp_path / "b", HINGE_OK), ENGAGE_SPEC).passed is False


def test_self_spin_of_a_free_disc_is_clear(tmp_path):
    spec = {
        "motion": {
            "kind": "revolute",
            "part": {"name_contains": "gear_a"},
            "axis": "self_spin",
            "start": 0,
            "stop": 360,
            "steps": 8,
            "expect": "clear_to",
            "threshold_deg": 360,
        }
    }
    res = _motion(make_workspace(tmp_path, GEARS_APART), spec)
    assert res.passed is True, res.detail


def test_motion_needs_two_parts(tmp_path):
    one = """
from build123d import Box
from solidifai import show
show(Box(10, 10, 10), name="solo")
"""
    res = _motion(make_workspace(tmp_path, one), CLEAR_SPEC)
    assert res.passed is False
    assert "two parts" in res.detail
