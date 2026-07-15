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
    assert m.process_for("unobtanium") is None


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


def test_unknown_custom_material_does_not_inherit_pla():
    with pytest.raises(ValueError, match="unknown material base"):
        m.material_from_record({"id": "mystery", "base": "moon-dust"})


def test_legacy_material_without_base_migrates_with_diagnostic():
    mat = m.material_from_record({"id": "legacy"})
    assert mat.base == "pla"
    assert mat.diagnostics == ("legacyFallback",)


def test_custom_aluminum_material_keeps_explicit_cnc_process():
    mat = m.material_from_record({"id": "anodized", "base": "aluminum", "process": "cnc"})
    assert mat.density == pytest.approx(2.70)
    assert mat.process == "cnc"
    assert mat.process_source == "explicit"


def test_reporting_uses_resolved_material_process_before_record_id():
    from solidifai_engine.reporting import _material_process

    mat = m.material_from_record({"id": "anodized", "base": "aluminum", "process": "cnc"})
    assert _material_process(mat) == "cnc"


def test_unknown_explicit_process_fails_validation():
    with pytest.raises(ValueError, match="unknown manufacturing process"):
        m.material_from_record({"id": "mystery", "base": "pla", "process": "laser"})


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


@pytest.mark.parametrize(
    ("record", "error"),
    [
        ({"id": "pla", "base": "moon-dust"}, "unknown material base"),
        ({"id": "pla", "base": "pla", "process": "laser"}, "unknown manufacturing process"),
        ({"id": "pla", "base": "pla", "colorHex": "not-a-color"}, "expected #rrggbb"),
    ],
)
def test_invalid_record_shadows_builtin_and_surfaces_diagnostic(tmp_path, record, error):
    path = tmp_path / "materials.json"
    path.write_text(json.dumps({"materials": [record]}))
    source = m.JsonFileSource(str(path))
    resolver = m.MaterialResolver([m.BuiltinSource(), source])

    with pytest.raises(ValueError, match=f"invalid material 'pla'.*{error}"):
        resolver.resolve("pla")
    assert source.get("pla") is None
    assert source.errors["pla"].startswith(error)


def test_invalid_unknown_record_and_default_are_visible_not_dropped(tmp_path, monkeypatch):
    config = tmp_path / "config"
    ws = tmp_path / "ws"
    config.mkdir()
    ws.mkdir()
    (ws / "materials.json").write_text(
        json.dumps(
            {
                "default": "mystery",
                "materials": [{"id": "mystery", "base": "moon-dust"}],
            }
        )
    )
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
    m.configure_resolver(str(ws))
    try:
        with pytest.raises(ValueError, match="invalid material 'mystery'"):
            m.RESOLVER.resolve(None)
        listed = m.list_effective(str(ws))
        mystery = next(entry for entry in listed["materials"] if entry["id"] == "mystery")
        assert mystery["invalid"] is True
        assert "unknown material base" in mystery["error"]
        assert listed["diagnostics"]["mystery"].startswith("unknown material base")
    finally:
        m.configure_resolver(str(tmp_path / "empty"))


def test_invalid_default_without_a_record_fails_resolution(tmp_path):
    path = tmp_path / "materials.json"
    path.write_text(json.dumps({"default": "missing", "materials": []}))
    resolver = m.MaterialResolver(
        [m.BuiltinSource(), m.JsonFileSource(str(path))], default="missing"
    )
    with pytest.raises(ValueError, match="invalid material default 'missing'"):
        resolver.resolve()


def test_invalid_pla_override_has_no_packaged_mass_or_process_fields(tmp_path, monkeypatch):
    config = tmp_path / "config"
    ws = tmp_path / "ws"
    config.mkdir()
    ws.mkdir()
    (ws / "materials.json").write_text(
        json.dumps({"materials": [{"id": "pla", "base": "moon-dust"}]})
    )
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
    pla = next(entry for entry in m.list_effective(str(ws))["materials"] if entry["id"] == "pla")
    assert pla == {
        "id": "pla",
        "invalid": True,
        "error": "unknown material base 'moon-dust'",
        "isDefault": True,
    }


def test_json_file_source_missing_file_is_empty():
    src = m.JsonFileSource("/no/such/materials.json")
    assert src.names() == []
    assert src.default is None


def test_json_file_source_reads_utf8_regardless_of_locale(tmp_path):
    # The host writes UTF-8; the read must not depend on the locale default
    # (Windows cp1252, or the ASCII locale OCC exports leave behind).
    p = tmp_path / "materials.json"
    p.write_bytes(
        json.dumps(
            {
                "materials": [
                    {"id": "tolerance-pla", "label": "PLA ±0.1 µm", "base": "pla"},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )
    src = m.JsonFileSource(str(p))
    assert src.get("tolerance-pla").label == "PLA ±0.1 µm"


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
