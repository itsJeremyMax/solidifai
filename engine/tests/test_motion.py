"""Range-of-motion collision sweep over shown parts."""

import pytest

from solidifai_engine.exploration import Exploration
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
    assert rep["verification"] == {
        "method": "sampled",
        "continuousProof": False,
        "samples": 5,
        "samplesRequested": 5,
        "samplesActual": 5,
        "spacing": {"value": 3.75, "unit": "deg"},
        "note": "Sampled clearance is not a continuous proof.",
    }


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


def test_motion_reversed_range_preserves_signed_spacing(tmp_path):
    rep = _sess(tmp_path).check_motion(
        "Arm",
        kind="revolute",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=15,
        stop=0,
        steps=4,
    )

    assert rep["range"] == [15.0, 0.0]
    assert rep["verification"] == {
        "method": "sampled",
        "continuousProof": False,
        "samples": 4,
        "samplesRequested": 4,
        "samplesActual": 4,
        "spacing": {"value": -5.0, "unit": "deg"},
        "note": "Sampled clearance is not a continuous proof.",
    }


def test_motion_zero_span_reports_zero_spacing(tmp_path):
    rep = _sess(tmp_path).check_motion(
        "Arm",
        kind="prismatic",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=5,
        stop=5,
        steps=3,
    )

    assert rep["range"] == [5.0, 5.0]
    assert rep["verification"] == {
        "method": "sampled",
        "continuousProof": False,
        "samples": 3,
        "samplesRequested": 3,
        "samplesActual": 3,
        "spacing": {"value": 0.0, "unit": "mm"},
        "note": "Sampled clearance is not a continuous proof.",
    }


def test_motion_clamps_sample_count_and_reports_requested_vs_actual(tmp_path):
    rep = _sess(tmp_path).check_motion(
        "Arm",
        kind="revolute",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=0,
        stop=15,
        steps=1,
    )

    assert rep["verification"] == {
        "method": "sampled",
        "continuousProof": False,
        "samples": 2,
        "samplesRequested": 1,
        "samplesActual": 2,
        "spacing": {"value": 15.0, "unit": "deg"},
        "note": "Sampled clearance is not a continuous proof.",
    }


def test_motion_failed_poses_are_inconclusive_not_verified_clear():
    def fail_transform(_at):
        raise ValueError("degenerate pose")

    rep = Exploration(None)._sweep(fail_transform, [], 0, 10, 3, unit="deg")

    assert rep["ok"] is False
    assert rep["code"] == "motion_pose_failed"
    assert rep["clearThrough"] is None
    assert rep["verification"]["samplesActual"] == 0
    assert rep["verification"]["failedSamples"] == 3
    assert all(step["collides"] is None for step in rep["steps"])


def test_motion_unknown_part(tmp_path):
    assert _sess(tmp_path).check_motion("Nope")["ok"] is False


def test_motion_unknown_part_mode_kind_is_rejected(tmp_path):
    rep = _sess(tmp_path).check_motion(
        "Arm",
        kind="wobble",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=0,
        stop=90,
        steps=4,
    )
    assert rep == {
        "ok": False,
        "code": "unsupported_motion_kind",
        "error": "unsupported motion kind 'wobble'; expected revolute or prismatic",
        "kind": "wobble",
        "supportedKinds": ["revolute", "prismatic"],
    }


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


@pytest.mark.parametrize("joint_kind", ["cylindrical", "planar", "ball"])
def test_motion_joint_rejects_multi_axis_joint_kinds(tmp_path, joint_kind):
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    s.set_skeleton(
        f"""
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("pivot", Location((0, 0, 0)))
    s.frame("post_at", Location((0, 20, 0)))
    s.joint("roll", "{joint_kind}", frame="pivot", limits=[0, 120], between=["arm", "post"])
    return s
"""
    )
    s.set_part(
        "arm",
        """
from solidifai import show
from build123d import Box, Align
def build(inputs):
    show(Box(40, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), name="Arm")
""",
        attach="pivot",
    )
    s.set_part(
        "post",
        """
from solidifai import show
from build123d import Box
def build(inputs):
    show(Box(12, 12, 30), name="Post")
""",
        attach="post_at",
    )

    rep = s.check_motion(joint="roll", steps=13)

    assert rep == {
        "ok": False,
        "code": "unsupported_joint_motion",
        "error": f"joint 'roll' kind '{joint_kind}' is declared but not verifiable by check_motion",
        "joint": "roll",
        "kind": joint_kind,
        "verifiedJoints": ["rigid", "revolute", "slider"],
    }
