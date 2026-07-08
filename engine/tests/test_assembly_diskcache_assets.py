import json

from build123d import Box, export_brep

from solidifai_engine.assembly import graph
from solidifai_engine.assembly.cache import NodeCache
from solidifai_engine.assembly.diskcache import DiskCache


def _write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


SKELETON = """
from solidifai import skeleton
from build123d import Location
PARAMS = {}
def build():
    s = skeleton(); s.frame("f", Location((0,0,0))); return s
"""
# a part that imports an external asset and shows it
PART = """
from solidifai import show, import_cad
def build(inputs):
    show(import_cad("assets/fixture.brep"), name="Imported")
"""


def _ws(tmp_path):
    _write(tmp_path / "skeleton.py", SKELETON)
    _write(tmp_path / "parts/a.py", PART)
    (tmp_path / "assets").mkdir(parents=True, exist_ok=True)
    export_brep(Box(10, 10, 10), str(tmp_path / "assets" / "fixture.brep"))
    _write(
        tmp_path / "assembly.json",
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {"id": "a", "kind": "part", "source": "parts/a.py", "attach": "f", "inputs": []}
                ],
            }
        ),
    )


def test_editing_an_asset_invalidates_disk_cache(tmp_path):
    _ws(tmp_path)
    disk = DiskCache(str(tmp_path))
    objs1 = graph.build_node(str(tmp_path), params={}, parent=None, cache=NodeCache(), disk=disk)
    v1 = objs1[0].shape.volume  # ~1000 (10mm cube)
    # edit the asset to a bigger cube
    export_brep(Box(20, 20, 20), str(tmp_path / "assets" / "fixture.brep"))
    objs2 = graph.build_node(str(tmp_path), params={}, parent=None, cache=NodeCache(), disk=disk)
    v2 = objs2[0].shape.volume  # ~8000 if invalidated; ~1000 if STALE
    assert abs(v1 - 1000) < 1.0
    assert v2 > 2000  # the asset change was picked up (NOT a stale cache hit)


def test_l2_to_l1_promotion_carries_asset_fingerprint(tmp_path):
    """Cross-session: a reopened workspace (cold L1, warm L2) promotes an L2 hit
    into L1. That promoted entry must carry the asset fingerprint so a later edit
    to the imported asset is revalidated and not served stale from the warm L1."""
    _ws(tmp_path)
    disk = DiskCache(str(tmp_path))
    # Session 1: cold L1 + L2, populates the DiskCache.
    graph.build_node(str(tmp_path), params={}, parent=None, cache=NodeCache(), disk=disk)

    # Session 2: FRESH NodeCache (reopened workspace) over the SAME warm DiskCache.
    # First build: L1 miss -> L2 hit -> promotes into L1.
    warm_l1 = NodeCache()
    graph.build_node(str(tmp_path), params={}, parent=None, cache=warm_l1, disk=disk)
    # Edit the asset on disk to a bigger cube.
    export_brep(Box(20, 20, 20), str(tmp_path / "assets" / "fixture.brep"))
    # Rebuild against the SAME warm L1: it must MISS the promoted entry and rebuild.
    objs = graph.build_node(str(tmp_path), params={}, parent=None, cache=warm_l1, disk=disk)
    assert objs[0].shape.volume > 2000  # picked up the edit, not a stale 1000


def test_promotion_keeps_hit_for_unchanged_asset(tmp_path):
    """A promoted L1 entry with an unchanged asset stays a hit (no needless rebuild)."""
    _ws(tmp_path)
    disk = DiskCache(str(tmp_path))
    graph.build_node(str(tmp_path), params={}, parent=None, cache=NodeCache(), disk=disk)

    warm_l1 = NodeCache()
    graph.build_node(str(tmp_path), params={}, parent=None, cache=warm_l1, disk=disk)  # promote
    hits_before = warm_l1.hits
    graph.build_node(str(tmp_path), params={}, parent=None, cache=warm_l1, disk=disk)  # unchanged
    assert warm_l1.hits == hits_before + 1  # served from L1, revalidation passed
