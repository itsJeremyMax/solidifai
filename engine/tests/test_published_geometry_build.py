import json

from solidifai_engine.assembly import graph
from solidifai_engine.assembly.cache import NodeCache


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


SKELETON = """
from solidifai import skeleton
from build123d import Location, Rectangle
PARAMS = {"w": {"value": 40.0, "min": 10, "max": 120, "step": 1, "unit": "mm"},
          "d": {"value": 30.0, "min": 10, "max": 120, "step": 1, "unit": "mm"},
          "fit": {"value": 0.2, "min": 0.0, "max": 1.0, "step": 0.05, "unit": "mm"}}
def build(w, d, fit):
    s = skeleton()
    s.scalar("fit", fit)
    s.profile("seat", Rectangle(w, d))         # the shared interface, defined ONCE
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, 20)))
    return s
"""
BASE = """
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(inputs["seat"])
        extrude(amount=4)
    show(p.part, name="Base")
"""
LID = """
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude, offset
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(offset(inputs["seat"], amount=inputs["fit"]))   # lip = seat grown to fit over base
        extrude(amount=4)
    show(p.part, name="Lid")
"""


def _ws(tmp_path):
    _write(tmp_path, "skeleton.py", SKELETON)
    _write(tmp_path, "parts/base.py", BASE)
    _write(tmp_path, "parts/lid.py", LID)
    _write(
        tmp_path,
        "assembly.json",
        json.dumps(
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
    )


def test_published_profile_drives_both_parts(tmp_path):
    _ws(tmp_path)
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    assert sorted(o.name for o in objs) == ["base/Base", "lid/Lid"]
    bb = {o.name: o.shape.bounding_box() for o in objs}
    # lid lip = seat offset out by fit (0.2) per side -> +0.4 in X and Y vs base
    assert round(bb["lid/Lid"].size.X - bb["base/Base"].size.X, 3) == 0.4
    assert round(bb["lid/Lid"].size.Y - bb["base/Base"].size.Y, 3) == 0.4


def test_same_params_reuses_consumers(tmp_path):
    _ws(tmp_path)
    cache = NodeCache()
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache)
    m0 = cache.misses
    assert m0 == 2  # base + lid built once
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache)
    assert cache.misses == m0  # profile recomputed identically -> both cache hits


def test_profile_change_rebuilds_consumers(tmp_path):
    _ws(tmp_path)
    cache = NodeCache()
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache)
    m0 = cache.misses
    graph.build_node(str(tmp_path), params={"w": 60.0}, parent=None, cache=cache)
    assert cache.misses == m0 + 2  # changed seat profile invalidates both consumers


from solidifai_engine.assembly import tree as tree_mod


def test_tree_lists_published_shapes_and_consumers(tmp_path):
    _ws(tmp_path)
    t = tree_mod.assembly_tree(str(tmp_path))
    assert t["skeleton"]["shapes"] == ["seat"]
    by_id = {c["id"]: c for c in t["children"]}
    assert by_id["base"]["shape_inputs"] == ["seat"]
    assert by_id["lid"]["shape_inputs"] == ["seat"]
