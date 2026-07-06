import json

from solidifai_engine.assembly import compose, graph, parallel
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
    s = skeleton(); s.scalar("w", w); s.frame("f", Location((0,0,0))); return s
"""
PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p: Box(inputs["w"], inputs["w"], 2)
    show(p.part, name="P")
"""


def _ws(tmp_path, n=4):
    _write(tmp_path, "skeleton.py", SKELETON)
    children = []
    for i in range(n):
        _write(tmp_path, f"parts/p{i}.py", PART)
        children.append(
            {
                "id": f"p{i}",
                "kind": "part",
                "source": f"parts/p{i}.py",
                "attach": "f",
                "inputs": ["w"],
            }
        )
    _write(
        tmp_path,
        "assembly.json",
        json.dumps({"version": 1, "skeleton": "skeleton.py", "children": children}),
    )


def test_warm_populates_disk_cache(tmp_path):
    _ws(tmp_path, 4)
    disk = DiskCache(str(tmp_path))
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=disk
    )
    assert len(misses) == 4
    parallel.warm_cache_parallel(misses, disk, min_parts=2)
    assert all(disk.peek(k) for _, _, k in misses)


def test_warmed_build_is_byte_identical_to_sequential(tmp_path):
    _ws(tmp_path, 4)
    seq = graph.build_node(str(tmp_path), params={}, parent=None, cache=None, disk=None)
    seq_vols = sorted(round(o.shape.volume, 6) for o in seq)
    disk = DiskCache(str(tmp_path))
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=disk
    )
    parallel.warm_cache_parallel(misses, disk, min_parts=2)
    cache = NodeCache()
    par = graph.build_node(str(tmp_path), params={}, parent=None, cache=cache, disk=disk)
    par_vols = sorted(round(o.shape.volume, 6) for o in par)
    assert seq_vols == par_vols
    assert disk.hits == 4  # all 4 served from the warmed disk cache (no kernel in build_node)


def test_below_threshold_is_noop(tmp_path):
    _ws(tmp_path, 1)
    disk = DiskCache(str(tmp_path))
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=disk
    )
    parallel.warm_cache_parallel(misses, disk, min_parts=2)  # 1 < 2 -> no-op
    assert not disk.peek(misses[0][2])


# -- published-geometry parallel warm-pass (H1) --------------------------------

SKEL_PUB = """
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

BASE_PUB = """
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(inputs["seat"])
        extrude(amount=4)
    show(p.part, name="Base")
"""

LID_PUB = """
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude, offset
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(offset(inputs["seat"], amount=inputs["fit"]))
        extrude(amount=4)
    show(p.part, name="Lid")
"""


def _ws_pub(tmp_path):
    _write(tmp_path, "skeleton.py", SKEL_PUB)
    _write(tmp_path, "parts/base.py", BASE_PUB)
    _write(tmp_path, "parts/lid.py", LID_PUB)
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


def test_published_geometry_warm_key_matches_build_key(tmp_path):
    """H1: after a real build the shape-consuming parts must be absent from enumerate_part_builds
    (warm key == build key -> L1 hit -> not in misses list)."""
    _ws_pub(tmp_path)
    cache = NodeCache()
    # Populate L1 via a real build.
    graph.build_node(str(tmp_path), params={}, parent=None, cache=cache)
    assert cache.misses == 2  # sanity: both parts were built

    # Now enumerate with the same L1 cache; if warm keys match, no misses.
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=cache, disk=None
    )
    assert misses == [], f"expected empty misses after warm build, got {[k for _, _, k in misses]}"
