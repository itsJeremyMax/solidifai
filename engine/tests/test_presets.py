# engine/tests/test_presets.py
"""Profile index + inheritance flattening over an OrcaSlicer-shaped config tree."""

import json
from pathlib import Path

from solidifai_engine.fabrication import presets


def _write(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def _tree(root: Path) -> str:
    """Build a minimal config: a system base + a user preset that inherits it."""
    # system process base (has 'type', 'from')
    _write(
        root / "system" / "BBL" / "process" / "0.20mm Standard @BBL X1C.json",
        {
            "type": "process",
            "from": "system",
            "name": "0.20mm Standard @BBL X1C",
            "layer_height": "0.2",
            "sparse_infill_density": "15%",
        },
    )
    # user process delta inheriting the system base (no 'type')
    _write(
        root / "user" / "default" / "process" / "0.20mm Optimized PETG @BBL X1C.json",
        {
            "from": "User",
            "inherits": "0.20mm Standard @BBL X1C",
            "name": "0.20mm Optimized PETG @BBL X1C",
            "sparse_infill_density": "20%",
        },
    )
    # a second account folder + system machine/filament
    _write(
        root / "user" / "482203983" / "filament" / "My PETG.json",
        {"from": "User", "name": "My PETG", "filament_cost": "30"},
    )
    _write(
        root / "system" / "BBL" / "machine" / "X1C.json",
        {"type": "machine", "from": "system", "name": "X1C", "nozzle_diameter": ["0.4"]},
    )
    return str(root)


def test_list_profiles_uses_real_layout(tmp_path):
    cfg = _tree(tmp_path)
    out = presets.list_profiles(cfg)
    assert "0.20mm Optimized PETG @BBL X1C" in out["processes"]
    assert "0.20mm Standard @BBL X1C" in out["processes"]
    assert "My PETG" in out["filaments"]
    assert "X1C" in out["printers"]  # 'machine' surfaces as 'printers'


def test_flatten_resolves_inheritance_and_injects_type(tmp_path):
    cfg = _tree(tmp_path)
    merged = presets.flatten(cfg, "0.20mm Optimized PETG @BBL X1C", "process")
    assert merged is not None
    assert merged["type"] == "process"  # injected
    assert merged["from"] == "User"  # leaf 'from' kept
    assert merged["layer_height"] == "0.2"  # inherited from system base
    assert merged["sparse_infill_density"] == "20%"  # child override wins
    assert "inherits" not in merged


def test_flatten_unknown_name_is_none(tmp_path):
    assert presets.flatten(_tree(tmp_path), "nope", "process") is None


def test_write_flattened_roundtrips(tmp_path):
    cfg = _tree(tmp_path)
    out = tmp_path / "flat.json"
    assert presets.write_flattened(cfg, "X1C", "machine", str(out)) is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["type"] == "machine" and data["name"] == "X1C"


def test_missing_config_dir_is_empty(tmp_path):
    out = presets.list_profiles(str(tmp_path / "absent"))
    assert out == {"printers": [], "filaments": [], "processes": []}
