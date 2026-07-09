"""Finding 1: features are discoverable/targetable in assembly mode.

Per-part feature() declarations are carried out of each isolated part build,
namespaced <part>/<name>, placed into composed coordinates, and survive the L1/L2
cache round-trip. set_feature routes a skeleton-param-driven feature through
set_params; inference falls back when nothing is declared."""

import os

from solidifai_engine.session import Session

SKEL = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"bore": {"value": 6.0, "min": 2.0, "max": 18.0, "step": 1.0, "unit": "mm"}}
def build(bore):
    s = skeleton()
    s.scalar("bore", bore)
    s.frame("f0", Location((0, 0, 0)))
    s.frame("f1", Location((50, 0, 0)))
    return s
"""

PLATE = """
from solidifai import show, feature
from build123d import BuildPart, Box, Locations, Hole
def build(inputs):
    with BuildPart() as p:
        Box(40, 40, 10)
        with feature("center_bore", driven_by="bore"), Locations((0, 0)):
            Hole(radius=inputs["bore"] / 2)
    show(p.part, name="Plate")
"""

PLATE_DUP = """
from solidifai import show, feature
from build123d import BuildPart, Box, Locations, Hole
def build(inputs):
    with BuildPart() as p:
        Box(60, 30, 10)
        with feature("port", driven_by="bore"), Locations((-15, 0)):
            Hole(radius=inputs["bore"] / 2)
        with feature("port", driven_by="bore"), Locations((15, 0)):
            Hole(radius=inputs["bore"] / 2)
    show(p.part, name="Plate")
"""

PLATE_UNTAGGED = """
from solidifai import show
from build123d import BuildPart, Box, Locations, Hole
def build(inputs):
    with BuildPart() as p:
        Box(40, 40, 10)
        with Locations((0, 0)):
            Hole(radius=inputs["bore"] / 2)
    show(p.part, name="Plate")
"""


def _mk(tmp_path) -> Session:
    root = tmp_path
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def test_inspect_features_lists_namespaced_part_feature(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.set_part("pin", PLATE, attach="f0", inputs=["bore"])["ok"] is True
    feats = s.inspect_features()["features"]
    assert [f["name"] for f in feats] == ["pin/center_bore"]
    f = feats[0]
    assert f["driven_by"] == ["bore"] and f["part"] == "pin"
    assert f["center"] is not None and f["bbox"] is not None


def test_feature_at_resolves_composed_feature(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("pin", PLATE, attach="f1", inputs=["bore"])  # placed at (50,0,0)
    # the bore center sits at the placed origin; a generous radius resolves it
    hit = s.feature_at([50.0, 0.0, 0.0], tolerance_mm=6.0)
    assert hit["match"] is not None and hit["match"]["name"] == "pin/center_bore"
    # and NOT at the un-shifted origin
    assert s.feature_at([0.0, 0.0, 0.0], tolerance_mm=6.0)["match"] is None


def test_set_feature_routes_through_skeleton_param(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("pin", PLATE, attach="f0", inputs=["bore"])
    b0 = s.build_id
    res = s.set_feature("pin/center_bore", {"bore": 12})
    assert res["ok"] is True
    assert s.build_id > b0
    assert s.get_params()["values"]["bore"] == 12
    # the feature is still listed after the param-driven rebuild
    assert [f["name"] for f in s.inspect_features()["features"]] == ["pin/center_bore"]


def test_duplicate_feature_names_within_part_disambiguated(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("pin", PLATE_DUP, attach="f0", inputs=["bore"])
    names = [f["name"] for f in s.inspect_features()["features"]]
    assert names == ["pin/port", "pin/port_2"]


def test_assembly_inference_fallback_when_untagged(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("pin", PLATE_UNTAGGED, attach="f0", inputs=["bore"])
    feats = s.inspect_features()["features"]
    assert feats, "expected inferred features for an untagged assembly with a hole"
    assert all(f["inferred"] is True for f in feats)


def test_features_survive_cache_round_trip(tmp_path):
    # Force an L2 (disk) hit on a cold L1: the reloaded part must still yield its
    # feature (metadata + geometry) so inspect/feature_at keep working.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("pin", PLATE, attach="f0", inputs=["bore"])
    # Drop the in-memory L1 cache so the next compose is served from L2 (disk).
    from solidifai_engine.assembly.cache import NodeCache

    s._node_cache = NodeCache()
    assert s.set_params({"bore": 6.0})["ok"] is True  # recompose (same values)
    assert s._disk_cache.hits >= 1  # served from L2
    feats = s.inspect_features()["features"]
    assert [f["name"] for f in feats] == ["pin/center_bore"]
    assert feats[0]["driven_by"] == ["bore"] and feats[0]["bbox"] is not None


def test_serialize_feature_round_trip(tmp_path):
    # Direct serialize/load_features round-trip (BREP faces + metadata).
    from build123d import Box, BuildPart, Hole, Locations

    import solidifai
    from solidifai import feature
    from solidifai_engine.assembly import serialize

    solidifai.reset_registry()
    with solidifai.build_scope() as scope:
        with BuildPart() as p:
            Box(40, 40, 10)
            with feature("bore", driven_by="bore"), Locations((0, 0)):
                Hole(radius=5)
        solidifai.show(p.part, name="Plate")
    objs, feats = list(scope.objects), list(scope.features)
    d = str(tmp_path / "cache")
    serialize.dump_result(d, "k1", objs, assets={}, features=feats)
    loaded = serialize.load_features(d, "k1")
    assert [r.name for r in loaded] == ["bore"]
    assert loaded[0].driven_by == ["bore"]
    assert loaded[0].faces, "feature faces must survive the BREP round-trip"
