"""App-level destinations store: round-trip, malformed, add/remove."""

from solidifai_engine import destinations as dst


def test_destinations_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(dst, "config_dir", lambda: str(tmp_path))
    dst.write(
        [
            {
                "id": "d1",
                "name": "Garage",
                "kind": "local",
                "provider": "orca",
                "printerProfile": "X1C",
                "filamentProfile": "PLA",
                "connection": None,
            }
        ]
    )
    out = dst.load()
    assert out[0]["name"] == "Garage"


def test_destinations_malformed_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(dst, "config_dir", lambda: str(tmp_path))
    (tmp_path / "destinations.json").write_text("{ not json")
    assert dst.load() == []


def test_add_then_remove(tmp_path, monkeypatch):
    monkeypatch.setattr(dst, "config_dir", lambda: str(tmp_path))
    after_add = dst.add({"id": "d2", "name": "Studio", "kind": "local", "provider": "orca"})
    assert any(d["id"] == "d2" for d in after_add)
    after_remove = dst.remove("d2")
    assert not any(d["id"] == "d2" for d in after_remove)
