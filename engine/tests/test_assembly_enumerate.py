import json

from solidifai_engine.assembly import parallel
from solidifai_engine.assembly.cache import NodeCache, part_key
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


def _ws(tmp_path):
    _write(tmp_path, "skeleton.py", SKELETON)
    _write(tmp_path, "parts/a.py", PART)
    _write(tmp_path, "parts/b.py", PART)
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
                    },
                    {
                        "id": "b",
                        "kind": "part",
                        "source": "parts/b.py",
                        "attach": "f",
                        "inputs": ["w"],
                    },
                ],
            }
        ),
    )


def test_enumerate_lists_uncached_parts(tmp_path):
    _ws(tmp_path)
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=None
    )
    assert len(misses) == 2
    for part_path, inputs, key in misses:
        assert part_path.endswith(".py") and isinstance(inputs, dict) and isinstance(key, str)
    assert {round(m[1]["w"], 1) for m in misses} == {20.0}


def test_enumerate_skips_cached_parts(tmp_path):
    _ws(tmp_path)
    cache = NodeCache()
    misses_all = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=None
    )
    pa = next(m for m in misses_all if "a.py" in m[0])
    cache.put(pa[2], ["dummy"])
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=cache, disk=None
    )
    assert len(misses) == 1 and "b.py" in misses[0][0]
