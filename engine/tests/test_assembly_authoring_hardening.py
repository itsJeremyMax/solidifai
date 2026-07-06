"""Regression tests for Phase 2A authoring hardening: path-traversal safety (C1),
atomic set_part rollback (I1), empty-geometry handling (I2), typed empty-compose
signal (I3), build_part compose status (I4)."""

import os

import pytest

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
    """A workspace under tmp_path/ws so we can assert NOTHING is written above it."""
    root = tmp_path / "ws"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


# -- C1: path traversal -----------------------------------------------------

# ids that must be rejected before they reach the filesystem.
BAD_IDS = ["../escape", "a/b", "", ".", "..", "a\\b", "/abs", "x\x00y", "a.b"]


@pytest.mark.parametrize("bad_id", BAD_IDS)
def test_set_part_rejects_unsafe_id(tmp_path, bad_id):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    res = s.set_part(bad_id, PART, attach="base_frame", inputs=["w"])
    assert res["ok"] is False and "invalid" in res["error"].lower()
    # nothing was written anywhere under or above the workspace for this id
    assert not os.path.exists(tmp_path / "escape.py")
    assert not os.path.exists(tmp_path / "ws" / "parts" / "escape.py")


@pytest.mark.parametrize("bad_id", BAD_IDS)
def test_add_subassembly_rejects_unsafe_id(tmp_path, bad_id):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    res = s.add_subassembly(bad_id, attach="base_frame")
    assert res["ok"] is False and "invalid" in res["error"].lower()
    assert not os.path.exists(tmp_path / "escape")


@pytest.mark.parametrize("bad_id", BAD_IDS)
def test_read_and_edit_tools_reject_unsafe_id(tmp_path, bad_id):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    for fn in (
        lambda: s.remove_part(bad_id),
        lambda: s.build_part(bad_id),
        lambda: s.get_part_info(bad_id),
        lambda: s.attach(bad_id, "base_frame"),
        lambda: s.set_inputs(bad_id, ["w"]),
    ):
        res = fn()
        assert res["ok"] is False and "invalid" in res["error"].lower()


# -- I1: atomic set_part (failed build must be a clean no-op) ----------------

RAISES_PART = "from solidifai import show\ndef build(inputs):\n    raise ValueError('boom')\n"


def test_set_part_failure_is_atomic_no_op(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])  # a good part exists
    res = s.set_part("bad", RAISES_PART, attach="base_frame", inputs=["w"])
    assert res["ok"] is False and "boom" in res["error"]
    # the broken part did NOT poison the manifest or leave a source file
    from solidifai_engine.assembly import manifest as m

    root = str(tmp_path / "ws")
    assert m.child_by_id(m.load_manifest(root), "bad") is None
    assert not os.path.exists(tmp_path / "ws" / "parts" / "bad.py")
    # the workspace still works: a subsequent rebuild/edit succeeds
    assert s.set_params({"w": 60.0})["ok"]
    assert s.get_model_info()["objects"]


def test_set_part_update_failure_restores_prior_source(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    good_src = (tmp_path / "ws" / "parts" / "base.py").read_text(encoding="utf-8")
    # a failing UPDATE to an existing part must restore the prior good source + wiring
    res = s.set_part("base", RAISES_PART)
    assert res["ok"] is False
    from solidifai_engine.assembly import manifest as m

    e = m.child_by_id(m.load_manifest(str(tmp_path / "ws")), "base")
    assert e is not None and e.attach == "base_frame" and e.inputs == ["w"]
    assert (tmp_path / "ws" / "parts" / "base.py").read_text(encoding="utf-8") == good_src
    assert s.get_model_info()["objects"]  # still composes the prior-good model


def test_set_part_empty_geometry_rolls_back(tmp_path):
    """I1 + I2 together: a no-show() part fails cleanly AND leaves no trace."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    res = s.set_part("ghost", EMPTY_PART, attach="base_frame", inputs=["w"])
    assert res["ok"] is False and "no geometry" in res["error"].lower()
    from solidifai_engine.assembly import manifest as m

    assert m.child_by_id(m.load_manifest(str(tmp_path / "ws")), "ghost") is None
    assert not os.path.exists(tmp_path / "ws" / "parts" / "ghost.py")
    assert s.set_params({"w": 55.0})["ok"]  # not bricked


# -- I4: build_part surfaces whole-assembly compose status -------------------


def test_build_part_reports_compose_status(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("good", PART, attach="base_frame", inputs=["w"])
    # plant a second, broken part directly so the whole-assembly compose fails
    # while the "good" part itself is still valid
    (tmp_path / "ws" / "parts" / "broken.py").write_text(RAISES_PART, encoding="utf-8")
    from solidifai_engine.assembly import manifest as m

    root = str(tmp_path / "ws")
    man = m.load_manifest(root)
    m.upsert_child(
        man, m.ChildEntry("broken", "part", "parts/broken.py", attach="base_frame", inputs=["w"])
    )
    m.write_manifest(root, man)
    res = s.build_part("good")
    assert res["ok"] is True  # the good part built in isolation
    assert res["valid"] is True and res["solids"] >= 1
    assert res["composed"] is False  # but the whole assembly does not compose


def test_build_part_compose_ok_when_assembly_healthy(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    res = s.build_part("base")
    assert res["ok"] is True and res["composed"] is True


# -- I2: empty-geometry part -------------------------------------------------

EMPTY_PART = "from solidifai import show\ndef build(inputs):\n    pass\n"  # no show()


def test_empty_geometry_part_clean_message(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    res = s.set_part("ghost", EMPTY_PART, attach="base_frame", inputs=["w"])
    assert res["ok"] is False
    # a readable message, not the OCC "Write_s(): incompatible function arguments"
    assert "no geometry" in res["error"].lower()
    assert "Write_s" not in res["error"]
    assert "show()" in res["error"]


# -- M1: _shape_is_valid is fail-closed --------------------------------------


def test_shape_is_valid_fails_closed():
    # a shape with no is_valid attribute must NOT be assumed valid
    class NoValidity:
        pass

    assert Session._shape_is_valid(NoValidity()) is False

    # a method form and a property form both resolve correctly
    class MethodForm:
        def is_valid(self):
            return True

    class PropForm:
        is_valid = False

    assert Session._shape_is_valid(MethodForm()) is True
    assert Session._shape_is_valid(PropForm()) is False


# -- M2: _assembly_root_paths uses a real check, not a strippable assert -----


def test_assembly_root_paths_raises_real_error_without_root(tmp_path):
    s = Session(str(tmp_path / "art"))  # bare session, root is None
    assert s.root is None
    with pytest.raises(RuntimeError):
        s._assembly_root_paths()


# -- I3: typed empty-compose signal (no brittle substring matching) ----------


def test_skeleton_only_assembly_is_benign_empty(tmp_path):
    """A skeleton with no children composes to nothing: ok:True, empty, no error."""
    s = _mk(tmp_path)
    res = s.set_skeleton(SKEL)
    assert res["ok"] is True
    # removing the only part returns to the benign-empty state
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    rm = s.remove_part("base")
    assert rm["ok"] is True


def test_empty_compose_with_children_is_not_silent_ok(tmp_path):
    """Children exist but the assembly composed to no geometry: must NOT be a
    silent ok:True with a stale build id."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    # add a sub-assembly child that itself has no children/geometry, then force a
    # build directly: this is "children exist, zero geometry".
    s.add_subassembly("empty_sub", attach="base_frame")
    res = s._build_assembly(params=s._param_values)
    assert res["ok"] is False
    assert "no geometry" in res["error"].lower() or "no objects" in res["error"].lower()


def test_remove_part_refuses_escaping_source(tmp_path):
    """A hand-edited/inconsistent manifest source that escapes root must NOT be
    deleted; remove_part fails loudly (the load_manifest containment chokepoint
    rejects the escaping source) instead of os.remove'ing outside root."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", PART, attach="base_frame", inputs=["w"])
    # plant a file outside the workspace and point the manifest source at it
    victim = tmp_path / "victim.txt"
    victim.write_text("precious", encoding="utf-8")
    from solidifai_engine.assembly import manifest as m

    root = str(tmp_path / "ws")
    # write the crafted manifest directly (write_manifest does not validate; the
    # load-time guard is the chokepoint that catches it on the next read).
    m.write_manifest(
        root,
        m.Manifest(
            skeleton="skeleton.py",
            children=[
                m.ChildEntry(id="base", kind="part", source="../victim.txt"),
            ],
        ),
    )
    res = s.remove_part("base")
    assert res["ok"] is False and "escapes" in res["error"].lower()
    assert victim.exists()  # data-loss bomb defused


# -- A1: atomic set_inputs / attach (a bad input must not brick the assembly) -

# A 2-frame skeleton that publishes body_w + wall as scalars but NOT body_h
# (body_h drives a frame only). set_inputs(..., ["body_h"]) therefore fails in
# resolve_inputs, and a non-atomic mutation would leave the bad input persisted.
SKEL_2 = """
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

LID = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], 3)
    show(p.part, name="Lid")
"""


def test_set_inputs_bad_scalar_is_atomic_no_op(tmp_path):
    """PoC: set_inputs naming a non-scalar (body_h) raises in resolve_inputs.
    A non-atomic mutation persisted the bad input and bricked EVERY later compose
    (even set_params). It must roll back: ok:False, manifest unchanged, not bricked."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2)
    s.set_part("lid", LID, attach="lid_frame", inputs=["body_w", "wall"])
    from solidifai_engine.assembly import manifest as m

    root = str(tmp_path / "ws")
    before = m.child_by_id(m.load_manifest(root), "lid").inputs

    res = s.set_inputs("lid", ["body_w", "body_h", "wall"])  # body_h is not a scalar
    assert res["ok"] is False and "body_h" in res["error"]

    # the manifest input wiring is UNCHANGED (rolled back to the prior good set)
    after = m.child_by_id(m.load_manifest(root), "lid").inputs
    assert after == before == ["body_w", "wall"]
    # the assembly is NOT bricked: a later set_params and read still work
    assert s.set_params({"body_w": 70.0})["ok"]
    assert s.get_model_info()["objects"]


def test_attach_bad_frame_is_atomic_no_op(tmp_path):
    """attach to a frame the skeleton does not publish must be a clean no-op too."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2)
    s.set_part("lid", LID, attach="lid_frame", inputs=["body_w", "wall"])
    from solidifai_engine.assembly import manifest as m

    root = str(tmp_path / "ws")
    before = m.child_by_id(m.load_manifest(root), "lid").attach

    res = s.attach("lid", "no_such_frame")
    assert res["ok"] is False

    after = m.child_by_id(m.load_manifest(root), "lid").attach
    assert after == before == "lid_frame"  # attach wiring rolled back
    assert s.set_params({"body_w": 70.0})["ok"]  # not bricked
    assert s.get_model_info()["objects"]
