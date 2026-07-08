import json

from build123d import Box, export_brep

from solidifai_engine.assembly import graph
from solidifai_engine.assembly.cache import NodeCache, part_key
from solidifai_engine.assembly.diskcache import DiskCache


def test_part_key_stable_for_same_inputs():
    k1 = part_key("def build(i): ...", {"body_w": 80.0, "wall": 2.4})
    k2 = part_key("def build(i): ...", {"wall": 2.4, "body_w": 80.0})  # order-independent
    assert k1 == k2


def test_part_key_differs_on_source_or_inputs():
    base = part_key("SRC-A", {"w": 1.0})
    assert part_key("SRC-B", {"w": 1.0}) != base  # source changed
    assert part_key("SRC-A", {"w": 2.0}) != base  # input value changed
    assert part_key("SRC-A", {"w": 1.0, "x": 0.0}) != base  # input set changed


def test_cache_get_put_and_counters():
    c = NodeCache()
    assert c.get("k") is None
    assert c.misses == 1 and c.hits == 0
    c.put("k", ["obj"])
    assert c.get("k") == ["obj"]
    assert c.hits == 1


def test_key_includes_assets():
    from solidifai_engine.assembly.cache import part_key

    base = part_key("SRC", {"w": 1.0}, path="parts/a.py", assets={})
    assert part_key("SRC", {"w": 1.0}, path="parts/a.py", assets={"a.brep": "h1"}) != base
    assert part_key("SRC", {"w": 1.0}, path="parts/a.py", assets={"a.brep": "h2"}) != part_key(
        "SRC", {"w": 1.0}, path="parts/a.py", assets={"a.brep": "h1"}
    )


def test_key_non_numeric_scalar_does_not_crash():
    from solidifai_engine.assembly.cache import part_key

    k = part_key("SRC", {"mode": "fast", "w": 2.0})  # string scalar tolerated
    assert isinstance(k, str)


def test_asset_fingerprint_changes_with_content(tmp_path):
    from solidifai_engine.assembly.cache import asset_fingerprint

    f = tmp_path / "a.brep"
    f.write_text("one", encoding="utf-8")
    fp1 = asset_fingerprint([str(f)])
    f.write_text("two", encoding="utf-8")
    fp2 = asset_fingerprint([str(f)])
    assert fp1 != fp2


def test_cache_revalidates_asset_fingerprint(tmp_path):
    # L1 entry carrying an asset fingerprint is a MISS once that asset's contents
    # change, and a HIT while they stay the same.
    from solidifai_engine.assembly.cache import asset_fingerprint

    f = tmp_path / "a.brep"
    f.write_text("one", encoding="utf-8")
    c = NodeCache()
    c.put("k", ["obj"], asset_fingerprint([str(f)]))
    assert c.get("k") == ["obj"]  # unchanged asset -> hit (no needless rebuild)
    assert c.hits == 1 and c.misses == 0
    f.write_text("two", encoding="utf-8")
    assert c.get("k") is None  # edited asset -> treated as a miss
    assert c.misses == 1


SKELETON = """
from solidifai import skeleton
from build123d import Location
PARAMS = {}
def build():
    s = skeleton(); s.frame("f", Location((0,0,0))); return s
"""
PART = """
from solidifai import show, import_cad
def build(inputs):
    show(import_cad("assets/fixture.brep"), name="Imported")
"""


def _ws(tmp_path):
    (tmp_path / "parts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "skeleton.py").write_text(SKELETON, encoding="utf-8")
    (tmp_path / "parts/a.py").write_text(PART, encoding="utf-8")
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    export_brep(Box(10, 10, 10), str(tmp_path / "assets" / "fixture.brep"))
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {"id": "a", "kind": "part", "source": "parts/a.py", "attach": "f", "inputs": []}
                ],
            }
        ),
        encoding="utf-8",
    )


def test_warm_l1_rebuilds_after_asset_edit(tmp_path):
    # A WARM L1 cache reused across an asset edit must not serve stale geometry.
    # (The disk-cache asset test hands each build a FRESH NodeCache, which masks
    # this: only a reused L1 exposes the stale-hit path.)
    _ws(tmp_path)
    warm = NodeCache()
    disk = DiskCache(str(tmp_path))
    objs1 = graph.build_node(str(tmp_path), params={}, parent=None, cache=warm, disk=disk)
    v1 = objs1[0].shape.volume  # ~1000 (10mm cube)
    export_brep(Box(20, 20, 20), str(tmp_path / "assets" / "fixture.brep"))
    objs2 = graph.build_node(str(tmp_path), params={}, parent=None, cache=warm, disk=disk)
    v2 = objs2[0].shape.volume  # ~8000 if revalidated; ~1000 if STALE L1 hit
    assert abs(v1 - 1000) < 1.0
    assert v2 > 2000
