"""Correctness guard: a warm build that reuses cached parts must produce
byte-identical geometry to a fully-cold build at the same final params.

Wall controls base/lid thickness; pin/knuckle derive from body_w only, so
they are cache hits on the second build while base/lid are rebuilt fresh.
The comparison confirms the cache returns faithful geometry, not stale or
wrong results."""

import json
import os
import shutil

from solidifai_engine.assembly import compose, graph
from solidifai_engine.assembly.cache import NodeCache
from solidifai_engine.render import render_to

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def _render(tmp_path, name, objects):
    artifacts = tmp_path / name
    artifacts.mkdir()
    render_to(str(artifacts), 1, objects=objects, node_ids=compose.path_ids(objects))
    return json.loads((artifacts / "model.json").read_text(encoding="utf-8"))


def _geom_key(m):
    return (
        sorted(o["id"] for o in m["objects"]),
        [round(x, 6) for x in m["bbox"]["min"]],
        [round(x, 6) for x in m["bbox"]["max"]],
        round(m["mass"]["value"], 4),
    )


def test_warm_build_with_hits_matches_cold_build(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(FIXTURE, root)

    # cold: one fresh build straight to wall=3.0, no cache
    cold_objs = graph.build_node(str(root), params={"wall": 3.0}, parent=None, cache=None)
    cold = _render(tmp_path, "cold", cold_objs)

    # warm: build at defaults (populates cache), then at wall=3.0 so pin/knuckle
    # (which consume pin_d, unaffected by wall) are reused from cache
    cache = NodeCache()
    graph.build_node(str(root), params={}, parent=None, cache=cache)
    warm_objs = graph.build_node(str(root), params={"wall": 3.0}, parent=None, cache=cache)
    assert cache.hits >= 2  # pin + knuckle genuinely reused
    warm = _render(tmp_path, "warm", warm_objs)

    assert _geom_key(warm) == _geom_key(cold)
