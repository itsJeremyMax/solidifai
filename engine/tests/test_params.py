import json

from solidifai_engine.session import Session

PARAM_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {"size": {"value": 10, "min": 2, "max": 40, "step": 1, "unit": "mm"}}

def build(size):
    with BuildPart() as p:
        Box(size, size, size)
    show(p.part, name="Cube")
"""


def test_get_params_after_execute(tmp_path):
    sess = Session(str(tmp_path))
    res = sess.execute_script(PARAM_SCRIPT)
    assert res["ok"] is True

    params = sess.get_params()
    assert "schema" in params
    assert "values" in params
    assert params["schema"]["size"]["min"] == 2
    assert params["schema"]["size"]["max"] == 40
    assert params["values"]["size"] == 10

    data = json.loads((tmp_path / "model.json").read_text())
    assert abs(data["bbox"]["size"][0] - 10) < 1e-4
    assert data["params"]["values"]["size"] == 10


def test_set_params_rebuilds_and_bumps(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(PARAM_SCRIPT)
    assert sess.build_id == 1

    res = sess.set_params({"size": 20})
    assert res["ok"] is True
    assert sess.build_id == 2

    data = json.loads((tmp_path / "model.json").read_text())
    assert abs(data["bbox"]["size"][0] - 20) < 1e-4
    assert data["buildId"] == 2
    assert data["params"]["values"]["size"] == 20

    # get_params reflects the new value
    assert sess.get_params()["values"]["size"] == 20


NEAR_MISS_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "size": {"value": 20, "min": 5, "max": 40, "step": 1, "unit": "mm"},
    "bad": {"value": 7, "min": 1, "max": 10},          # missing step/unit
    "label": {"value": "hex"},                          # non-numeric -> no slider
}

def build(size, bad, label):
    with BuildPart() as p:
        Box(size, size, size)
    show(p.part, name=label)        # proves build() received the non-numeric param
"""


def test_near_miss_schema_is_normalized_and_build_gets_all_params(tmp_path):
    sess = Session(str(tmp_path))
    res = sess.execute_script(NEAR_MISS_SCRIPT)
    assert res["ok"] is True

    data = json.loads((tmp_path / "model.json").read_text())
    schema = data["params"]["schema"]
    values = data["params"]["values"]

    # numeric entries are present and fully normalized (all 5 fields, floats)
    assert set(schema.keys()) == {"size", "bad"}
    for key in ("size", "bad"):
        entry = schema[key]
        assert set(entry.keys()) == {"value", "min", "max", "step", "unit", "desc"}
        for field in ("value", "min", "max", "step"):
            assert isinstance(entry[field], float)
        assert isinstance(entry["unit"], str)
        # NEAR_MISS_SCRIPT sets no desc -> defaults to ""
        assert entry["desc"] == ""

    # missing-step/unit entry gets defaults
    assert schema["bad"]["step"] == 1.0
    assert schema["bad"]["unit"] == ""
    assert schema["size"]["unit"] == "mm"

    # non-numeric param is dropped from the slider schema...
    assert "label" not in schema

    # ...and from the numeric values, which contain only the schema keys
    assert set(values.keys()) == {"size", "bad"}
    assert values["size"] == 20.0
    assert values["bad"] == 7.0

    # ...but build() still received it: the shown object is named from `label`
    assert data["objects"][0]["name"] == "hex"


DESC_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "size":  {"value": 10, "min": 2, "max": 40, "step": 1, "unit": "mm", "desc": "  Cube edge  "},
    "plain": {"value": 5,  "min": 1, "max": 10, "step": 1, "unit": "mm"},
    "weird": {"value": 3,  "min": 1, "max": 6,  "step": 1, "unit": "mm", "desc": 123},
}

def build(size, plain, weird):
    with BuildPart() as p:
        Box(size, size, size)
    show(p.part, name="Cube")
"""


def test_desc_is_normalized(tmp_path):
    sess = Session(str(tmp_path))
    res = sess.execute_script(DESC_SCRIPT)
    assert res["ok"] is True

    schema = json.loads((tmp_path / "model.json").read_text())["params"]["schema"]
    # string desc is kept and stripped of surrounding whitespace
    assert schema["size"]["desc"] == "Cube edge"
    # a missing desc defaults to ""
    assert schema["plain"]["desc"] == ""
    # a non-string desc coerces to ""
    assert schema["weird"]["desc"] == ""
    # every entry carries desc, always a str
    for entry in schema.values():
        assert isinstance(entry["desc"], str)
