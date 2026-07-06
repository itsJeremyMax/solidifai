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


def test_set_material_on_assembly_part(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    res = sess.set_part_material("hinge/pin/pin", "aluminum")
    assert res.get("ok") is not False  # not rejected as an unknown id
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    pin = next(o for o in model["objects"] if o["id"] == "hinge/pin/pin")
    assert pin["appearance"]["material"] == "aluminum"


def test_unknown_assembly_part_id_rejected(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    res = sess.set_part_material("hinge/pin/nope", "aluminum")
    assert res["ok"] is False
