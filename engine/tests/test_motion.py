"""Range-of-motion collision sweep over shown parts."""

from solidifai_engine.session import Session

MOTION_SCRIPT = """
from build123d import Box, Pos
from solidifai import show
# A long arm along +X pivoting at the origin, and a post it swings into at +Y.
show(Box(40, 6, 6, align=None), name="Arm")
show(Pos(0, 20, 0) * Box(12, 12, 30), name="Post")
"""


def _sess(tmp_path):
    s = Session(str(tmp_path))
    s.execute_script(MOTION_SCRIPT)
    return s


def test_motion_revolute_collides(tmp_path):
    s = _sess(tmp_path)
    rep = s.check_motion(
        "Arm",
        kind="revolute",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=0,
        stop=120,
        steps=13,
    )
    assert rep["ok"] is True
    assert rep["collides"] is True
    assert rep["firstCollision"]["with"] == "Post"
    # Swinging the +X arm toward +Y, it reaches the post somewhere past ~45 deg.
    assert 30 <= rep["firstCollision"]["at"] <= 120


def test_motion_clear_small_range(tmp_path):
    s = _sess(tmp_path)
    rep = s.check_motion(
        "Arm",
        kind="revolute",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=0,
        stop=15,
        steps=5,
    )
    assert rep["collides"] is False
    assert rep["firstCollision"] is None


def test_motion_clear_through_is_last_clear_sample(tmp_path):
    # clearThrough must report the last collision-free position, not the first
    # colliding one (off-by-one would overstate safe travel).
    s = _sess(tmp_path)
    rep = s.check_motion(
        "Arm",
        kind="revolute",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=0,
        stop=120,
        steps=13,
    )
    assert rep["collides"] is True
    assert rep["clearThrough"] < rep["firstCollision"]["at"]


def test_motion_unknown_part(tmp_path):
    assert _sess(tmp_path).check_motion("Nope")["ok"] is False


def test_motion_single_part_errors(tmp_path):
    s = Session(str(tmp_path))
    s.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10,10,10),name='Solo')\n"
    )
    assert s.check_motion("Solo")["ok"] is False


def test_motion_zero_axis_dir_errors_cleanly(tmp_path):
    # A zero-length axis_dir must return a clean bad-input envelope, not raise.
    s = _sess(tmp_path)
    for kind in ("revolute", "prismatic"):
        rep = s.check_motion(
            "Arm",
            kind=kind,
            axis_origin=[0, 0, 0],
            axis_dir=[0, 0, 0],
            start=0,
            stop=90,
            steps=6,
        )
        assert rep["ok"] is False
        assert "axis_dir" in rep["error"]
