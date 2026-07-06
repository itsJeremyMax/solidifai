from solidifai_engine import part_materials as pm


def test_load_missing_file_is_empty(tmp_path):
    assert pm.load_overrides(str(tmp_path)) == {}


def test_write_then_load_round_trips(tmp_path):
    pm.write_overrides(str(tmp_path), {"bracket": "aluminum", "pin": "cobalt-pla"})
    assert pm.load_overrides(str(tmp_path)) == {"bracket": "aluminum", "pin": "cobalt-pla"}


def test_load_malformed_file_is_empty(tmp_path):
    (tmp_path / "part_materials.json").write_text("{ not json")
    assert pm.load_overrides(str(tmp_path)) == {}


def test_load_ignores_non_string_values(tmp_path):
    (tmp_path / "part_materials.json").write_text(
        '{"schema":1,"overrides":{"a":"steel","b":123,"c":null}}'
    )
    assert pm.load_overrides(str(tmp_path)) == {"a": "steel"}


def test_write_is_atomic_and_schema_tagged(tmp_path):
    pm.write_overrides(str(tmp_path), {"a": "steel"})
    import json

    data = json.loads((tmp_path / "part_materials.json").read_text())
    assert data["schema"] == 1
    assert data["overrides"] == {"a": "steel"}
