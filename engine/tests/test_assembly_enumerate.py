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


def test_identical_parts_share_one_content_key(tmp_path):
    # a.py and b.py are byte-identical with identical inputs: content-addressing
    # (path dropped from the key) collapses them to ONE key, so caching it skips
    # BOTH -- this is the instancing dedup (20 identical brackets build once).
    _ws(tmp_path)
    cache = NodeCache()
    misses_all = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=None
    )
    keys = {m[2] for m in misses_all}
    assert len(keys) == 1  # identical source+inputs -> single shared key
    cache.put(next(iter(keys)), ["dummy"])
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=cache, disk=None
    )
    assert misses == []  # the shared key is cached -> neither identical part rebuilds


def test_distinct_parts_have_distinct_keys(tmp_path):
    # A genuinely different part source yields a different key even at the same
    # inputs, so caching one does not mask the other.
    _ws(tmp_path)
    (tmp_path / "parts" / "b.py").write_text(PART.replace('name="P"', 'name="Q"'), encoding="utf-8")
    cache = NodeCache()
    misses_all = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=None, disk=None
    )
    assert len({m[2] for m in misses_all}) == 2
    pa = next(m for m in misses_all if "a.py" in m[0])
    cache.put(pa[2], ["dummy"])
    misses = parallel.enumerate_part_builds(
        str(tmp_path), params={}, parent=None, cache=cache, disk=None
    )
    assert len(misses) == 1 and "b.py" in misses[0][0]
