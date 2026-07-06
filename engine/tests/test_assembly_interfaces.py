"""check_interfaces validates the declared wiring of an assembly (every attach
names a published skeleton frame; every input names a published scalar) and folds
in the composed-model geometric interference summary. Recurses through
sub-assemblies. Never raises."""

import os

from solidifai_engine.assembly import manifest as manifest_mod
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


def _mk(tmp_path) -> Session:
    root = tmp_path
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def _set_attach(s, child_id, frame):
    """Rewrite a child's attach frame directly in the manifest (no rebuild), to
    set up an intentionally broken wiring the geometric build would otherwise
    refuse."""

    def mutate(man):
        c = manifest_mod.child_by_id(man, child_id)
        c.attach = frame

    s._rewrite_manifest(mutate)


def _set_inputs(s, child_id, inputs):
    def mutate(man):
        c = manifest_mod.child_by_id(man, child_id)
        c.inputs = list(inputs)

    s._rewrite_manifest(mutate)


def test_check_interfaces_flags_missing_attach_frame(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    _set_attach(s, "base", "ghost_frame")  # skeleton does not publish this
    res = s.check_interfaces()
    assert res["ok"] is True
    assert any(i["id"] == "base" and i["issue"] == "missing_attach_frame" for i in res["issues"])


def test_check_interfaces_flags_missing_input(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    _set_inputs(s, "base", ["body_w", "nonexistent"])
    res = s.check_interfaces()
    assert res["ok"] is True
    assert any(i["id"] == "base" and i["issue"] == "missing_input" for i in res["issues"])


def test_check_interfaces_clean_assembly(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    res = s.check_interfaces()
    assert res["ok"] is True and res["issues"] == []
    assert "interference" in res  # geometric summary folded in


def test_check_interfaces_requires_assembly(tmp_path):
    root = tmp_path / "single"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    res = s.check_interfaces()
    assert res["ok"] is False and "assembly" in res["error"].lower()


def test_check_interfaces_attach_none_is_clean(tmp_path):
    # attach=None means the node origin (always valid), not a missing frame.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach=None, inputs=["body_w", "wall"])
    res = s.check_interfaces()
    assert res["ok"] is True and res["issues"] == []


def test_check_interfaces_recurses_subassembly(tmp_path):
    # A sub-assembly node whose child attaches to a frame the sub-skeleton does
    # not publish is flagged with a path-qualified id.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.add_subassembly("hinge", attach="lid_frame", inputs=["body_w"])
    SUB_SKEL = (
        "from solidifai import skeleton\n"
        "from build123d import Location\n"
        "def build(parent):\n"
        "    s = skeleton()\n"
        "    s.scalar('pin_d', 4.0)\n"
        "    s.frame('pin_frame', Location((0, 0, 0)))\n"
        "    return s\n"
    )
    sub_dir = os.path.join(str(tmp_path), "hinge")
    with open(os.path.join(sub_dir, "skeleton.py"), "w", encoding="utf-8") as f:
        f.write(SUB_SKEL)

    def mutate(man):
        man.skeleton = "skeleton.py"
        man.children.append(
            manifest_mod.ChildEntry(
                id="pin",
                kind="part",
                source="parts/pin.py",
                attach="ghost",
                inputs=[],
            )
        )

    sub_man = manifest_mod.load_manifest(sub_dir)
    mutate(sub_man)
    manifest_mod.write_manifest(sub_dir, sub_man)
    os.makedirs(os.path.join(sub_dir, "parts"), exist_ok=True)
    with open(os.path.join(sub_dir, "parts", "pin.py"), "w", encoding="utf-8") as f:
        f.write(BASE_PART)

    res = s.check_interfaces()
    assert res["ok"] is True
    assert any(
        i["issue"] == "missing_attach_frame" and i["id"].endswith("pin") for i in res["issues"]
    )
