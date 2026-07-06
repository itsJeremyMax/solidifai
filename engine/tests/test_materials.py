import json
import math

import pytest

from solidifai_engine import materials as m
from solidifai_engine.materials import (
    BUILTIN,
    RESOLVER,
    BuiltinSource,
    Material,
    MaterialResolver,
)


def test_default_resolves_to_pla():
    mat = RESOLVER.resolve(None)
    assert mat.name == "pla"
    assert mat.label == "PLA"
    assert mat.density == 1.24
    assert mat.metalness == 0.0


def test_every_builtin_resolves():
    for name in BUILTIN:
        mat = RESOLVER.resolve(name)
        assert mat.name == name
        assert 0.0 <= mat.metalness <= 1.0
        assert 0.0 <= mat.roughness <= 1.0
        assert len(mat.base_color) == 3
        assert all(0.0 <= v <= 1.0 for v in mat.base_color)


def test_unknown_material_lists_valid_names():
    with pytest.raises(ValueError) as exc:
        RESOLVER.resolve("unobtainium")
    msg = str(exc.value)
    assert "unobtainium" in msg
    assert "aluminum" in msg  # the valid vocabulary is listed


def test_color_overrides_base_color_not_finish():
    mat = RESOLVER.resolve("aluminum", color=(0.9, 0.1, 0.1))
    assert mat.base_color == (0.9, 0.1, 0.1)  # override applied
    assert mat.metalness == 1.0  # finish unchanged from aluminum


def test_color_must_be_three_floats_in_unit_range():
    with pytest.raises(ValueError):
        RESOLVER.resolve("pla", color=(2.0, 0.0, 0.0))  # out of range
    with pytest.raises(ValueError):
        RESOLVER.resolve("pla", color=(0.1, 0.2))  # wrong length


def test_appearance_wire_shape():
    mat = RESOLVER.resolve("steel")
    ap = RESOLVER.appearance(mat)
    assert ap["material"] == "steel"
    assert len(ap["baseColor"]) == 3
    assert set(ap) == {
        "material",
        "baseColor",
        "metalness",
        "roughness",
        "clearcoat",
        "clearcoatRoughness",
    }


def test_resolver_source_priority_proves_extensibility_seam():
    # A higher-priority source (last in the list) overrides the built-in.
    override = Material(
        name="pla",
        label="PLA-X",
        density=9.9,
        base_color=(0.0, 0.0, 0.0),
        metalness=0.0,
        roughness=0.1,
    )

    class FakeSource:
        def get(self, name):
            return override if name == "pla" else None

        def names(self):
            return ["pla"]

    resolver = MaterialResolver([BuiltinSource(), FakeSource()])
    mat = resolver.resolve("pla")
    assert mat.label == "PLA-X"  # workspace/global layer wins
    assert mat.density == 9.9
    # built-in-only names still resolve through the chain
    assert resolver.resolve("brass").name == "brass"


def test_show_records_material_and_color():
    from build123d import Box

    from solidifai import _registry, reset_registry, show

    reset_registry()
    show(Box(10, 10, 10), name="A", material="steel", color=(0.1, 0.2, 0.3))
    show(Box(5, 5, 5), name="B")  # defaults

    objs = _registry()
    assert objs[0].material == "steel"
    assert objs[0].color == (0.1, 0.2, 0.3)
    assert objs[1].material is None  # unspecified → resolver default later
    assert objs[1].color is None


def test_process_for_plastics_is_fdm():
    for base in ("pla", "abs", "petg", "nylon"):
        assert m.process_for(base) == "fdm"


def test_process_for_metals_is_cnc():
    for base in ("aluminum", "steel", "stainless", "brass", "copper"):
        assert m.process_for(base) == "cnc"


def test_process_for_unknown_defaults_to_fdm():
    assert m.process_for("unobtanium") == "fdm"


def test_hex_to_linear_white_and_black():
    assert m.hex_to_linear("#ffffff") == (1.0, 1.0, 1.0)
    assert m.hex_to_linear("#000000") == (0.0, 0.0, 0.0)


def test_hex_to_linear_is_srgb_decoded():
    # mid-gray #808080 (sRGB 0.5019) decodes to ~0.2158 linear
    r, g, b = m.hex_to_linear("#808080")
    assert math.isclose(r, 0.2158, abs_tol=0.002)
    assert r == g == b


def test_linear_to_hex_round_trips_known_gray():
    # PLA built-in base_color (linear) re-encodes to a light gray sRGB hex
    assert m.linear_to_hex((0.52, 0.54, 0.57)).startswith("#")
    # round-trip stays close (8-bit quantization, not exact)
    assert round_trip_close((0.25, 0.5, 0.75)) == (0.25, 0.5, 0.75)


def round_trip_close(c):
    return tuple(round(x, 2) for x in m.hex_to_linear(m.linear_to_hex(c)))


def test_material_from_record_maps_base_density_and_color():
    rec = {
        "id": "cobalt-pla",
        "label": "Cobalt PLA",
        "base": "pla",
        "colorHex": "#2b6cff",
        "finish": "satin",
    }
    mat = m.material_from_record(rec)
    assert mat.name == "cobalt-pla"
    assert mat.label == "Cobalt PLA"
    assert mat.density == 1.24  # from PLA built-in
    assert mat.roughness == 0.55  # satin preset
    assert mat.metalness == 0.0  # plastic base, non-metallic finish
    assert mat.base_color == m.hex_to_linear("#2b6cff")


def test_material_from_record_metallic_finish_forces_metalness():
    rec = {
        "id": "raw-alu",
        "label": "Raw Aluminum",
        "base": "aluminum",
        "colorHex": "#d6d9de",
        "finish": "metallic",
    }
    mat = m.material_from_record(rec)
    assert mat.metalness == 1.0
    assert mat.density == 2.70


def test_json_file_source_reads_and_resolves(tmp_path):
    p = tmp_path / "materials.json"
    p.write_text(
        json.dumps(
            {
                "default": "cobalt-pla",
                "materials": [
                    {
                        "id": "cobalt-pla",
                        "label": "Cobalt PLA",
                        "base": "pla",
                        "colorHex": "#2b6cff",
                        "finish": "satin",
                    },
                ],
            }
        )
    )
    src = m.JsonFileSource(str(p))
    assert src.names() == ["cobalt-pla"]
    assert src.default == "cobalt-pla"
    assert src.get("cobalt-pla").label == "Cobalt PLA"
    assert src.get("missing") is None


def test_json_file_source_missing_file_is_empty():
    src = m.JsonFileSource("/no/such/materials.json")
    assert src.names() == []
    assert src.default is None


def test_resolver_uses_configured_default_when_name_is_none():
    r = m.MaterialResolver([m.BuiltinSource()], default="petg")
    assert r.resolve(None).name == "petg"


def test_resolver_default_falls_back_to_pla():
    r = m.MaterialResolver([m.BuiltinSource()], default=None)
    assert r.resolve(None).name == "pla"


def test_configure_resolver_layers_workspace_over_global(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "materials.json").write_text(
        json.dumps(
            {
                "default": "global-red",
                "materials": [
                    {
                        "id": "global-red",
                        "label": "Global Red",
                        "base": "pla",
                        "colorHex": "#d23b3b",
                        "finish": "matte",
                    }
                ],
            }
        )
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "materials.json").write_text(
        json.dumps(
            {
                "default": "ws-blue",
                "materials": [
                    {
                        "id": "ws-blue",
                        "label": "WS Blue",
                        "base": "pla",
                        "colorHex": "#2b6cff",
                        "finish": "satin",
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
    m.configure_resolver(str(ws))
    try:
        assert m.RESOLVER.resolve("global-red").label == "Global Red"  # global visible
        assert m.RESOLVER.resolve("ws-blue").label == "WS Blue"  # workspace visible
        assert m.RESOLVER.resolve(None).name == "ws-blue"  # workspace default wins
        assert m.RESOLVER.resolve("pla").name == "pla"  # built-in still there
    finally:
        m.configure_resolver(str(tmp_path / "empty"))  # reset to a clean state


def test_list_effective_includes_builtins_with_process(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    out = m.list_effective(str(tmp_path / "nows"))
    by_id = {e["id"]: e for e in out["materials"]}
    assert "pla" in by_id and by_id["pla"]["process"] == "fdm"
    assert by_id["aluminum"]["process"] == "cnc"
    assert by_id["pla"]["colorHex"].startswith("#")
    assert out["default"] == "pla"
    assert by_id["pla"]["isDefault"] is True


def test_list_effective_merges_and_flags_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "materials.json").write_text(
        json.dumps(
            {
                "default": "cobalt-pla",
                "materials": [
                    {
                        "id": "cobalt-pla",
                        "label": "Cobalt PLA",
                        "base": "pla",
                        "colorHex": "#2b6cff",
                        "finish": "satin",
                    }
                ],
            }
        )
    )
    out = m.list_effective(str(ws))
    by_id = {e["id"]: e for e in out["materials"]}
    assert by_id["cobalt-pla"]["process"] == "fdm"
    assert by_id["cobalt-pla"]["density"] == 1.24
    assert out["default"] == "cobalt-pla"
    assert by_id["cobalt-pla"]["isDefault"] is True
    assert by_id["pla"]["isDefault"] is False
