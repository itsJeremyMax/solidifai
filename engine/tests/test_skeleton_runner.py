from solidifai_engine.assembly import runner

ROOT_SKELETON = """
from solidifai import skeleton
from build123d import Location

PARAMS = {"body_w": {"value": 80.0, "min": 40, "max": 160, "step": 1, "unit": "mm"}}

def build(body_w):
    s = skeleton()
    s.scalar("body_w", body_w)
    s.frame("base_frame", Location((0, 0, 0)))
    return s
"""

SUB_SKELETON = """
from solidifai import skeleton
from build123d import Location

PARAMS = {"count": {"value": 2.0, "min": 1, "max": 8, "step": 1, "unit": ""}}

def build(parent, count):
    s = skeleton()
    pitch = parent["body_w"] / count
    s.scalar("pitch", pitch)
    return s
"""


def test_root_skeleton_runs_with_param_defaults(tmp_path):
    (tmp_path / "skeleton.py").write_text(ROOT_SKELETON, encoding="utf-8")
    res = runner.run_skeleton(str(tmp_path / "skeleton.py"), params={}, parent=None)
    assert res.scalars["body_w"] == 80.0
    assert "base_frame" in res.frames


def test_param_override(tmp_path):
    (tmp_path / "skeleton.py").write_text(ROOT_SKELETON, encoding="utf-8")
    res = runner.run_skeleton(str(tmp_path / "skeleton.py"), params={"body_w": 120.0}, parent=None)
    assert res.scalars["body_w"] == 120.0


def test_parent_inputs_injected_when_declared(tmp_path):
    (tmp_path / "skeleton.py").write_text(SUB_SKELETON, encoding="utf-8")
    res = runner.run_skeleton(str(tmp_path / "skeleton.py"), params={}, parent={"body_w": 80.0})
    assert res.scalars["pitch"] == 40.0
