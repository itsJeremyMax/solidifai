import json
import os

from solidifai_engine.assembly import build

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "assembly_enclosure")


def test_nested_enclosure_builds_all_four_parts(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    res = build.build_workspace(FIXTURE, str(artifacts), build_id=1)
    assert res["ok"] is True
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    ids = sorted(o["id"] for o in model["objects"])
    assert ids == ["base/base", "hinge/knuckle/knuckle", "hinge/pin/pin", "lid/lid"]
    # the steel pin carries its material through composition
    pin = next(o for o in model["objects"] if o["id"] == "hinge/pin/pin")
    assert pin["appearance"]["material"] == "steel"


def test_param_change_rebuilds_assembly(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    build.build_workspace(FIXTURE, str(artifacts), build_id=1)
    res = build.build_workspace(FIXTURE, str(artifacts), build_id=2, params={"body_w": 100.0})
    assert res["buildId"] == 2
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    assert round(model["bbox"]["max"][0] - model["bbox"]["min"][0], 1) >= 100.0
