import json

from solidifai_engine import paths, settings
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


def test_session_notifies_publishing_immediately_before_committing_pointer(tmp_path):
    _root, model, artifacts = _ws(tmp_path)
    observed = []
    sess = Session(
        str(artifacts),
        model_path=str(model),
        on_publishing=lambda: observed.append(paths.read_current_publication(str(artifacts))),
    )

    result = sess.execute_script(PARAM_SCRIPT)

    assert result["ok"] is True
    assert observed == [None]
    assert paths.read_current_publication(str(artifacts)) is not None


def test_failed_stage_never_reports_publishing(tmp_path, monkeypatch):
    _root, model, artifacts = _ws(tmp_path)
    published = []
    sess = Session(
        str(artifacts), model_path=str(model), on_publishing=lambda: published.append(True)
    )

    monkeypatch.setattr(
        "solidifai_engine.render.paths.stage_publication",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("stage failed")),
    )

    result = sess.execute_script(PARAM_SCRIPT)

    assert result["ok"] is False
    assert published == []


def test_failure_after_pointer_commit_keeps_the_publishing_notification(tmp_path, monkeypatch):
    _root, model, artifacts = _ws(tmp_path)
    published = []
    sess = Session(
        str(artifacts), model_path=str(model), on_publishing=lambda: published.append(True)
    )
    commit = paths.commit_publication

    def commit_then_fail(*args, **kwargs):
        commit(*args, **kwargs)
        raise OSError("mirror failed after pointer commit")

    monkeypatch.setattr("solidifai_engine.render.paths.commit_publication", commit_then_fail)

    result = sess.execute_script(PARAM_SCRIPT)

    assert result["ok"] is False
    assert published == [True]
    assert paths.read_current_publication(str(artifacts)) is not None


def test_set_params_writes_settings_json(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(model))
    sess.execute_script(PARAM_SCRIPT)

    sess.set_params({"size": 42.0})
    assert settings.load_params(str(root)) == {"size": 42.0}
    pointer = paths.read_current_publication(str(artifacts))
    assert pointer is not None
    generation = artifacts / "generations" / pointer.publication_id
    assert json.loads((generation / "inputs" / "settings.json").read_text())["params"] == {
        "size": 42.0
    }


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


def test_source_publication_failure_keeps_last_good_session_state(tmp_path, monkeypatch):
    root, model, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(model))
    assert sess.execute_script(PARAM_SCRIPT)["ok"] is True
    prior_objects = sess._objects
    prior_model = sess._model
    prior_hash = sess._model_hash
    prior_build = sess.build_id
    prior_source = model.read_text()
    original = paths.atomic_finalize

    def fail_source(tmp, final):
        if final == str(model):
            raise OSError("source disk full")
        original(tmp, final)

    monkeypatch.setattr(paths, "atomic_finalize", fail_source)
    result = sess.execute_script(PARAM_SCRIPT.replace("20.0", "30.0"))

    assert result["ok"] is True
    assert sess.build_id == prior_build + 1
    assert sess._objects is not prior_objects
    assert sess._model is not prior_model
    assert sess._model_hash != prior_hash
    assert model.read_text() == prior_source
    monkeypatch.setattr(paths, "atomic_finalize", original)
    paths.recover_publication(str(artifacts))
    assert model.read_text() != prior_source


def test_model_metadata_and_conformance_bind_to_publication_source_hash(tmp_path):
    root, model, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(model))
    result = sess.execute_script(PARAM_SCRIPT)

    metadata = json.loads((artifacts / "model.json").read_text())
    pointer = json.loads((artifacts / "current.json").read_text())
    assert metadata["publicationId"] == result["publicationId"] == pointer["publicationId"]
    assert metadata["sourceHash"] == sess._model_hash == pointer["sourceHash"]
    assert sess._persistence_evidence() is True
