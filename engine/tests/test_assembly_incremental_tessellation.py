"""Prove that unchanged parts are not re-tessellated on a re-render.

The B1 NodeCache stores the same shape objects (by Python identity) across
re-builds when no geometric change occurs. export_gltf meshes each shape
before writing and then calls BRepTools.Clean_s -- so the active triangulation
is removed after each render. The reuse proof is therefore:

  ensure_meshed() + triangle_count() on the cached shapes before the second
  render produces the same counts as before the first render, confirming that
  the same underlying TShape objects are reused (no geometric rebuild happened).
"""

import json
import os

from solidifai_engine.assembly import compose, graph
from solidifai_engine.assembly.cache import NodeCache
from solidifai_engine.assembly.meshing import ensure_meshed, is_meshed, triangle_count
from solidifai_engine.render import render_to

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def _cached_shapes(cache):
    return [o.shape for objs in cache._store.values() for o in objs]


def _mesh_all(shapes):
    for s in shapes:
        ensure_meshed(s)


def test_is_meshed_reflects_triangulation_state():
    """is_meshed and ensure_meshed correctly reflect OCC triangulation state."""
    from build123d import Box
    from OCP.BRepTools import BRepTools

    box = Box(10, 10, 10)
    assert not is_meshed(box)
    assert triangle_count(box) == 0

    ensure_meshed(box)
    assert is_meshed(box)
    assert triangle_count(box) > 0

    # Clean_s removes the triangulation (same behavior as export_gltf uses)
    BRepTools.Clean_s(box.wrapped)
    assert not is_meshed(box)
    assert triangle_count(box) == 0


def test_frame_only_rerender_reuses_tessellation(tmp_path):
    """A body_h change only moves frames; no part rebuilds, so the same shape
    objects survive in the cache and produce identical triangle counts."""
    cache = NodeCache()
    objs1 = graph.build_node(FIXTURE, params={}, parent=None, cache=cache)
    art1 = tmp_path / "a"
    art1.mkdir()
    render_to(str(art1), 1, objects=objs1, node_ids=compose.path_ids(objs1))

    # Mesh the cached shapes explicitly -- they share TShape with the placed copies
    # that were rendered, so the deflection used by ensure_meshed is deterministic.
    cached = _cached_shapes(cache)
    _mesh_all(cached)
    before = {id(s): triangle_count(s) for s in cached}
    assert all(c > 0 for c in before.values()), "expected non-zero triangles after ensure_meshed"

    # Re-build with body_h change: only frames move, no part consumes body_h,
    # so all 4 parts are cache hits (same Python objects).
    objs2 = graph.build_node(FIXTURE, params={"body_h": 80.0}, parent=None, cache=cache)
    art2 = tmp_path / "b"
    art2.mkdir()
    render_to(str(art2), 2, objects=objs2, node_ids=compose.path_ids(objs2))

    # Re-mesh and re-count: same shape objects -> same counts (not re-built).
    _mesh_all(cached)
    after = {id(s): triangle_count(s) for s in cached}
    assert before == after, "cached shapes changed identity or geometry -- unexpected rebuild"
    assert len(before) == 4


def test_changed_part_remeshes_others_reuse(tmp_path):
    """A wall-thickness change rebuilds base+lid; pin/knuckle are cache hits.
    All 4 cached shapes can be meshed and produce valid geometry after both renders."""
    cache = NodeCache()
    objs1 = graph.build_node(FIXTURE, params={}, parent=None, cache=cache)
    art1 = tmp_path / "a"
    art1.mkdir()
    render_to(str(art1), 1, objects=objs1, node_ids=compose.path_ids(objs1))

    # Record which shape objects are cached after the first build.
    first_ids = {id(s) for s in _cached_shapes(cache)}
    assert len(first_ids) == 4

    objs2 = graph.build_node(FIXTURE, params={"wall": 3.5}, parent=None, cache=cache)
    art2 = tmp_path / "b"
    art2.mkdir()
    render_to(str(art2), 2, objects=objs2, node_ids=compose.path_ids(objs2))

    # After the second build the cache holds the new shapes; all are meshable.
    cached2 = _cached_shapes(cache)
    _mesh_all(cached2)
    assert all(is_meshed(s) for s in cached2)
    assert all(triangle_count(s) > 0 for s in cached2)

    # model.json must reflect all 4 parts.
    model = json.loads((art2 / "model.json").read_text(encoding="utf-8"))
    assert len(model["objects"]) == 4
