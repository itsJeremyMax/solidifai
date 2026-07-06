"""Assembly undo/redo/goto are now SUPPORTED (Phase 4): they restore the whole
recursive fileset and rebuild. The only remaining refusal is mid-round, which
keeps the deferred-compose round internally consistent.

(Earlier phases refused assembly undo/redo entirely; this file now guards the
supported behavior plus the round refusal.)
"""

import os
import shutil

from solidifai_engine.session import Session

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def _ws(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(FIXTURE, root)
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    return root, artifacts


def _sess(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    return sess


def test_assembly_undo_redo_supported(tmp_path):
    sess = _sess(tmp_path)
    before = sess.get_model_info()["bbox"]["size"]
    sess.set_params({"body_w": 90.0})  # widen, creating a second commit
    widened = sess.get_model_info()["bbox"]["size"]
    assert widened != before
    res = sess.undo()
    assert res["ok"] is True
    assert sess.get_model_info()["bbox"]["size"] == before
    res = sess.redo()
    assert res["ok"] is True
    assert sess.get_model_info()["bbox"]["size"] == widened


def test_assembly_goto_supported(tmp_path):
    sess = _sess(tmp_path)
    before = sess.get_model_info()["bbox"]["size"]
    sess.set_params({"body_w": 90.0})
    res = sess.goto(0)
    assert res["ok"] is True
    assert sess.get_model_info()["bbox"]["size"] == before


def test_undo_refused_during_round_without_history_mutation(tmp_path):
    sess = _sess(tmp_path)
    sess.set_params({"body_w": 90.0})  # ensure there is somewhere to undo
    sess.begin_round()
    commits_before = list(sess.history.commits)
    index_before = sess.history.index
    res = sess.undo()
    assert res["ok"] is False and "round" in res["error"].lower()
    # the refused undo did not move history
    assert list(sess.history.commits) == commits_before
    assert sess.history.index == index_before
    sess.abort_round()


def test_redo_refused_during_round(tmp_path):
    sess = _sess(tmp_path)
    sess.begin_round()
    res = sess.redo()
    assert res["ok"] is False and "round" in res["error"].lower()
    sess.abort_round()


def test_goto_refused_during_round(tmp_path):
    sess = _sess(tmp_path)
    sess.set_params({"body_w": 90.0})
    sess.begin_round()
    res = sess.goto(0)
    assert res["ok"] is False and "round" in res["error"].lower()
    sess.abort_round()
