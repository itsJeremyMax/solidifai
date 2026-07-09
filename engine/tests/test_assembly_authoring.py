"""Session-level assembly authoring tools (set_skeleton, set_part, read/edit)."""

import os

from solidifai_engine.session import Session

SKEL = """
from solidifai import skeleton
PARAMS = {"w": {"value": 50.0, "min": 10.0, "max": 100.0, "step": 1.0, "unit": "mm"}}
def build(w):
    s = skeleton()
    s.scalar("w", w)
    s.frame("base_frame", __import__("build123d").Location((0, 0, 0)))
    return s
"""

PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["w"], inputs["w"], 3)
    show(p.part, name="Base")
"""


def _mk(tmp_path) -> Session:
    """An empty workspace not yet in assembly mode; set_skeleton turns it on."""
    root = tmp_path
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def test_set_skeleton_initializes_assembly(tmp_path):
    s = _mk(tmp_path)
    res = s.set_skeleton(SKEL)
    assert res["ok"] is True
    assert os.path.exists(tmp_path / "assembly.json")  # workspace became an assembly
    assert os.path.exists(tmp_path / "skeleton.py")
    assert s._is_assembly_mode() is True
    # the skeleton PARAMS now drive the UI sliders
    block = s._params_block()
    assert block["values"]["w"] == 50.0


def test_set_part_over_subassembly_id_is_rejected(tmp_path):
    # Finding 8: set_part must not silently convert a sub-assembly to a part and
    # orphan its directory.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.add_subassembly("hinge", attach="base_frame")["ok"] is True
    res = s.set_part("hinge", PART, attach="base_frame", inputs=["w"])
    assert res["ok"] is False
    assert "sub-assembly" in res["error"] and "remove_part" in res["error"]
    assert os.path.isdir(tmp_path / "hinge")  # the sub-assembly dir is intact
    assert not os.path.exists(tmp_path / "parts" / "hinge.py")  # no orphan part source


def test_add_subassembly_over_part_id_is_rejected(tmp_path):
    # Finding 8: the reverse direction must not orphan parts/<id>.py.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.set_part("base", PART, attach="base_frame", inputs=["w"])["ok"] is True
    res = s.add_subassembly("base", attach="base_frame")
    assert res["ok"] is False
    assert "part" in res["error"] and "remove_part" in res["error"]
    assert os.path.exists(tmp_path / "parts" / "base.py")  # part source not orphaned
    assert not os.path.isdir(tmp_path / "base")  # no stray sub-assembly dir


def test_set_part_adds_child_and_builds(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    res = s.set_part("base", PART, attach="base_frame", inputs=["w"])
    assert res["ok"] is True
    from solidifai_engine.assembly import manifest as m

    man = m.load_manifest(str(tmp_path))
    e = m.child_by_id(man, "base")
    assert e and e.kind == "part" and e.source == "parts/base.py"
    assert e.attach == "base_frame" and e.inputs == ["w"]
    assert os.path.exists(tmp_path / "parts" / "base.py")
    # the composed model now has one object; the composer path-prefixes the
    # part's show() name with the child id (base/Base).
    info = s.get_model_info()
    assert any(o.get("name", "").endswith("Base") for o in info["objects"])
    assert any(o.get("id", "").startswith("base") for o in info["objects"])


def test_set_part_requires_assembly(tmp_path):
    s = _mk(tmp_path)
    res = s.set_part("base", PART)
    assert res["ok"] is False and "skeleton" in res["error"].lower()


def test_set_part_update_preserves_wiring(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    # updating source without re-specifying attach/inputs keeps them
    s.set_part("base", PART.replace('name="Base"', 'name="Base2"'))
    from solidifai_engine.assembly import manifest as m

    e = m.child_by_id(m.load_manifest(str(tmp_path)), "base")
    assert e.attach == "base_frame" and e.inputs == ["w"]


def test_get_assembly_tree(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    tree = s.get_assembly_tree()
    assert tree["ok"] is True
    assert "base_frame" in tree["tree"]["skeleton"]["frames"]
    assert [c["id"] for c in tree["tree"]["children"]] == ["base"]


def test_get_part_info(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    info = s.get_part_info("base")
    assert info["ok"] is True
    assert info["id"] == "base" and info["attach"] == "base_frame"
    assert info["inputs"] == ["w"]
    assert "def build(inputs)" in info["source"]
    assert info["solids"] >= 1  # last build produced geometry


def test_get_part_info_missing(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.get_part_info("nope")["ok"] is False


# A two-frame skeleton: base_frame at origin and alt offset on +X.
SKEL_ALT = SKEL.replace(
    "    return s",
    '    s.frame("alt", __import__("build123d").Location((10, 0, 0)))\n    return s',
)


def test_attach_moves_without_rebuild(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    # add a second frame to the skeleton, then re-attach base to it
    s.set_skeleton(SKEL_ALT)
    res = s.attach("base", "alt")
    assert res["ok"] is True
    from solidifai_engine.assembly import manifest as m

    e = m.child_by_id(m.load_manifest(str(tmp_path)), "base")
    assert e.attach == "alt"


def test_attach_missing_child(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.attach("ghost", "base_frame")["ok"] is False


def test_set_inputs_updates_wiring(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    res = s.set_inputs("base", ["w"])  # idempotent here; assert it stays consistent
    assert res["ok"] is True
    from solidifai_engine.assembly import manifest as m

    assert m.child_by_id(m.load_manifest(str(tmp_path)), "base").inputs == ["w"]


def test_remove_part(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    res = s.remove_part("base")
    assert res["ok"] is True
    from solidifai_engine.assembly import manifest as m

    assert m.child_by_id(m.load_manifest(str(tmp_path)), "base") is None
    assert not os.path.exists(tmp_path / "parts" / "base.py")


def test_remove_part_missing(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.remove_part("ghost")["ok"] is False


def test_add_subassembly(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    res = s.add_subassembly("hinge", attach="base_frame", inputs=["w"])
    assert res["ok"] is True
    # a sub-assembly folder with its own manifest now exists
    assert os.path.exists(tmp_path / "hinge" / "assembly.json")
    from solidifai_engine.assembly import manifest as m

    e = m.child_by_id(m.load_manifest(str(tmp_path)), "hinge")
    assert e.kind == "assembly" and e.source == "hinge/"
    assert e.attach == "base_frame" and e.inputs == ["w"]


def test_build_part_returns_node_result(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    res = s.build_part("base")
    assert res["ok"] is True
    assert res["id"] == "base" and res["solids"] >= 1
    assert res["valid"] is True


def test_build_part_reports_failure(tmp_path):
    # A failed set_part rolls back (atomic), so plant the broken part directly to
    # exercise build_part's own isolated-build failure reporting.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    bad = "from solidifai import show\ndef build(inputs):\n    raise ValueError('boom')\n"
    (tmp_path / "parts" / "oops.py").write_text(bad, encoding="utf-8")
    from solidifai_engine.assembly import manifest as m

    man = m.load_manifest(str(tmp_path))
    m.upsert_child(
        man, m.ChildEntry("oops", "part", "parts/oops.py", attach="base_frame", inputs=["w"])
    )
    m.write_manifest(str(tmp_path), man)
    res = s.build_part("oops")
    assert res["ok"] is False and "boom" in res["error"]


def test_build_part_missing(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.build_part("ghost")["ok"] is False


SKEL_SHAPE = """\
from solidifai import skeleton
from build123d import Rectangle, Location
PARAMS = {"w": {"value": 40.0, "min": 10, "max": 80, "step": 1, "unit": "mm"}}
def build(w):
    s = skeleton()
    s.profile("seat", Rectangle(w, w))
    s.frame("o", Location((0, 0, 0)))
    return s
"""

PART_SHAPE = """\
from solidifai import show
from build123d import BuildPart, BuildSketch, add, extrude
def build(inputs):
    with BuildPart() as p:
        with BuildSketch():
            add(inputs["seat"])
        extrude(amount=3)
    show(p.part, name="Base")
"""


def test_get_part_info_includes_shape_inputs(tmp_path):
    s = _mk(tmp_path)
    res = s.set_skeleton(SKEL_SHAPE)
    assert res["ok"], res
    res2 = s.set_part("base", PART_SHAPE, attach="o", inputs=[], shape_inputs=["seat"])
    assert res2.get("ok"), res2
    info = s.get_part_info("base")
    assert info["ok"] is True
    assert info["shape_inputs"] == ["seat"]
