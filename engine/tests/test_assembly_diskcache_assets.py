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
