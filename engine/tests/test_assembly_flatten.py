"""Flattened model.py export: an assembly is reduced to a single runnable
model.py that, executed in a plain single-model Session, shows the same parts as
the composed assembly (by name + count)."""

import os

from solidifai_engine.session import Session

SKEL_2FRAME = """
from solidifai import skeleton
from build123d import Location
PARAMS = {
    "body_w": {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0, "unit": "mm"},
    "body_h": {"value": 30.0, "min": 15.0, "max": 90.0, "step": 1.0, "unit": "mm"},
    "wall":   {"value": 2.4, "min": 1.2, "max": 5.0, "step": 0.2, "unit": "mm"},
}
def build(body_w, body_h, wall):
    s = skeleton()
    s.scalar("body_w", body_w)
    s.scalar("wall", wall)
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, body_h)))
    return s
"""

BASE_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
"""

LID_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], 3)
    show(p.part, name="Lid")
"""


def _mk(tmp_path) -> Session:
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def _flat_session(tmp_path):
    """A clean single-model session (root has no assembly.json) to run the flat code."""
    flat_root = tmp_path / "flat"
    flat_root.mkdir()
    return Session(
        str(flat_root / ".solidifai" / "artifacts"),
        model_path=str(flat_root / "model.py"),
    )


def test_flatten_emits_runnable_model(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    res = s.export_flat_model()
    assert res["ok"] is True
    code = res["code"]

    s2 = _flat_session(tmp_path)
    out = s2.execute_script(code)
    assert out["ok"] is True, out
    assert s2._is_assembly_mode() is False  # genuinely single-model
    names = {o["name"] for o in s2.get_model_info()["objects"]}
    assert {"base/Base", "lid/Lid"} <= names  # both parts, path-id names preserved


def test_flatten_reproduces_geometry(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    asm_bbox = s.get_model_info()["bbox"]["size"]

    s2 = _flat_session(tmp_path)
    s2.execute_script(s.export_flat_model()["code"])
    flat_bbox = s2.get_model_info()["bbox"]["size"]
    # The flattened model composes to the same overall envelope as the assembly.
    for a, b in zip(asm_bbox, flat_bbox, strict=True):
        assert abs(a - b) < 1e-3


def test_flatten_writes_file_when_requested(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    res = s.export_flat_model(write=True)
    assert res["ok"] is True
    assert os.path.exists(res["path"])
    with open(res["path"]) as f:
        assert f.read() == res["code"]


def test_flatten_requires_assembly(tmp_path):
    flat_root = tmp_path / "single"
    flat_root.mkdir()
    s = Session(
        str(flat_root / ".solidifai" / "artifacts"),
        model_path=str(flat_root / "model.py"),
    )
    res = s.export_flat_model()
    assert res["ok"] is False and "assembly" in res["error"].lower()


# -- published-geometry flatten (C1) ------------------------------------------

import json as _json

SKEL_PUBLISHED = """
from solidifai import skeleton
from build123d import Location, Rectangle
PARAMS = {"w": {"value": 40.0, "min": 10, "max": 120, "step": 1, "unit": "mm"},
          "d": {"value": 30.0, "min": 10, "max": 120, "step": 1, "unit": "mm"},
          "fit": {"value": 0.2, "min": 0.0, "max": 1.0, "step": 0.05, "unit": "mm"}}
def build(w, d, fit):
    s = skeleton()
    s.scalar("fit", fit)
    s.profile("seat", Rectangle(w, d))
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, 20)))
    return s
"""

BASE_SHAPE = """
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(inputs["seat"])
        extrude(amount=4)
    show(p.part, name="Base")
"""

LID_SHAPE = """
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude, offset
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(offset(inputs["seat"], amount=inputs["fit"]))
        extrude(amount=4)
    show(p.part, name="Lid")
"""


def _mk_published(tmp_path):
    """Create a published-geometry assembly workspace and return its Session."""
    root = tmp_path / "asm_pub"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s, root


def test_flatten_published_geometry(tmp_path):
    """C1: flatten must carry shape_inputs so the emitted model.py runs without KeyError."""
    s, root = _mk_published(tmp_path)
    # Build the assembly files directly (Session.set_part doesn't expose shape_inputs yet).
    skel_path = root / "skeleton.py"
    skel_path.write_text(SKEL_PUBLISHED, encoding="utf-8")
    (root / "parts").mkdir(exist_ok=True)
    (root / "parts" / "base.py").write_text(BASE_SHAPE, encoding="utf-8")
    (root / "parts" / "lid.py").write_text(LID_SHAPE, encoding="utf-8")
    (root / "assembly.json").write_text(
        _json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "base",
                        "kind": "part",
                        "source": "parts/base.py",
                        "attach": "base_frame",
                        "inputs": [],
                        "shape_inputs": ["seat"],
                    },
                    {
                        "id": "lid",
                        "kind": "part",
                        "source": "parts/lid.py",
                        "attach": "lid_frame",
                        "inputs": ["fit"],
                        "shape_inputs": ["seat"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    # Reload after writing files.
    s2 = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))

    res = s2.export_flat_model()
    assert res["ok"] is True, res
    code = res["code"]

    # Execute the emitted model.py in a fresh single-model session.
    flat_root = tmp_path / "flat_pub"
    flat_root.mkdir()
    s3 = Session(
        str(flat_root / ".solidifai" / "artifacts"), model_path=str(flat_root / "model.py")
    )
    out = s3.execute_script(code)
    assert out["ok"] is True, out
    names = {o["name"] for o in s3.get_model_info()["objects"]}
    assert {"base/Base", "lid/Lid"} <= names
