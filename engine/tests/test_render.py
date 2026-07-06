import json
import os

import pytest
from build123d import Box

from solidifai import reset_registry, show
from solidifai_engine import render as render_mod
from solidifai_engine.render import render_to


def setup_function():
    reset_registry()


def test_render_writes_glb_and_json(tmp_path):
    show(Box(20, 20, 20), name="Bracket")

    result = render_to(str(tmp_path), build_id=1)
    assert result["ok"] is True

    glb_path = tmp_path / "model.glb"
    json_path = tmp_path / "model.json"
    assert glb_path.exists()
    assert json_path.exists()

    with open(glb_path, "rb") as f:
        assert f.read(4) == b"glTF"

    data = json.loads(json_path.read_text())
    assert data["schema"] == 2
    assert data["buildId"] == 1
    assert data["objects"][0]["name"] == "Bracket"
    assert data["bbox"]["size"] is not None
    assert len(data["bbox"]["size"]) == 3
    assert data["valid"] is True

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_default_object_gets_pla_appearance(tmp_path):
    show(Box(20, 20, 20), name="Bracket")
    render_to(str(tmp_path), build_id=7)

    data = json.loads((tmp_path / "model.json").read_text())
    obj = data["objects"][0]
    ap = obj["appearance"]
    assert ap["material"] == "pla"
    assert ap["metalness"] == 0.0
    assert len(ap["baseColor"]) == 3
    assert obj["mass"]["material"] == "PLA"
    assert obj["mass"]["density"] == 1.24
    assert obj["mass"]["value"] > 0
    # uniform build → build-level mass names the single material
    assert data["mass"]["material"] == "PLA"
    assert data["mass"]["value"] == obj["mass"]["value"]


def test_mixed_materials_order_and_aggregate(tmp_path):
    show(Box(20, 20, 20), name="Body", material="aluminum")
    show(Box(10, 10, 10), name="Pin", material="steel")
    render_to(str(tmp_path), build_id=8)

    data = json.loads((tmp_path / "model.json").read_text())
    objs = data["objects"]
    # appearance order matches show() / registry order
    assert objs[0]["appearance"]["material"] == "aluminum"
    assert objs[1]["appearance"]["material"] == "steel"
    # per-object mass uses each material's density
    assert objs[0]["mass"]["density"] == 2.70
    assert objs[1]["mass"]["density"] == 7.85
    # build-level mass is the sum, labeled "mixed"
    assert data["mass"]["material"] == "mixed"
    assert data["mass"]["density"] == 0
    total = round(objs[0]["mass"]["value"] + objs[1]["mass"]["value"], 4)
    assert data["mass"]["value"] == total


def test_unknown_material_fails_build_without_touching_last_good(tmp_path):
    # Seed a last-good build.
    show(Box(20, 20, 20), name="Good")
    render_to(str(tmp_path), build_id=1)
    good = (tmp_path / "model.json").read_text()

    reset_registry()
    show(Box(10, 10, 10), name="Bad", material="unobtainium")
    with pytest.raises(ValueError):
        render_to(str(tmp_path), build_id=2)

    # last-good json untouched; no temp leftovers
    assert (tmp_path / "model.json").read_text() == good
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_node_ids_are_collision_safe():
    from solidifai_engine.render import _node_ids

    class Obj:  # minimal stand-in with a .name
        def __init__(self, name):
            self.name = name

    ids = _node_ids([Obj("Bracket"), Obj("Bracket"), Obj("Pin")])
    assert ids == ["bracket", "bracket_1", "pin"]


def test_override_changes_a_parts_material(tmp_path):
    show(Box(20, 20, 20), name="Bracket", material="pla")
    show(Box(10, 10, 10), name="Pin", material="pla")

    render_to(str(tmp_path), 1, overrides={"bracket": "aluminum"})

    model = json.loads((tmp_path / "model.json").read_text())
    by_id = {o["id"]: o for o in model["objects"]}
    assert by_id["bracket"]["appearance"]["material"] == "aluminum"
    assert by_id["pin"]["appearance"]["material"] == "pla"


def test_override_for_unknown_id_is_ignored(tmp_path):
    show(Box(20, 20, 20), name="Bracket", material="pla")

    render_to(str(tmp_path), 1, overrides={"ghost": "aluminum"})

    model = json.loads((tmp_path / "model.json").read_text())
    assert model["objects"][0]["appearance"]["material"] == "pla"


def test_failure_after_tessellation_keeps_last_good_artifacts(tmp_path, monkeypatch):
    # First, a successful render establishes last-good artifacts.
    show(Box(20, 20, 20), name="Bracket")
    render_to(str(tmp_path), build_id=1)

    glb_path = tmp_path / "model.glb"
    json_path = tmp_path / "model.json"
    good_glb = glb_path.read_bytes()
    good_json = json_path.read_bytes()

    # A second render fails AFTER tessellation but BEFORE the replaces.
    def boom(*args, **kwargs):
        raise RuntimeError("properties exploded")

    monkeypatch.setattr(render_mod, "properties", boom)

    reset_registry()
    show(Box(40, 40, 40), name="Bracket")
    with pytest.raises(RuntimeError, match="properties exploded"):
        render_to(str(tmp_path), build_id=2)

    # (a) live artifacts are byte-for-byte unchanged
    assert glb_path.read_bytes() == good_glb
    assert json_path.read_bytes() == good_json

    # (b) no temp files left behind
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
