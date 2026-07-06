import json

from solidifai_engine import settings
from solidifai_engine.session import Session

PARAM_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {"size": {"value": 20.0, "min": 5.0, "max": 100.0, "step": 1.0, "unit": "mm"}}

def build(size):
    with BuildPart() as p:
        Box(size, size, size)
    show(p.part, name="B")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


def _ws(tmp_path):
    """A workspace layout: <root>/model.py + <root>/.solidifai/artifacts."""
    root = tmp_path
    model = root / "model.py"
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    return root, model, artifacts


def test_execute_script_writes_settings_json(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(model))
    sess.execute_script(PARAM_SCRIPT)
    assert settings.load_params(str(root)) == {"size": 20.0}


def test_set_params_writes_settings_json(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(model))
    sess.execute_script(PARAM_SCRIPT)

    sess.set_params({"size": 42.0})
    assert settings.load_params(str(root)) == {"size": 42.0}


def test_startup_applies_saved_values_over_defaults(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    settings.write_params(str(root), {"size": 73.0})

    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()

    info = json.loads((artifacts / "model.json").read_text())
    assert info["params"]["values"]["size"] == 73.0


def test_startup_ignores_unknown_saved_keys(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    settings.write_params(str(root), {"size": 60.0, "removed_param": 5.0})

    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()  # must not raise on the stale key

    info = json.loads((artifacts / "model.json").read_text())
    assert info["params"]["values"]["size"] == 60.0
    assert "removed_param" not in info["params"]["values"]


def test_build_auto_commits_and_undo_reverts_params(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()  # initial commit (size=20 default)

    sess.set_params({"size": 80.0})  # one discrete action -> one commit
    import time

    time.sleep(0.8)  # exceed the coalesce window
    sess.set_params({"size": 81.0})

    res = sess.undo()
    assert res["ok"] is True
    info = json.loads((artifacts / "model.json").read_text())
    assert info["params"]["values"]["size"] == 80.0


def test_reopen_does_not_add_a_commit(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess1 = Session(str(artifacts), model_path=str(model))
    sess1.startup()
    sess1.set_params({"size": 55.0})
    import time

    time.sleep(0.8)
    n_before = len(sess1.history.entries())

    sess2 = Session(str(artifacts), model_path=str(model))
    sess2.startup()  # reopen
    assert len(sess2.history.entries()) == n_before


def test_history_method_shape(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()
    out = sess.history_state()
    assert "entries" in out and "index" in out
    assert out["entries"][out["index"]]["current"] is True


def test_undo_with_no_history_is_clean_error(tmp_path):
    # Bare session (no model_path) has no history; undo must not crash.
    sess = Session(str(tmp_path))
    res = sess.undo()
    assert res["ok"] is False
    assert "history" in res["error"]


def test_checkpoint_labels_current_commit(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()
    sess.checkpoint("milestone")
    entries = sess.history.entries()
    assert entries[-1]["message"] == "milestone"
    assert entries[-1]["current"] is True


def test_commit_failure_does_not_fail_build(tmp_path, monkeypatch):
    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sess.history, "commit", boom)
    res = sess.set_params({"size": 30.0})
    assert res["ok"] is True  # build succeeds despite the auto-commit failing


def test_checkpoint_refuses_mid_undo_and_keeps_redo(tmp_path):
    import time

    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()
    sess.set_params({"size": 40.0})
    time.sleep(0.8)
    sess.set_params({"size": 50.0})  # init, 40, 50
    sess.undo()  # back to 40; redo available
    n = len(sess.history.entries())
    res = sess.checkpoint("label")
    assert res["ok"] is False
    assert sess.history.can_redo() is True  # redo stack preserved
    assert len(sess.history.entries()) == n  # no new commit added


def test_restore_rebuild_failure_returns_clean_error(tmp_path, monkeypatch):
    import time

    root, model, artifacts = _ws(tmp_path)
    model.write_text(PARAM_SCRIPT)
    sess = Session(str(artifacts), model_path=str(model))
    sess.startup()
    sess.set_params({"size": 60.0})
    time.sleep(0.8)
    sess.set_params({"size": 70.0})
    monkeypatch.setattr(
        sess, "run_file", lambda *a, **k: {"ok": False, "error": "x", "traceback": "t"}
    )
    res = sess.undo()
    assert res["ok"] is False
    assert "traceback" not in res  # no internal traceback leaked
    assert res["error"] == "could not rebuild the restored model state"
