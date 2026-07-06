import os
import shutil

from solidifai_engine.history import History

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def test_history_stages_assembly_fileset(tmp_path):
    root = tmp_path / "ws"
    shutil.copytree(FIXTURE, root)
    (root / ".solidifai").mkdir()
    (root / "settings.json").write_text('{"schema":1,"params":{}}\n', encoding="utf-8")
    h = History(str(root))
    h.ensure()
    sha = h.commit("init", amend=False)
    assert sha is not None
    tracked = set(h._tracked_paths())
    assert "assembly.json" in tracked
    assert "skeleton.py" in tracked
    assert "parts/base.py" in tracked
    assert "hinge/assembly.json" in tracked
    assert "hinge/parts/pin.py" in tracked
