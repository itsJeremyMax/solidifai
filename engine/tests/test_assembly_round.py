"""Authoring-round behavior: begin_round freezes the skeleton and defers compose,
set_part/build_part validate each part in isolation, end_round composes once and
reports failed parts, abort_round discards the round. A single set_part OUTSIDE a
round still composes immediately (byte-compatible with Phase 2A)."""

import json
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

LID_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], 3)
    show(p.part, name="Lid")
"""

RAISES_PART = "from solidifai import show\ndef build(inputs):\n    raise ValueError('boom')\n"


def _mk(tmp_path) -> Session:
    root = tmp_path
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def test_begin_round_freezes_skeleton(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    r = s.begin_round()
    assert r["ok"] is True
    assert "frames" in r["skeleton"]  # returns the contract for fan-out
    # skeleton is frozen during a round
    blocked = s.set_skeleton(SKEL)
    assert blocked["ok"] is False and "round" in blocked["error"].lower()
    s.abort_round()
    assert s.set_skeleton(SKEL)["ok"] is True  # thawed


def test_round_defers_compose_then_composes_once(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    build_before = s.build_id
    s.begin_round()
    b = s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    assert b["ok"] is True and b["deferred"] is True and b["valid"] is True
    lid_res = s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])
    assert lid_res["deferred"] is True
    end = s.end_round()
    assert end["ok"] is True
    assert end.get("empty") is not True
    assert s.build_id == build_before + 1
    names = {o["name"] for o in s.get_model_info()["objects"]}
    assert {"base/Base", "lid/Lid"} <= names
    disk = json.loads((tmp_path / ".solidifai" / "artifacts" / "model.json").read_text())
    assert {o["name"] for o in disk["objects"]} >= {"base/Base", "lid/Lid"}


def test_failed_part_in_round_is_isolated_not_fatal(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.begin_round()
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    bad = s.set_part("oops", RAISES_PART, attach="base_frame", inputs=["body_w"])
    assert bad["ok"] is False and "boom" in bad["error"]  # this part failed
    end = s.end_round()
    # the good part still composed; the round reports which parts failed
    assert end["ok"] is True
    assert "oops" in end.get("failed", {})
    assert any(o["name"] == "base/Base" for o in s.get_model_info()["objects"])
    # the failed part left no trace (atomic per-part rollback)
    from solidifai_engine.assembly import manifest as m

    assert m.child_by_id(m.load_manifest(str(tmp_path)), "oops") is None
    assert not os.path.exists(tmp_path / "parts" / "oops.py")


def test_begin_round_requires_assembly(tmp_path):
    s = _mk(tmp_path)
    assert s.begin_round()["ok"] is False  # no skeleton yet


def test_begin_round_rejects_nested_round(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.begin_round()["ok"] is True
    again = s.begin_round()
    assert again["ok"] is False and "already" in again["error"].lower()


def test_end_round_without_round_is_error(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    assert s.end_round()["ok"] is False
    assert s.abort_round()["ok"] is False


def test_abort_round_removes_part_added_during_round(tmp_path):
    # Finding 7: a part written via set_part during a round must not survive an abort.
    from solidifai_engine.assembly import manifest as m

    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.begin_round()
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    assert not os.path.exists(tmp_path / "parts" / "base.py")
    assert m.child_by_id(m.load_manifest(str(tmp_path)), "base") is None
    assert s.abort_round()["ok"] is True
    # the source file and the manifest child are both gone
    assert not os.path.exists(tmp_path / "parts" / "base.py")
    assert m.child_by_id(m.load_manifest(str(tmp_path)), "base") is None


def test_abort_round_restores_edited_part_source(tmp_path):
    # Finding 7: editing an existing part during a round then aborting restores it.
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    original = (tmp_path / "parts" / "base.py").read_text(encoding="utf-8")
    s.begin_round()
    s.set_part("base", LID_PART, attach="base_frame", inputs=["body_w", "wall"])
    assert (tmp_path / "parts" / "base.py").read_text(encoding="utf-8") == original
    assert s.abort_round()["ok"] is True
    assert (tmp_path / "parts" / "base.py").read_text(encoding="utf-8") == original


def test_end_round_publishes_deferred_parts_without_empty_generation(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    before = json.loads((tmp_path / ".solidifai" / "artifacts" / "current.json").read_text())

    s.begin_round()
    assert s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])["ok"]
    assert s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])["ok"]

    end = s.end_round()

    assert end["ok"] is True
    assert end.get("empty") is not True
    current = json.loads((tmp_path / ".solidifai" / "artifacts" / "current.json").read_text())
    assert current["publicationId"] != before["publicationId"]
    model = json.loads((tmp_path / ".solidifai" / "artifacts" / "model.json").read_text())
    assert {o["name"] for o in model["objects"]} >= {"base/Base", "lid/Lid"}


def test_build_part_defers_in_round(tmp_path):
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_2FRAME)
    s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])
    s.begin_round()
    res = s.build_part("base")
    assert res["ok"] is True and res["deferred"] is True and res["valid"] is True


# -- Task 3: fan-out simulation + single-compose + byte-compat ---------------

# A four-frame skeleton so we can place four distinct parts in one round.
SKEL_4FRAME = """
from solidifai import skeleton
from build123d import Location
PARAMS = {"w": {"value": 40.0, "min": 10.0, "max": 100.0, "step": 1.0, "unit": "mm"}}
def build(w):
    s = skeleton()
    s.scalar("w", w)
    s.frame("f0", Location((0, 0, 0)))
    s.frame("f1", Location((60, 0, 0)))
    s.frame("f2", Location((0, 60, 0)))
    s.frame("f3", Location((60, 60, 0)))
    return s
"""


def _part_named(name: str, z: float = 3.0) -> str:
    return (
        "from solidifai import show\n"
        "from build123d import BuildPart, Box\n"
        "def build(inputs):\n"
        "    with BuildPart() as p:\n"
        f'        Box(inputs["w"], inputs["w"], {z})\n'
        f'    show(p.part, name="{name}")\n'
    )


def test_round_fan_out_composes_once(tmp_path):
    """Mimic subagents finishing out of order: author N=4 parts inside one round,
    then end_round. The whole round must render exactly once (build_id +1 total, not
    per part), and every part must be present in the model and the tree."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_4FRAME)
    s.begin_round()
    bid_before = s.build_id
    # arbitrary order, like four workers reporting back at different times
    plan = [("c2", "f2"), ("c0", "f0"), ("c3", "f3"), ("c1", "f1")]
    for cid, frame in plan:
        r = s.set_part(cid, _part_named(cid.upper()), attach=frame, inputs=["w"])
        assert r["ok"] is True and r["deferred"] is True
    # nothing rendered during the round: build_id is unchanged so far
    assert s.build_id == bid_before
    end = s.end_round()
    assert end["ok"] is True and end.get("failed") == {}
    # exactly one render happened for the whole round
    assert s.build_id == bid_before + 1
    names = {o["name"] for o in s.get_model_info()["objects"]}
    assert {"c0/C0", "c1/C1", "c2/C2", "c3/C3"} <= names
    tree_ids = {c["id"] for c in s.get_assembly_tree()["tree"]["children"]}
    assert tree_ids == {"c0", "c1", "c2", "c3"}


def test_round_handles_move_only_part(tmp_path):
    """A part authored in a round, then re-attached to a different frame (a move,
    not a rebuild), composes at the new frame after end_round."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_4FRAME)
    s.begin_round()
    s.set_part("c0", _part_named("C0"), attach="f0", inputs=["w"])
    s.end_round()
    # move it to f3 (attach is not part of the cache key, so this is a recompose)
    s.begin_round()
    moved = s.set_part("c0", _part_named("C0"), attach="f3", inputs=["w"])
    assert moved["deferred"] is True
    s.end_round()
    from solidifai_engine.assembly import manifest as m

    assert m.child_by_id(m.load_manifest(str(tmp_path)), "c0").attach == "f3"
    assert any(o["name"] == "c0/C0" for o in s.get_model_info()["objects"])


def test_single_set_part_outside_round_composes_immediately(tmp_path):
    """Byte-compat: outside any round a single set_part composes immediately and
    advances build_id by exactly 1 (Phase 2A behavior, unchanged)."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    bid_before = s.build_id
    res = s.set_part(
        "base",
        _part_named("Base").replace('inputs["w"]', 'inputs["w"]'),
        attach="base_frame",
        inputs=["w"],
    )
    assert res["ok"] is True
    assert "deferred" not in res  # not a round result
    assert res.get("buildId") == bid_before + 1  # composed immediately
    assert s.build_id == bid_before + 1
    assert any(o["name"] == "base/Base" for o in s.get_model_info()["objects"])


# -- C1: round-built parts are REUSED at end_round (no double work) ----------


def test_end_round_reuses_round_built_parts_zero_rebuilds(tmp_path, monkeypatch):
    """The proof for C1: parts built during the round must be cache HITS at
    end_round, so end_round runs ZERO additional part builds. Without reuse,
    end_round's compose re-ran every part from scratch (the round doubled work)."""
    from solidifai_engine.assembly import graph

    s = _mk(tmp_path)
    s.set_skeleton(SKEL_4FRAME)
    s.begin_round()
    for cid, frame in [("c0", "f0"), ("c1", "f1"), ("c2", "f2")]:
        assert s.set_part(cid, _part_named(cid.upper()), attach=frame, inputs=["w"])["ok"]

    # Count run_part calls during end_round only. If the round populated the cache
    # with the SAME keys the composer computes, end_round hits cache for all three
    # parts and never calls run_part.
    calls = {"n": 0}
    real_run_part = graph.runner.run_part

    def counting_run_part(*a, **k):
        calls["n"] += 1
        return real_run_part(*a, **k)

    monkeypatch.setattr(graph.runner, "run_part", counting_run_part)
    hits_before, misses_before = s._node_cache.hits, s._node_cache.misses
    end = s.end_round()
    assert end["ok"] is True

    assert calls["n"] == 0, "end_round re-ran parts from scratch; round work was wasted"
    # exactly three L1 cache hits (one per round-built part), zero new misses
    assert s._node_cache.hits - hits_before == 3
    assert s._node_cache.misses - misses_before == 0
    names = {o["name"] for o in s.get_model_info()["objects"]}
    assert {"c0/C0", "c1/C1", "c2/C2"} <= names


def test_round_runs_skeleton_once_not_per_part(tmp_path, monkeypatch):
    """The frozen skeleton is run once at begin_round and reused for every part in
    the round, not re-run per set_part."""
    from solidifai_engine.assembly import graph

    s = _mk(tmp_path)
    s.set_skeleton(SKEL_4FRAME)
    calls = {"n": 0}
    real_run_skeleton = graph.runner.run_skeleton

    def counting_run_skeleton(*a, **k):
        calls["n"] += 1
        return real_run_skeleton(*a, **k)

    monkeypatch.setattr(graph.runner, "run_skeleton", counting_run_skeleton)
    s.begin_round()
    base = calls["n"]  # the one run at begin_round
    for cid, frame in [("c0", "f0"), ("c1", "f1"), ("c2", "f2")]:
        s.set_part(cid, _part_named(cid.upper()), attach=frame, inputs=["w"])
    # the three set_parts reused the frozen skeleton: no extra runs per part
    assert calls["n"] == base


# -- I1: deferred-compose invariant is protected (no mid-round drift) --------


def test_mutators_refused_mid_round(tmp_path):
    """Every compose-triggering mutator is refused during a round, does not advance
    build_id, and does not drift params. Only set_part (the deferred path) is allowed."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL_4FRAME)
    s.set_part("c0", _part_named("C0"), attach="f0", inputs=["w"])  # a part to target
    s.begin_round()
    bid_before = s.build_id
    params_before = dict(s._param_values)

    blocked = [
        lambda: s.set_params({"w": 80.0}),
        lambda: s.attach("c0", "f1"),
        lambda: s.set_inputs("c0", ["w"]),
        lambda: s.remove_part("c0"),
        lambda: s.add_subassembly("sub", attach="f1"),
        lambda: s.set_part_material("c0", "steel"),
    ]
    for call in blocked:
        res = call()
        assert res["ok"] is False
        assert "round" in res["error"].lower()

    # nothing composed and no params drifted
    assert s.build_id == bid_before
    assert s._param_values == params_before
    # the one allowed mutation still works (deferred)
    assert s.set_part("c0", _part_named("C0"), attach="f0", inputs=["w"])["deferred"] is True


# -- I2: a stuck round is cleared on workspace re-open (startup) -------------


def test_startup_clears_stale_round(tmp_path):
    """A crashed orchestrator can leave a round active with no end_round. Re-opening
    the workspace (startup) must clear it so set_skeleton is not refused forever."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.begin_round()
    assert s._round["active"] is True
    assert s.set_skeleton(SKEL)["ok"] is False  # frozen while the round is open
    s.startup()  # re-open the workspace
    assert s._round.get("active") is False
    assert s.set_skeleton(SKEL)["ok"] is True  # thawed by the re-open


def test_get_model_info_round_active_flag(tmp_path):
    """round_active is visible at runtime so a stuck round can be diagnosed, but it
    must NOT be persisted into the on-disk model.json."""
    s = _mk(tmp_path)
    s.set_skeleton(SKEL)
    s.set_part("base", _part_named("Base"), attach="base_frame", inputs=["w"])
    assert s.get_model_info().get("round_active") is False
    s.begin_round()
    assert s.get_model_info().get("round_active") is True
    # the on-disk model.json never carries round state (single-model byte guarantee)
    import json

    from solidifai_engine import paths as _paths

    with open(_paths.json_path(s.artifacts_dir), encoding="utf-8") as f:
        disk = json.loads(f.read())
    assert "round_active" not in disk
