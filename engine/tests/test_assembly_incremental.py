import json

from solidifai_engine.assembly import graph
from solidifai_engine.assembly.cache import NodeCache


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


SKELETON = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"w": {"value": 20.0, "min": 5, "max": 80, "step": 1, "unit": "mm"},
          "gap": {"value": 10.0, "min": 1, "max": 40, "step": 1, "unit": "mm"}}
def build(w, gap):
    s = skeleton(); s.scalar("w", w)
    s.frame("a_frame", Location((0, 0, 0)))
    s.frame("b_frame", Location((0, 0, gap)))   # gap only moves b, no part consumes it
    return s
"""
PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["w"], inputs["w"], 2)
    show(p.part, name="P")
"""


def _ws(tmp_path):
    _write(tmp_path, "skeleton.py", SKELETON)
    _write(tmp_path, "parts/a.py", PART)
    # b is a DISTINCT part (different show() name, identical geometry) so a and b
    # get separate content keys -- this suite tests per-part incremental caching,
    # not the identical-part instancing dedup (covered in test_assembly_enumerate).
    _write(tmp_path, "parts/b.py", PART.replace('name="P"', 'name="Q"'))
    _write(
        tmp_path,
        "assembly.json",
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "a",
                        "kind": "part",
                        "source": "parts/a.py",
                        "attach": "a_frame",
                        "inputs": ["w"],
                    },
                    {
                        "id": "b",
                        "kind": "part",
                        "source": "parts/b.py",
                        "attach": "b_frame",
                        "inputs": ["w"],
                    },
                ],
            }
        ),
    )


def test_no_cache_behaves_as_before(tmp_path):
    _ws(tmp_path)
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    assert sorted(o.name for o in objs) == ["a/P", "b/Q"]


def test_second_build_same_params_all_hits(tmp_path):
    _ws(tmp_path)
    cache = NodeCache()
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache)
    misses_after_first = cache.misses
    assert misses_after_first == 2  # both parts built once
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache)
    assert cache.misses == misses_after_first  # no new misses: both reused
    assert cache.hits >= 2


def test_frame_only_change_is_all_hits(tmp_path):
    # changing 'gap' moves b_frame but no part consumes gap -> zero rebuilds
    _ws(tmp_path)
    cache = NodeCache()
    graph.build_node(str(tmp_path), params={"gap": 10.0}, parent=None, cache=cache)
    m0 = cache.misses
    objs = graph.build_node(str(tmp_path), params={"gap": 30.0}, parent=None, cache=cache)
    assert cache.misses == m0  # no rebuilds
    by = {o.name: o.shape.bounding_box().center().Z for o in objs}
    assert by["b/Q"] - by["a/P"] == 30.0  # b moved to the new frame (recompose)


def test_input_change_rebuilds_only_affected(tmp_path):
    _ws(tmp_path)
    cache = NodeCache()
    graph.build_node(str(tmp_path), params={"w": 20.0}, parent=None, cache=cache)
    m0 = cache.misses
    graph.build_node(str(tmp_path), params={"w": 40.0}, parent=None, cache=cache)
    assert cache.misses == m0 + 2
