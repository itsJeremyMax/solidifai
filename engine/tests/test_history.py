from solidifai_engine.history import History


def _repo(tmp_path):
    root = str(tmp_path)
    (tmp_path / ".solidifai").mkdir()
    (tmp_path / "model.py").write_text("# v0\n")
    (tmp_path / "settings.json").write_text('{"schema":1,"params":{}}\n')
    h = History(root)
    h.ensure()
    return tmp_path, h


def test_ensure_inits_repo_and_writes_gitignore(tmp_path):
    tmp, h = _repo(tmp_path)
    assert h.enabled()
    assert (tmp / ".git").is_dir()
    assert (tmp / ".gitignore").read_text().startswith("# solidifai-managed")


def test_commit_appends_to_timeline(tmp_path):
    tmp, h = _repo(tmp_path)
    sha = h.commit("init", amend=False)
    assert sha is not None
    assert h.commits == [sha]
    assert h.index == 0


def test_undo_redo_restore_file_contents(tmp_path):
    tmp, h = _repo(tmp_path)
    h.commit("v0", amend=False)
    (tmp / "model.py").write_text("# v1\n")
    h.commit("v1", amend=False)

    assert h.undo() is True
    assert (tmp / "model.py").read_text() == "# v0\n"
    assert h.index == 0

    assert h.redo() is True
    assert (tmp / "model.py").read_text() == "# v1\n"
    assert h.index == 1


def test_amend_replaces_tip_not_append(tmp_path):
    tmp, h = _repo(tmp_path)
    h.commit("v0", amend=False)
    (tmp / "model.py").write_text("# v1\n")
    first = h.commit("v1", amend=False)
    (tmp / "model.py").write_text("# v1b\n")
    amended = h.commit("v1b", amend=True)

    assert len(h.commits) == 2  # tip replaced, not appended
    assert h.commits[-1] == amended
    assert amended != first


def test_new_edit_after_undo_truncates_redo(tmp_path):
    tmp, h = _repo(tmp_path)
    h.commit("v0", amend=False)
    (tmp / "model.py").write_text("# v1\n")
    h.commit("v1", amend=False)
    h.undo()  # back to v0

    (tmp / "model.py").write_text("# v2\n")
    h.commit("v2", amend=False)  # new edit from v0

    assert h.index == 1
    assert len(h.commits) == 2  # v1 dropped from the line
    assert h.can_redo() is False


def test_entries_report_message_and_current(tmp_path):
    tmp, h = _repo(tmp_path)
    h.commit("first", amend=False)
    (tmp / "model.py").write_text("# v1\n")
    h.commit("second", amend=False)

    entries = h.entries()
    assert [e["message"] for e in entries] == ["first", "second"]
    assert entries[-1]["current"] is True
    assert entries[0]["current"] is False


def test_rebuild_timeline_when_history_json_missing(tmp_path):
    tmp, h = _repo(tmp_path)
    h.commit("v0", amend=False)
    (tmp / "model.py").write_text("# v1\n")
    h.commit("v1", amend=False)

    (tmp / ".solidifai" / "history.json").unlink()
    h2 = History(str(tmp))
    h2.ensure()  # rebuilds from git log
    assert len(h2.commits) == 2
    assert h2.index == 1


def test_fresh_repo_defaults_to_main_branch(tmp_path):
    from dulwich.repo import Repo

    tmp, h = _repo(tmp_path)  # _repo() runs History.ensure() on a fresh dir
    h.commit("v0", amend=False)  # first commit creates the default branch

    repo = Repo(str(tmp))
    assert repo.refs.read_ref(b"HEAD") == b"ref: refs/heads/main"
    keys = repo.refs.keys()
    assert b"refs/heads/main" in keys
    assert b"refs/heads/master" not in keys


def test_restore_removes_file_absent_in_target_snapshot(tmp_path):
    tmp, h = _repo(tmp_path)
    # Commit a snapshot that LACKS settings.json...
    (tmp / "settings.json").unlink()
    h.commit("no-settings", amend=False)
    # ...then a later snapshot that HAS it.
    (tmp / "settings.json").write_text('{"schema":1,"params":{"x":1}}\n')
    h.commit("with-settings", amend=False)
    # Undo back to the snapshot without settings.json -> on-disk file must be gone.
    assert h.undo() is True
    assert not (tmp / "settings.json").exists()
