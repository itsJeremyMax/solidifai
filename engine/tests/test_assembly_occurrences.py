"""Occurrence-based instancing: ONE part definition placed at N frames, with
optional per-occurrence mirroring. Covers the manifest round-trip (byte-compat
when absent), graph composition, mirrored-geometry correctness (volume, chiral
BOM group, STL export), and the end-to-end session tools (set_occurrences,
attach re-point, get_part_info, check_interfaces, interference, flatten, diff,
warm-cache rebuild)."""

import json
import os

from solidifai_engine.assembly import compose, diff, flatten, graph
from solidifai_engine.assembly import manifest as manifest_mod
from solidifai_engine.assembly.cache import NodeCache
from solidifai_engine.drawing.features import group_parts
from solidifai_engine.session import Session

SKEL = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"gap": {"value": 40.0, "min": 10.0, "max": 120.0, "step": 1.0, "unit": "mm"}}
def build(gap):
    s = skeleton()
    s.scalar("gap", gap)
    s.frame("left", Location((0, 0, 0)))
    s.frame("right", Location((gap, 0, 0)))
    return s
"""

# A genuinely 3D-chiral part (three unequal perpendicular arms, no mirror plane),
# so a mirrored occurrence forms a SEPARATE chirality-aware BOM group.
GNOMON = """
from solidifai import show
from build123d import BuildPart, Box, Align
def build(inputs):
    a = (Align.MIN, Align.MIN, Align.MIN)
    with BuildPart() as p:
        Box(24, 6, 5, align=a)
        Box(6, 16, 5, align=a)
        Box(6, 6, 12, align=a)
    show(p.part, name="Gnomon", material="pla")
"""


def _write(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def _assembly(tmp_path, occurrences):
    root = str(tmp_path / "asm")
    _write(root, "skeleton.py", SKEL)
    _write(root, "parts/gnomon.py", GNOMON)
    child = {
        "id": "gnomon",
        "kind": "part",
        "source": "parts/gnomon.py",
        "attach": "left",
        "inputs": [],
    }
    if occurrences is not None:
        child["occurrences"] = occurrences
    _write(
        root,
        "assembly.json",
        json.dumps({"version": 2, "skeleton": "skeleton.py", "children": [child]}),
    )
    return root


def _session(tmp_path):
    """Session with an authored skeleton + single-occurrence part (via the tools)."""
    root = tmp_path / "asm"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    s.set_skeleton(SKEL)
    s.set_part("gnomon", GNOMON, attach="left")
    return s, root


# -- manifest round-trip ------------------------------------------------------


def test_manifest_without_occurrences_round_trips_byte_compatibly(tmp_path):
    root = _assembly(tmp_path, occurrences=None)
    man = manifest_mod.load_manifest(root)
    assert man.children[0].occurrences is None
    manifest_mod.write_manifest(root, man)
    data = json.loads((tmp_path / "asm" / "assembly.json").read_text())
    # No occurrences key is emitted for a legacy single-placement child.
    assert "occurrences" not in data["children"][0]


def test_manifest_rejects_bad_mirror(tmp_path):
    root = _assembly(tmp_path, occurrences=[{"frame": "left", "mirror": "diagonal"}])
    try:
        manifest_mod.load_manifest(root)
        raise AssertionError("expected a bad-mirror ValueError")
    except ValueError as exc:
        assert "mirror" in str(exc)


def test_effective_occurrences_defaults_to_single_at_attach(tmp_path):
    root = _assembly(tmp_path, occurrences=None)
    child = manifest_mod.load_manifest(root).children[0]
    occs = manifest_mod.effective_occurrences(child)
    assert len(occs) == 1 and occs[0].frame == "left" and occs[0].mirror is None


# -- graph composition --------------------------------------------------------


def test_graph_places_each_occurrence_with_stable_names(tmp_path):
    root = _assembly(
        tmp_path,
        occurrences=[
            {"frame": "left", "mirror": None},
            {"frame": "right", "mirror": None},
        ],
    )
    objs = graph.build_node(root, params={}, parent=None)
    names = sorted(o.name for o in objs)
    # First occurrence keeps the bare id; the rest gain @2, @3 ...
    assert names == ["gnomon/Gnomon", "gnomon@2/Gnomon"]
    xs = {o.name: round(o.shape.bounding_box().center().X, 1) for o in objs}
    assert xs["gnomon@2/Gnomon"] > xs["gnomon/Gnomon"]  # placed at the right frame


def test_occurrence_prefixes_helper():
    assert compose.occurrence_prefixes("wheel", 1) == ["wheel"]
    assert compose.occurrence_prefixes("wheel", 3) == ["wheel", "wheel@2", "wheel@3"]


# -- mirrored occurrence correctness -----------------------------------------


def test_mirrored_occurrence_volume_bom_and_export(tmp_path):
    s, root = _session(tmp_path)
    single_vol = s.get_model_info()["volume"]
    res = s.set_occurrences(
        "gnomon",
        [
            {"frame": "left", "mirror": None},
            {"frame": "right", "mirror": "yz"},
        ],
    )
    assert res["ok"] is True

    # Two bodies now compose.
    assert len(s._objects) == 2
    info = s.get_model_info()
    # Per-object unsigned aggregation: total volume is exactly 2x the single part,
    # NOT cancelled to ~0 by the mirror's negative determinant.
    assert abs(info["volume"] - 2 * single_vol) < 1e-3

    # The mirror is chiral, so it forms a SEPARATE BOM group from the original.
    groups = group_parts(s._objects)
    assert len(groups) == 2
    assert all(g["qty"] == 1 for g in groups)

    # The mirrored (negative-determinant) geometry still exports a valid STL.
    out = s.export("stl", path=str(root / "out.stl"))
    assert out["ok"] is True
    assert os.path.getsize(out["path"]) > 0


# -- session tools ------------------------------------------------------------


def test_set_occurrences_recompose_and_get_part_info(tmp_path):
    s, _root = _session(tmp_path)
    b0 = s.build_id
    res = s.set_occurrences(
        "gnomon",
        [
            {"frame": "left", "mirror": None},
            {"frame": "right", "mirror": None},
        ],
    )
    assert res["ok"] is True and s.build_id > b0

    info = s.get_part_info("gnomon")
    assert len(info["occurrences"]) == 2
    # solids are counted across EVERY occurrence, not just the primary.
    single = 1  # one solid per gnomon
    assert info["solids"] == 2 * single
    # attach re-points to the primary occurrence's frame.
    assert info["attach"] == "left"


def test_attach_repoints_primary_occurrence(tmp_path):
    s, root = _session(tmp_path)
    s.set_occurrences(
        "gnomon",
        [
            {"frame": "left", "mirror": None},
            {"frame": "right", "mirror": None},
        ],
    )
    assert s.attach("gnomon", "right")["ok"] is True
    man = manifest_mod.load_manifest(str(root))
    child = man.children[0]
    assert child.attach == "right"
    assert child.occurrences[0].frame == "right"  # primary followed attach
    assert child.occurrences[1].frame == "right"  # secondary untouched


def test_overlapping_occurrences_flag_interference(tmp_path):
    s, _root = _session(tmp_path)
    # Two occurrences at the SAME frame -> two bodies fully overlapping.
    s.set_occurrences(
        "gnomon",
        [
            {"frame": "left", "mirror": None},
            {"frame": "left", "mirror": None},
        ],
    )
    rep = s.check_interferences()
    assert rep["ok"] is True
    assert rep["summary"]["overlaps"] >= 1


def test_set_occurrences_rejects_bad_mirror_without_bricking(tmp_path):
    s, _root = _session(tmp_path)
    res = s.set_occurrences("gnomon", [{"frame": "left", "mirror": "nope"}])
    assert res["ok"] is False and "mirror" in res["error"]
    # The prior single-occurrence model still composes.
    assert s.set_params({"gap": 50.0})["ok"] is True


def test_bad_occurrence_frame_rolls_back(tmp_path):
    s, root = _session(tmp_path)
    res = s.set_occurrences("gnomon", [{"frame": "nonexistent", "mirror": None}])
    assert res["ok"] is False
    # Manifest was rolled back: the single-occurrence part is intact and rebuilds.
    man = manifest_mod.load_manifest(str(root))
    assert man.children[0].occurrences is None or all(
        o.frame != "nonexistent" for o in (man.children[0].occurrences or [])
    )
    assert s.set_params({"gap": 55.0})["ok"] is True


def test_check_interfaces_validates_occurrence_frames(tmp_path):
    s, root = _session(tmp_path)
    # Hand-write an occurrence with a bad frame, bypassing the tool guard.
    man = manifest_mod.load_manifest(str(root))
    man.children[0].occurrences = [
        manifest_mod.Occurrence(frame="left", mirror=None),
        manifest_mod.Occurrence(frame="ghost", mirror=None),
    ]
    manifest_mod.write_manifest(str(root), man)
    rep = s.check_interfaces()
    assert rep["ok"] is True
    frames_flagged = [i for i in rep["issues"] if i["issue"] == "missing_attach_frame"]
    assert any(i["name"] == "ghost" for i in frames_flagged)


# -- flatten + diff + cache ---------------------------------------------------


def test_flatten_reproduces_all_occurrences(tmp_path):
    root = _assembly(
        tmp_path,
        occurrences=[
            {"frame": "left", "mirror": None},
            {"frame": "right", "mirror": "yz"},
        ],
    )
    code = flatten.flatten_to_model(root, {"gap": 40.0})
    ns = {"__name__": "__main__"}
    import solidifai

    solidifai.reset_registry()
    exec(compile(code, "<flat>", "exec"), ns)
    shown = list(solidifai._registry())
    names = sorted(o.name for o in shown)
    assert names == ["gnomon/Gnomon", "gnomon@2/Gnomon"]
    solidifai.reset_registry()


def test_diff_reports_occurrence_change(tmp_path):
    root = _assembly(tmp_path, occurrences=None)
    old = (tmp_path / "asm" / "assembly.json").read_text()
    # Add a second occurrence.
    man = manifest_mod.load_manifest(root)
    man.children[0].occurrences = [
        manifest_mod.Occurrence(frame="left", mirror=None),
        manifest_mod.Occurrence(frame="right", mirror="yz"),
    ]
    manifest_mod.write_manifest(root, man)
    new = (tmp_path / "asm" / "assembly.json").read_text()
    rep = diff.structural_diff(root, {"assembly.json": old}, {"assembly.json": new})
    assert "gnomon" in rep["structural"]["rewired"]


def test_warm_cache_rebuild_reproduces_all_occurrences(tmp_path):
    root = _assembly(
        tmp_path,
        occurrences=[
            {"frame": "left", "mirror": None},
            {"frame": "right", "mirror": None},
        ],
    )
    cache = NodeCache()
    first = graph.build_node(root, params={}, parent=None, cache=cache)
    assert len(first) == 2
    # Second build hits the L1 cache for the single part definition, yet still
    # composes BOTH occurrences (occurrences live in the manifest, not the cache).
    second = graph.build_node(root, params={}, parent=None, cache=cache)
    assert cache.hits >= 1
    assert sorted(o.name for o in second) == ["gnomon/Gnomon", "gnomon@2/Gnomon"]
