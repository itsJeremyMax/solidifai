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


def test_full_assembly_lifecycle(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    assert sess.last_ok is True
    # params surfaced
    assert sess.get_params()["values"]["body_w"] == 60.0
    # rebuild on param change
    sess.set_params({"body_w": 100.0})
    # material on a nested part by path id
    sess.set_part_material("hinge/knuckle/knuckle", "aluminum")
    # history has commits and tracks the assembly
    assert sess.history is not None and sess.history.enabled()
    assert len(sess.history.commits) >= 1
    # reopen: saved param persists
    sess2 = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess2.startup()
    assert sess2.get_params()["values"]["body_w"] == 100.0
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    knuckle = next(o for o in model["objects"] if o["id"] == "hinge/knuckle/knuckle")
    assert (
        knuckle["appearance"]["material"] == "aluminum"
        or sess2._material_overrides.get("hinge/knuckle/knuckle") == "aluminum"
    )
