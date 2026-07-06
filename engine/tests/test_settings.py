from solidifai_engine import settings


def test_write_then_load_round_trips(tmp_path):
    root = str(tmp_path)
    settings.write_params(root, {"size": 47.0, "hole_dia": 6.5})
    assert settings.load_params(root) == {"size": 47.0, "hole_dia": 6.5}


def test_load_missing_file_returns_empty(tmp_path):
    assert settings.load_params(str(tmp_path)) == {}


def test_load_malformed_returns_empty(tmp_path):
    (tmp_path / "settings.json").write_text("{ not json")
    assert settings.load_params(str(tmp_path)) == {}


def test_merge_keeps_known_drops_unknown_defaults_missing():
    defaults = {"size": 20.0, "hole_dia": 5.0, "label": "x"}
    saved = {"size": 47.0, "gone": 1.0}
    assert settings.merge(defaults, saved) == {"size": 47.0, "hole_dia": 5.0, "label": "x"}


def test_write_is_atomic_no_tmp_left(tmp_path):
    settings.write_params(str(tmp_path), {"a": 1.0})
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []
