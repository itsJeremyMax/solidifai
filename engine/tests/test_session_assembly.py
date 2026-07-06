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


def test_is_assembly_mode_true_for_assembly_root(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    assert sess._is_assembly_mode() is True


def test_startup_builds_assembly_and_writes_model(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    assert sess.last_ok is True
    assert sess.build_id >= 1
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    ids = sorted(o["id"] for o in model["objects"])
    assert ids == ["base/base", "hinge/knuckle/knuckle", "hinge/pin/pin", "lid/lid"]
    assert sess._objects and len(sess._objects) == 4


def test_single_model_mode_unaffected(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(
        "from solidifai import show\nfrom build123d import Box\nshow(Box(10,10,10), name='B')\n",
        encoding="utf-8",
    )
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    sess = Session(str(artifacts), model_path=str(root / "model.py"))
    assert sess._is_assembly_mode() is False
    sess.startup()
    assert sess.last_ok is True


def test_assembly_params_surface_from_skeleton(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    block = sess.get_params()
    assert set(block["schema"]) == {"body_w", "body_h", "wall"}
    assert block["values"]["body_w"] == 60.0
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    assert set(model["params"]["schema"]) == {"body_w", "body_h", "wall"}


def test_set_params_rebuilds_assembly(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    b0 = sess.build_id
    res = sess.set_params({"body_w": 100.0})
    assert res["ok"] is True and res["buildId"] > b0
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    assert round(model["bbox"]["max"][0] - model["bbox"]["min"][0], 1) >= 100.0
    assert sess.get_params()["values"]["body_w"] == 100.0


def test_assembly_param_values_present_in_model_json_at_startup(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    # model.json params block must carry the actual default VALUES, not {}
    assert model["params"]["values"]["body_w"] == 60.0
    assert set(model["params"]["values"]) == {"body_w", "body_h", "wall"}


def test_saved_settings_apply_on_reopen(tmp_path):
    root, artifacts = _ws(tmp_path)
    sess = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess.startup()
    sess.set_params({"body_w": 90.0})  # persists settings.json
    # reopen: a fresh Session on the same root should load body_w=90
    sess2 = Session(str(artifacts), model_path=str(root / "assembly.json"))
    sess2.startup()
    assert sess2.get_params()["values"]["body_w"] == 90.0
