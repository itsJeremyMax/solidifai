"""Assembly-aware history: undo/redo/goto restore the whole recursive fileset
(skeleton + parts + manifest) and rebuild the DAG, and the structural diff
separates manifest / skeleton / per-part changes.

The composed object names are path-prefixed by the child id (e.g. "base/Base"),
so the tests assert against the part-id prefix rather than the bare show() name.
"""

import os

from solidifai_engine.session import Session

SKEL_2FRAME = """
from solidifai import skeleton
from build123d import Location
PARAMS = {
    "body_w": {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0, "unit": "mm"},
    "body_h": {"value": 30.0, "min": 15.0, "max": 90.0, "step": 1.0, "unit": "mm"},
    "wall":   {"value": 2.4, "min": 1.2, "max": 5.0, "step": 0.2, "unit": "mm"},
}
def build(body_w, body_h, wall):
    s = skeleton()
    s.scalar("body_w", body_w)
    s.scalar("wall", wall)
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, body_h)))
    return s
"""

BASE_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
"""

BASE_PART_V2 = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"] + 5, inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
"""

LID_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], 3)
    show(p.part, name="Lid")
"""

LID_PART_THICK = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    # THICK lid variant
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], 6)
    show(p.part, name="Lid")
"""


def _mk(tmp_path) -> Session:
    root = tmp_path
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def _part_ids(s) -> set:
    """Top-level part ids present in the composed model (first path segment)."""
    return {o.get("name", "").split("/", 1)[0] for o in s.get_model_info()["objects"]}


def test_assembly_undo_restores_prior_part_set(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART_THICK)  # edit lid (source only)
    with open(tmp_path / "parts" / "lid.py") as f:
        assert "THICK" in f.read()
    assert s.undo()["ok"] is True  # back to thin lid
    assert {"base", "lid"} <= _part_ids(s)
    with open(tmp_path / "parts" / "lid.py") as f:
        assert "THICK" not in f.read()
    assert s.redo()["ok"] is True
    with open(tmp_path / "parts" / "lid.py") as f:
        assert "THICK" in f.read()
    assert {"base", "lid"} <= _part_ids(s)


def test_assembly_undo_add_part_removes_its_file(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    assert (tmp_path / "parts" / "lid.py").exists()
    assert s.undo()["ok"] is True  # undo the lid add
    assert not (tmp_path / "parts" / "lid.py").exists()  # file gone, not orphaned
    assert _part_ids(s) == {"base"}
    # the manifest itself no longer lists lid
    from solidifai_engine.assembly import manifest as m

    assert m.child_by_id(m.load_manifest(str(tmp_path)), "lid") is None


def test_assembly_undo_remove_part_restores_its_file(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    s.remove_part("lid")
    assert not (tmp_path / "parts" / "lid.py").exists()
    assert s.undo()["ok"] is True  # undo the removal
    assert (tmp_path / "parts" / "lid.py").exists()  # source is back
    assert {"base", "lid"} <= _part_ids(s)


def test_assembly_goto_index(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    hist = s.history_state()
    assert s.goto(hist["index"] - 1)["ok"] is True  # one step back
    assert _part_ids(s) == {"base"}


def test_assembly_undo_skeleton_param_edit(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_params({"body_w": 90.0})  # widen the body
    wide_bbox = s.get_model_info()["bbox"]["size"]
    assert s.undo()["ok"] is True  # revert the width
    narrow_bbox = s.get_model_info()["bbox"]["size"]
    assert narrow_bbox[0] < wide_bbox[0]


def test_assembly_undo_refused_during_round(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.begin_round()
    res = s.undo()
    assert res["ok"] is False and "round" in res["error"].lower()
    # history untouched by the refused undo
    s.abort_round()


# -- Task 2: structural diff -------------------------------------------------


def test_structural_diff_classifies_changes(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    base_idx = s.history_state()["index"]
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])  # +child
    s.set_part("base", BASE_PART_V2)  # base source
    d = s.diff_against(base_idx)
    assert d["ok"] is True
    assert "lid" in d["structural"]["added"]
    assert "base" in d["parts"]["changed"]
    assert d["skeleton"]["changed"] is False  # skeleton unchanged here


def test_structural_diff_detects_skeleton_change(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    base_idx = s.history_state()["index"]
    # widen a param default (skeleton.py source changes)
    s.set_skeleton(SKEL_2FRAME.replace('"value": 60.0', '"value": 80.0'))
    d = s.diff_against(base_idx)
    assert d["ok"] is True
    assert d["skeleton"]["changed"] is True


def test_structural_diff_detects_removed_and_rewired(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    base_idx = s.history_state()["index"]
    s.remove_part("lid")  # structural: - child
    s.attach("base", "lid_frame")  # structural: rewired
    d = s.diff_against(base_idx)
    assert d["ok"] is True
    assert "lid" in d["structural"]["removed"]
    assert "base" in d["structural"]["rewired"]


# -- Data-loss regressions (C1, C2): the restore path must never touch a file or
# directory outside the declared, in-root assembly fileset. assembly.json is
# agent/user-editable, so a crafted child.source must not become an arbitrary
# delete, and the empty-dir prune must not sweep unrelated user directories.


def _write_manifest_json(path, data):
    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def test_restore_does_not_delete_out_of_root_file_via_crafted_source(tmp_path):
    # PoC (C1): a hand-edited assembly.json child whose source escapes the
    # workspace with "../" must NOT cause undo/goto to delete the targeted file.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])

    # A victim file in the workspace's PARENT directory (outside root).
    victim = tmp_path.parent / "VICTIM.txt"
    victim.write_text("precious user data", encoding="utf-8")
    nested_victim = tmp_path.parent / "NESTED_VICTIM.txt"
    nested_victim.write_text("also precious", encoding="utf-8")

    # Hand-edit the live manifest so a child points OUT of the root (leaf-part
    # branch) and a sub-assembly child also escapes (recursion branch, I1). These
    # children are not part of any committed snapshot, so they would land in
    # current - target and be deleted by an unguarded restore.
    import json

    man_path = tmp_path / "assembly.json"
    data = json.loads(man_path.read_text(encoding="utf-8"))
    data["children"].append(
        {"id": "evil", "kind": "part", "source": "../VICTIM.txt", "attach": None, "inputs": []}
    )
    data["children"].append(
        {"id": "evilsub", "kind": "assembly", "source": "../", "attach": None, "inputs": []}
    )
    _write_manifest_json(man_path, data)

    # Drive both navigation paths that would run the deletion loop. With the
    # load_manifest containment chokepoint, the crafted manifest fails to load, so
    # restore fails loudly (clean ok:False, no crash) BEFORE any deletion runs --
    # the out-of-root files survive either way.
    r = s.undo()
    assert r["ok"] is False and "escapes" in r["error"].lower()
    assert victim.exists(), "undo deleted an out-of-root file (C1)"
    r = s.goto(0)
    assert r["ok"] is False and "escapes" in r["error"].lower()
    assert victim.exists(), "goto deleted an out-of-root file (C1)"
    assert nested_victim.exists(), "restore escaped via a sub-assembly source (I1)"
    assert victim.read_text(encoding="utf-8") == "precious user data"


def test_restore_does_not_prune_unrelated_user_dirs(tmp_path):
    # PoC (C2): an undo that removes a part must not delete unrelated empty user
    # directories (git does not track empty dirs, so they would never come back).
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])

    user_empty = tmp_path / "docs"
    user_empty.mkdir()
    user_nested = tmp_path / "notes" / "sub"
    user_nested.mkdir(parents=True)

    s.undo()  # removes lid (a real prune)
    assert not (tmp_path / "parts" / "lid.py").exists()  # the orphan IS gone
    assert user_empty.is_dir(), "undo pruned an unrelated empty user dir (C2)"
    assert user_nested.is_dir(), "undo pruned a nested empty user dir (C2)"


def test_structural_diff_rewired_on_shape_inputs_change():
    """A child whose shape_inputs differs between snapshots must appear in rewired."""
    import json

    from solidifai_engine.assembly.diff import structural_diff

    child_before = {"id": "seat", "kind": "part", "attach": "o", "inputs": [], "shape_inputs": []}
    child_after = {
        "id": "seat",
        "kind": "part",
        "attach": "o",
        "inputs": [],
        "shape_inputs": ["seat"],
    }
    manifest_before = json.dumps({"version": 2, "children": [child_before]})
    manifest_after = json.dumps({"version": 2, "children": [child_after]})

    result = structural_diff(
        ".", {"assembly.json": manifest_before}, {"assembly.json": manifest_after}
    )
    assert "seat" in result["structural"]["rewired"]
