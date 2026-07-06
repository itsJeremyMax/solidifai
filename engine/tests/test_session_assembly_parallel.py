import json
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


def test_cold_assembly_build_correct_with_parallel_warm(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    assert sess.last_ok is True
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    ids = sorted(o["id"] for o in model["objects"])
    assert ids == ["base/base", "hinge/knuckle/knuckle", "hinge/pin/pin", "lid/lid"]
    s2 = Session(str(artifacts), model_path=str(root / "assembly.json"))
    s2.startup()
    assert s2._disk_cache.hits >= 4
