import json

from solidifai_engine.assembly import graph


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


SKELETON = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"body_w": {"value": 80.0, "min": 40, "max": 160, "step": 1, "unit": "mm"},
          "wall": {"value": 2.4, "min": 1, "max": 5, "step": 0.2, "unit": "mm"}}
def build(body_w, wall):
    s = skeleton()
    s.scalar("body_w", body_w); s.scalar("wall", wall)
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, 40)))
    return s
"""
BASE = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
"""
LID = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Lid")
"""


def test_flat_assembly_composes_two_parts(tmp_path):
    _write(tmp_path, "skeleton.py", SKELETON)
    _write(tmp_path, "parts/base.py", BASE)
    _write(tmp_path, "parts/lid.py", LID)
    _write(
        tmp_path,
        "assembly.json",
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "base",
                        "kind": "part",
                        "source": "parts/base.py",
                        "attach": "base_frame",
                        "inputs": ["body_w", "wall"],
                    },
                    {
                        "id": "lid",
                        "kind": "part",
                        "source": "parts/lid.py",
                        "attach": "lid_frame",
                        "inputs": ["body_w", "wall"],
                    },
                ],
            }
        ),
    )
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    names = sorted(o.name for o in objs)
    assert names == ["base/Base", "lid/Lid"]
    # lid was attached at z=40, base at z=0 -> their centroids differ in Z
    by = {o.name: o.shape.bounding_box().center().Z for o in objs}
    assert by["lid/Lid"] - by["base/Base"] == 40.0


def test_nested_subassembly(tmp_path):
    _write(tmp_path, "skeleton.py", SKELETON)
    _write(tmp_path, "parts/base.py", BASE)
    _write(
        tmp_path,
        "assembly.json",
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "base",
                        "kind": "part",
                        "source": "parts/base.py",
                        "attach": "base_frame",
                        "inputs": ["body_w", "wall"],
                    },
                    {
                        "id": "hinge",
                        "kind": "assembly",
                        "source": "hinge/",
                        "attach": "lid_frame",
                        "inputs": ["body_w"],
                    },
                ],
            }
        ),
    )
    # sub-assembly: own skeleton driven by parent body_w, one part
    _write(
        tmp_path,
        "hinge/skeleton.py",
        """
from solidifai import skeleton
from build123d import Location
PARAMS = {}
def build(parent):
    s = skeleton()
    s.scalar("pin_d", parent["body_w"] / 10)
    s.frame("pin_frame", Location((0, 0, 5)))   # non-zero internal offset
    return s
""",
    )
    _write(
        tmp_path,
        "hinge/parts/pin.py",
        """
from solidifai import show
from build123d import BuildPart, Cylinder
def build(inputs):
    with BuildPart() as p:
        Cylinder(radius=inputs["pin_d"] / 2, height=20)
    show(p.part, name="Pin")
""",
    )
    _write(
        tmp_path,
        "hinge/assembly.json",
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "pin",
                        "kind": "part",
                        "source": "parts/pin.py",
                        "attach": "pin_frame",
                        "inputs": ["pin_d"],
                    },
                ],
            }
        ),
    )
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    names = sorted(o.name for o in objs)
    assert names == ["base/Base", "hinge/pin/Pin"]
    # The pin sits at its internal frame (z=5); the hinge is attached at the
    # parent's lid_frame (z=40). Correct composition -> z=45. If place() used
    # located() (replace) instead of moved() (compose), this would be z=40.
    pin = next(o for o in objs if o.name == "hinge/pin/Pin")
    assert round(pin.shape.bounding_box().center().Z) == 45
