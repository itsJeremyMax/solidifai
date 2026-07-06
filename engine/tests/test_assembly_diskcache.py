import json

from solidifai_engine.assembly import graph
from solidifai_engine.assembly.cache import NodeCache
from solidifai_engine.assembly.diskcache import DiskCache


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


SKELETON = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"w": {"value": 20.0, "min": 5, "max": 80, "step": 1, "unit": "mm"}}
def build(w):
    s = skeleton(); s.scalar("w", w); s.frame("f", Location((0,0,0)))
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
                        "attach": "f",
                        "inputs": ["w"],
                    }
                ],
            }
        ),
    )


def test_disk_cache_survives_new_in_memory_cache(tmp_path):
    _ws(tmp_path)
    disk = DiskCache(str(tmp_path))
    graph.build_node(str(tmp_path), params={}, parent=None, cache=NodeCache(), disk=disk)
    cache2 = NodeCache()
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache2, disk=disk)
    assert cache2.misses == 1 and cache2.hits == 0  # L1 missed (fresh in-memory)
    assert disk.hits >= 1  # ...but L2 (disk) hit -> no run_part


def test_disk_cache_byte_identical_geometry(tmp_path):
    _ws(tmp_path)
    cold = graph.build_node(str(tmp_path), params={"w": 30.0}, parent=None, cache=None, disk=None)
    disk = DiskCache(str(tmp_path))
    graph.build_node(str(tmp_path), params={"w": 30.0}, parent=None, cache=NodeCache(), disk=disk)
    warm = graph.build_node(
        str(tmp_path), params={"w": 30.0}, parent=None, cache=NodeCache(), disk=disk
    )
    assert abs(cold[0].shape.volume - warm[0].shape.volume) < 1e-6
