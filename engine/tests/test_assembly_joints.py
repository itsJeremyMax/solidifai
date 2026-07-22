"""Joints/mates: a DECLARED-INTENT motion model (not a constraint solver).
skeleton.py declares joints with s.joint(...); they publish through the skeleton
contract (tree / get_assembly_tree), check_interfaces validates their frame +
between, and check_motion drives a joint through its range and reports collisions."""

import os

import pytest

from solidifai import skeleton
from solidifai.skeleton_api import SkeletonResult
from solidifai_engine.session import Session

# A revolute hinge: an arm child that swings about the origin toward a fixed post.
SKEL = """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("pivot", Location((0, 0, 0)))
    s.frame("post_at", Location((0, 20, 0)))
    s.joint("hinge", "revolute", frame="pivot", axis=[0, 0, 1],
            limits=[0, 120], between=["arm", "post"])
    return s
"""

ARM = """
from solidifai import show
from build123d import Box, Align
def build(inputs):
    show(Box(40, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), name="Arm")
"""

POST = """
from solidifai import show
from build123d import Box
def build(inputs):
    show(Box(12, 12, 30), name="Post")
"""


def _session(tmp_path):
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    s.set_skeleton(SKEL)
    s.set_part("arm", ARM, attach="pivot")
    s.set_part("post", POST, attach="post_at")
    return s, root


# -- declaration + validation (skeleton_api) ---------------------------------


def test_joint_records_fields_with_defaults():
    s = skeleton()
    rec = s.joint("j", "slider", frame="rail")
    assert rec["kind"] == "slider"
    assert rec["axis"] == [0.0, 0.0, 1.0]  # default +Z
    assert rec["limits"] is None and rec["between"] is None
    assert s.joints == [rec]


def test_joint_rejects_bad_kind():
    with pytest.raises(ValueError, match="kind"):
        skeleton().joint("j", "wobble", frame="f")


def test_joint_rejects_zero_axis_and_bad_limits():
    with pytest.raises(ValueError, match="non-zero"):
        skeleton().joint("j", "revolute", frame="f", axis=[0, 0, 0])
    with pytest.raises(ValueError, match="lo"):
        skeleton().joint("j", "slider", frame="f", limits=[10, 5])


def test_joint_rejects_bad_between():
    with pytest.raises(ValueError, match="between"):
        skeleton().joint("j", "revolute", frame="f", between=["only_one"])


def test_skeleton_result_has_joints_field():
    assert SkeletonResult().joints == []


# -- publish through the contract --------------------------------------------


def test_get_assembly_tree_exposes_joints(tmp_path):
    s, _root = _session(tmp_path)
    tree = s.get_assembly_tree()
    assert tree["ok"] is True
    joints = tree["tree"]["skeleton"]["joints"]
    assert len(joints) == 1
    j = joints[0]
    assert j["name"] == "hinge" and j["kind"] == "revolute"
    assert j["between"] == ["arm", "post"] and j["limits"] == [0, 120]


def test_begin_round_contract_exposes_joints(tmp_path):
    s, _root = _session(tmp_path)
    res = s.begin_round()
    assert res["ok"] is True
    assert any(j["name"] == "hinge" for j in res["skeleton"]["joints"])
    s.abort_round()


# -- check_interfaces validation ---------------------------------------------


def test_check_interfaces_flags_bad_joint_frame_and_between(tmp_path):
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    bad_skel = """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("pivot", Location((0, 0, 0)))
    s.joint("hinge", "revolute", frame="ghost_frame", between=["arm", "nobody"])
    return s
"""
    s.set_skeleton(bad_skel)
    s.set_part("arm", ARM, attach="pivot")
    rep = s.check_interfaces()
    assert rep["ok"] is True
    kinds = {(i["issue"], i["name"]) for i in rep["issues"]}
    assert ("missing_joint_frame", "ghost_frame") in kinds
    assert ("unknown_joint_between", "nobody") in kinds


def test_check_interfaces_clean_when_joint_valid(tmp_path):
    s, _root = _session(tmp_path)
    rep = s.check_interfaces()
    assert rep["ok"] is True
    joint_issues = [i for i in rep["issues"] if "joint" in i["issue"]]
    assert joint_issues == []


# -- check_motion joint mode --------------------------------------------------


def test_check_motion_drives_joint_and_finds_collision(tmp_path):
    s, _root = _session(tmp_path)
    # Sweeps the hinge's declared limits [0, 120]; the +X arm swings into the
    # +Y post and must collide somewhere in that range.
    rep = s.check_motion(joint="hinge", steps=13)
    assert rep["ok"] is True
    assert rep["joint"] == "hinge" and rep["moving"] == "arm"
    assert rep["range"] == [0.0, 120.0]  # taken from the joint's limits
    assert rep["collides"] is True
    assert rep["firstCollision"]["with"] == "post/Post"
    assert rep["clearThrough"] < rep["firstCollision"]["at"]


def test_check_motion_joint_respects_passed_range(tmp_path):
    s, _root = _session(tmp_path)
    # A small range keeps the arm clear of the post.
    rep = s.check_motion(joint="hinge", start=0, stop=15, steps=5)
    assert rep["ok"] is True
    assert rep["range"] == [0.0, 15.0]
    assert rep["collides"] is False


def test_check_motion_unknown_joint_errors(tmp_path):
    s, _root = _session(tmp_path)
    rep = s.check_motion(joint="nope")
    assert rep["ok"] is False and "not found" in rep["error"]


def test_check_motion_rigid_joint_is_noop(tmp_path):
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    rigid_skel = """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("pivot", Location((0, 0, 0)))
    s.frame("post_at", Location((0, 20, 0)))
    s.joint("weld", "rigid", frame="pivot", between=["arm", "post"])
    return s
"""
    s.set_skeleton(rigid_skel)
    s.set_part("arm", ARM, attach="pivot")
    s.set_part("post", POST, attach="post_at")
    rep = s.check_motion(joint="weld")
    assert rep["ok"] is True and rep["collides"] is False
    assert "rigid" in rep["note"]
    assert rep["verification"] == {
        "method": "static",
        "continuousProof": False,
        "samples": 0,
        "samplesRequested": 0,
        "samplesActual": 0,
        "spacing": None,
        "note": "No motion to verify for a rigid joint.",
    }


def test_check_motion_still_works_in_part_mode(tmp_path):
    """The pre-existing single-part call shape is unchanged by the joint addition."""
    s = Session(str(tmp_path))
    s.execute_script(
        "from build123d import Box, Pos, Align\n"
        "from solidifai import show\n"
        "show(Box(40, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), name='Arm')\n"
        "show(Pos(0, 20, 0) * Box(12, 12, 30), name='Post')\n"
    )
    rep = s.check_motion(
        "Arm",
        kind="revolute",
        axis_origin=[0, 0, 0],
        axis_dir=[0, 0, 1],
        start=0,
        stop=120,
        steps=13,
    )
    assert rep["ok"] is True and rep["collides"] is True
    assert rep["firstCollision"]["with"] == "Post"


def test_check_motion_joint_needs_between(tmp_path):
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    skel = """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("pivot", Location((0, 0, 0)))
    s.joint("hinge", "revolute", frame="pivot")
    return s
"""
    s.set_skeleton(skel)
    s.set_part("arm", ARM, attach="pivot")
    rep = s.check_motion(joint="hinge")
    assert rep["ok"] is False and "between" in rep["error"]
