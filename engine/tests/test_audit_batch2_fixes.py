"""Second adversarial-audit batch: worker crash-isolation, history transactionality,
assembly/single split-brain, param validation, and mirrored-diff correctness.

Each test reproduces a concrete failure the audit found and pins the fix:
  1. a poisoned on-disk part after a native crash no longer bricks the workspace
  2. a legal build slower than the spawn-ready budget can still be reloaded
  3. a failed undo/redo leaves the timeline and disk untouched (no cursor drift)
  4. execute_script/run_file are refused on an assembly workspace
  5. set_params validates against the schema (bool/unknown/out-of-range rejected)
  7. set_params refuses after an out-of-band model.py edit
  8. diff_against reports the true (per-solid) volume for mirrored geometry
"""

import os

import pytest

from solidifai_engine.session import Session
from solidifai_engine.worker import _STARTUP_SENTINEL, KernelCrash, SessionProxy

# -- fixtures ---------------------------------------------------------------

SKEL = (
    "from solidifai import skeleton\n"
    "PARAMS = {'w': {'value': 20, 'min': 5, 'max': 60}}\n"
    "def build(w=20):\n"
    "    sk = skeleton()\n"
    "    sk.scalar('w', w)\n"
    "    return sk\n"
)
GOOD_PART = (
    "from build123d import Box\n"
    "from solidifai import show\n"
    "def build(inputs):\n"
    "    show(Box(inputs.get('w', 20), 10, 5), name='beam')\n"
)
# os._exit is uncatchable: kills the worker mid-build exactly like an OCC SIGSEGV.
CRASH_PART = "import os\nos._exit(139)\n"

CUBE = (
    "from build123d import Box\n"
    "from solidifai import show\n"
    "PARAMS = {'size': {'value': 10, 'min': 5, 'max': 50}, 'tag': {'value': 'a'}}\n"
    "def build(size=10, tag='a'):\n"
    "    show(Box(size, size, size), name='cube')\n"
    "build(**{k: v['value'] for k, v in PARAMS.items()})\n"
)


def _session(tmp_path) -> Session:
    (tmp_path / ".solidifai").mkdir(exist_ok=True)
    art = str(tmp_path / ".solidifai" / "artifacts")
    return Session(art, model_path=str(tmp_path / "model.py"))


# -- Finding 1: a poisoned part after a native crash must not brick the ws ----


def test_native_crash_in_set_part_rolls_back_and_workspace_keeps_serving(tmp_path):
    (tmp_path / ".solidifai").mkdir()
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"), model_path=str(tmp_path / "model.py")
    )
    try:
        assert proxy.set_skeleton(SKEL)["ok"] is True
        with pytest.raises(KernelCrash) as exc:
            proxy.set_part("pin", CRASH_PART)
        assert "rolled back" in str(exc.value)

        # The poisoned source + manifest entry are gone (parent-side rollback), so a
        # respawned worker rebuilds a clean model on startup instead of crashing.
        assert not (tmp_path / "parts" / "pin.py").exists()
        # The workspace still serves RPCs -- the whole point of the fix.
        assert isinstance(proxy.get_model_info(), dict)
        # And a subsequent good part builds.
        assert proxy.set_part("pin", GOOD_PART, inputs=["w"])["ok"] is True
    finally:
        proxy.close()


def test_startup_sentinel_recovers_a_workspace_that_crashes_during_startup(tmp_path):
    # A model.py that natively crashes when run. Startup runs it before "ready",
    # so the first spawn dies in startup; the sentinel it wrote survives the native
    # crash and the next spawn comes up model-less-but-serving instead of looping.
    (tmp_path / ".solidifai").mkdir()
    art = tmp_path / ".solidifai" / "artifacts"
    (tmp_path / "model.py").write_text(CRASH_PART, encoding="utf-8")
    proxy = SessionProxy(str(art), model_path=str(tmp_path / "model.py"))
    try:
        with pytest.raises(KernelCrash):
            proxy.start()  # first spawn: writes sentinel, startup crashes natively
        assert (art / _STARTUP_SENTINEL).exists()  # marker survived the crash

        # Next spawn sees the marker, skips the reload, and serves.
        assert isinstance(proxy.get_model_info(), dict)
        assert not (art / _STARTUP_SENTINEL).exists()  # cleared for a later reopen
    finally:
        proxy.close()


# -- Finding 2: startup budget must cover a legal build -----------------------


def test_slow_startup_build_within_budget_survives_respawn(tmp_path):
    # A model that legally builds slower than the (small) spawn-ready override but
    # well under the build timeout. Before the fix the respawn timed out at the
    # ready budget forever; now the effective budget is at least the build timeout.
    (tmp_path / ".solidifai").mkdir()
    (tmp_path / "model.py").write_text(
        "import time\n"
        "from build123d import Box\n"
        "from solidifai import show\n"
        "time.sleep(2)\n"
        "show(Box(10, 10, 10), name='a')\n",
        encoding="utf-8",
    )
    proxy = SessionProxy(
        str(tmp_path / ".solidifai" / "artifacts"),
        model_path=str(tmp_path / "model.py"),
        timeout=10.0,
        start_timeout=1.0,  # smaller than the 2s build: the old bug's trigger
    )
    try:
        # The effective startup budget never drops below the per-build timeout.
        assert proxy._start_timeout >= proxy._timeout
        proxy.start()
        proxy._teardown()  # simulate any worker death (crash / timeout / app restart)
        assert proxy.get_model_info()["valid"] is True  # respawn reloaded the model
    finally:
        proxy.close()


# -- Finding 3: a failed undo/redo/goto must not move the timeline or disk -----


def test_failed_undo_leaves_timeline_and_disk_untouched(tmp_path):
    s = _session(tmp_path)
    s.startup()
    asset = tmp_path / "dep.txt"
    asset.write_text("x", encoding="utf-8")
    dep = (
        "from build123d import Box\n"
        "from solidifai import show\n"
        f"open({str(asset)!r}).read()\n"
        "def build():\n"
        "    show(Box(10, 10, 10), name='a')\n"
        "build()\n"
    )
    good = (
        "from build123d import Box\n"
        "from solidifai import show\n"
        "def build():\n"
        "    show(Box(12, 12, 12), name='c')\n"
        "build()\n"
    )
    assert s.execute_script(dep)["ok"] is True
    assert s.execute_script(good)["ok"] is True
    idx_before = s.history.index
    ncommits = len(s.history.commits)
    disk_before = (tmp_path / "model.py").read_text(encoding="utf-8")

    asset.unlink()  # now the older state (dep) can no longer rebuild

    r1 = s.undo()
    assert r1["ok"] is False
    assert s.history.index == idx_before, "failed undo drifted the cursor"
    assert (tmp_path / "model.py").read_text(encoding="utf-8") == disk_before
    assert len(s.history.commits) == ncommits, "redo stack was mutated"
    assert not list(tmp_path.glob("model.py.tmp")), "left a temp file behind"

    # A second attempt must fail identically -- no accumulating drift.
    r2 = s.undo()
    assert r2["ok"] is False
    assert s.history.index == idx_before
    assert (tmp_path / "model.py").read_text(encoding="utf-8") == disk_before


def test_successful_undo_still_restores(tmp_path):
    # The transactional wrapper must not break the normal (rebuildable) path.
    s = _session(tmp_path)
    s.startup()
    v1 = (
        "from build123d import Box\nfrom solidifai import show\n"
        "def build():\n    show(Box(10, 10, 10), name='a')\nbuild()\n"
    )
    v2 = v1.replace("10, 10, 10", "20, 20, 20")
    assert s.execute_script(v1)["ok"] is True
    assert s.execute_script(v2)["ok"] is True
    assert s.undo()["ok"] is True
    assert "10, 10, 10" in (tmp_path / "model.py").read_text(encoding="utf-8")
    assert s.redo()["ok"] is True
    assert "20, 20, 20" in (tmp_path / "model.py").read_text(encoding="utf-8")


# -- Finding 4: execute_script/run_file refused in assembly mode --------------


def test_execute_script_refused_in_assembly_mode(tmp_path):
    s = _session(tmp_path)
    s.startup()
    assert s.set_skeleton(SKEL)["ok"] is True
    assert s.set_part("beam", GOOD_PART, inputs=["w"])["ok"] is True
    before = [o["id"] for o in s.get_model_info()["objects"]]

    script = (
        "from build123d import Cylinder\nfrom solidifai import show\n"
        "def build():\n    show(Cylinder(4, 30), name='rod')\nbuild()\n"
    )
    r = s.execute_script(script)
    assert r["ok"] is False
    assert "set_part" in r["error"] and "assembly" in r["error"]
    # The assembly is intact -- no split-brain.
    assert [o["id"] for o in s.get_model_info()["objects"]] == before

    (tmp_path / "loose.py").write_text(script, encoding="utf-8")
    rf = s.run_file(str(tmp_path / "loose.py"))
    assert rf["ok"] is False and "set_part" in rf["error"]


# -- Finding 5: set_params schema validation ----------------------------------


def test_set_params_rejects_bool_unknown_and_out_of_range(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(CUBE)["ok"] is True

    r_bool = s.set_params({"size": True})
    assert r_bool["ok"] is False and "number" in r_bool["error"]
    # The rejected value never built and never entered the reported params.
    assert s.get_params()["values"]["size"] == 10.0

    r_unknown = s.set_params({"nope": 3})
    assert r_unknown["ok"] is False and "unknown parameter" in r_unknown["error"]

    r_range = s.set_params({"size": 999})
    assert r_range["ok"] is False and "out of range" in r_range["error"]

    # A valid numeric change still works; a declared non-numeric (string) is allowed.
    assert s.set_params({"size": 20})["ok"] is True
    assert s.get_params()["values"]["size"] == 20.0
    assert s.set_params({"tag": "b"})["ok"] is True


# -- Finding 7: set_params after an out-of-band model.py edit -----------------


def test_set_params_refuses_after_out_of_band_edit(tmp_path):
    s = _session(tmp_path)
    assert s.execute_script(CUBE)["ok"] is True

    # Someone edits model.py directly (not through the engine).
    (tmp_path / "model.py").write_text(
        CUBE.replace("Box(size, size, size)", "Box(size, size, size * 2)"),
        encoding="utf-8",
    )
    r = s.set_params({"size": 20})
    assert r["ok"] is False and "run_file" in r["error"]

    # Reloading via run_file reconciles disk and memory, then set_params works.
    assert s.run_file(str(tmp_path / "model.py"))["ok"] is True
    assert s.set_params({"size": 20})["ok"] is True


# -- Finding 8: diff_against reports true per-solid volume for mirrors ---------


def test_diff_against_reports_true_mirrored_volume(tmp_path):
    s = _session(tmp_path)
    s.startup()
    single = (
        "from solidifai import show\nfrom build123d import Pos, Box\n"
        "def build():\n    show(Pos(-20, 0, 0) * Box(10, 10, 10), name='left')\nbuild()\n"
    )
    mirrored = (
        "from solidifai import show\nfrom build123d import Pos, Box, mirror, Plane\n"
        "def build():\n"
        "    left = Pos(-20, 0, 0) * Box(10, 10, 10)\n"
        "    show(left, name='left')\n"
        "    show(mirror(left, Plane.YZ), name='right')\n"
        "build()\n"
    )
    assert s.execute_script(single)["ok"] is True  # checkpoint index 0
    assert s.execute_script(mirrored)["ok"] is True  # current: mirror pair

    r = s.diff_against(0)
    assert r["ok"] is True
    # Two 1000mm^3 solids, one mirrored (negative determinant). The compound's own
    # signed volume cancels to ~0; per-solid aggregation reports the true 2000.
    assert r["currentVolume"] == pytest.approx(2000.0, rel=1e-3)
    assert r["checkpointVolume"] == pytest.approx(1000.0, rel=1e-3)
