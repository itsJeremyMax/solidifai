"""Manifest child helpers + the read-only assembly_tree reader."""

import os
import shutil

from solidifai_engine.assembly.manifest import (
    ChildEntry,
    Manifest,
    child_by_id,
    remove_child,
    upsert_child,
)
from solidifai_engine.assembly.tree import assembly_tree

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def test_child_helpers_roundtrip():
    man = Manifest(skeleton="skeleton.py", children=[ChildEntry("base", "part", "parts/base.py")])
    assert child_by_id(man, "base").source == "parts/base.py"
    assert child_by_id(man, "missing") is None
    # upsert updates in place, preserves order, does not duplicate
    upsert_child(man, ChildEntry("base", "part", "parts/base.py", attach="base_frame"))
    assert len(man.children) == 1 and man.children[0].attach == "base_frame"
    # upsert appends a new id
    upsert_child(man, ChildEntry("lid", "part", "parts/lid.py"))
    assert [c.id for c in man.children] == ["base", "lid"]
    # remove drops it and returns True; removing missing returns False
    assert remove_child(man, "base") is True
    assert [c.id for c in man.children] == ["lid"]
    assert remove_child(man, "nope") is False


def test_assembly_tree_nested(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(FIX, root)
    tree = assembly_tree(str(root))
    assert tree["skeleton"]["params"]["body_w"]["value"] == 60.0  # from fixture PARAMS
    assert set(tree["skeleton"]["frames"]) >= {"base_frame", "lid_frame", "hinge_frame"}
    ids = {c["id"]: c for c in tree["children"]}
    assert ids["base"]["kind"] == "part" and ids["base"]["attach"] == "base_frame"
    # the sub-assembly recurses and reports its own children
    hinge = ids["hinge"]
    assert hinge["kind"] == "assembly"
    assert {c["id"] for c in hinge["children"]} == {"pin", "knuckle"}
