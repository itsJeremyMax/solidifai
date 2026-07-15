"""Spot-check the standards library against published values.

Every expected number here was verified against the standard or vendor source
named in standards.py at authoring time; these tests pin the data against
accidental edits, and pin fit resolution against the manufacturing profile.
"""

import json
from pathlib import Path

import pytest

from solidifai_engine import standards


def test_standards_catalog_is_the_only_shipped_dimension_table():
    source = Path(standards.__file__).read_text(encoding="utf-8")
    assert "ISO273_CLEARANCE: dict[str, dict[str, float]] = {" not in source
    assert "ISO4762_CAP: dict[str, dict[str, float]] = {" not in source
    assert "HEAT_SET_INSERTS: dict[str, dict[str, float]] = {" not in source


def test_catalog_preserves_all_geometry_driving_m2_to_m8_values():
    assert standards.sizes() == ["M2", "M2.5", "M3", "M4", "M5", "M6", "M8"]
    assert standards.clearance_hole("M2", "close") == 2.2
    assert standards.clearance_hole("M8", "coarse") == 10.0
    assert standards.screw("M8")["head_dia"] == 13.0
    assert standards.nut("M6")["thickness"] == 5.2
    assert standards.washer("M5")["thickness"] == 1.0
    assert standards.insert("M4")["min_hole_depth"] == 9.1


def test_standard_results_include_catalog_provenance_additively():
    result = standards.screw("M3")
    provenance = result["provenance"]
    assert result["head_dia"] == 5.5
    assert provenance == {
        "sourceTitle": "ISO 4762",
        "revision": "2019",
        "table": "Table 1",
        "units": "mm",
        "verifiedDate": "2026-07-13",
    }


def test_workspace_provider_shadows_packaged_standard_and_is_validated(tmp_path):
    provider = {
        "schema": 1,
        "standards": {
            "iso-4762-cap": {
                "source": {
                    "sourceTitle": "Workspace ISO 4762",
                    "revision": "local",
                    "table": "approved vendor table",
                    "units": "mm",
                    "verifiedDate": "2026-07-13",
                },
                "values": {"M3": {"head_dia": 5.6, "head_height": 3.0, "socket": 2.5}},
            }
        },
    }
    (tmp_path / "standards-provider.json").write_text(json.dumps(provider), encoding="utf-8")
    result = standards.screw("M3", workspace_root=str(tmp_path))
    assert result["head_dia"] == 5.6
    assert result["provenance"]["sourceTitle"] == "Workspace ISO 4762"

    provider["standards"]["iso-4762-cap"]["values"]["M3"] = {"head_dia": "bad"}
    (tmp_path / "standards-provider.json").write_text(json.dumps(provider), encoding="utf-8")
    with pytest.raises(ValueError, match="head_height"):
        standards.screw("M3", workspace_root=str(tmp_path))


def test_workspace_provider_shadows_user_provider(tmp_path, monkeypatch):
    from solidifai_engine import paths

    user = tmp_path / "user"
    workspace = tmp_path / "workspace"
    user.mkdir()
    workspace.mkdir()
    monkeypatch.setattr(paths, "app_config_dir", lambda: str(user))
    for root, dia in ((user, 5.6), (workspace, 5.7)):
        (root / "standards-provider.json").write_text(
            json.dumps(
                {
                    "standards": {
                        "iso-4762-cap": {
                            "source": {
                                "sourceTitle": str(root),
                                "revision": "local",
                                "table": "table",
                                "units": "mm",
                                "verifiedDate": "2026-07-13",
                            },
                            "values": {"M3": {"head_dia": dia, "head_height": 3.0, "socket": 2.5}},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
    assert standards.screw("M3", workspace_root=str(workspace))["head_dia"] == 5.7


def test_provider_shadows_clearance_tap_pitch_and_lookup_standard(tmp_path):
    source = {
        "sourceTitle": "Workspace dimensions",
        "revision": "local",
        "table": "approved dimensions",
        "units": "mm",
        "verifiedDate": "2026-07-13",
    }
    provider = {
        "standards": {
            "iso-273-clearance": {
                "source": source,
                "values": {"M3": {"close": 3.1, "medium": 3.3, "coarse": 3.5}},
            },
            "tap-drill-coarse": {"source": source, "values": {"M3": 2.4}},
            "iso-261-pitch": {"source": source, "values": {"M3": 0.55}},
        }
    }
    (tmp_path / "standards-provider.json").write_text(json.dumps(provider), encoding="utf-8")

    assert standards.clearance_hole("M3", "normal", workspace_root=str(tmp_path)) == 3.3
    assert standards.pilot_hole("M3", workspace_root=str(tmp_path)) == 2.4
    assert standards.thread_pitch("M3", workspace_root=str(tmp_path)) == 0.55
    lookup = standards.lookup_standard("M3 clearance and pilot", workspace_root=str(tmp_path))
    assert lookup["clearance_hole"]["dia"] == 3.3
    assert lookup["clearance_hole"]["series"]["close"] == 3.1
    assert lookup["pilot_hole"] == 2.4


def test_std_facade_forwards_workspace_provider_to_every_hardware_helper(tmp_path, monkeypatch):
    from solidifai import std

    monkeypatch.setattr(std, "workspace_root", lambda: str(tmp_path))
    source = {
        "sourceTitle": "Workspace dimensions",
        "revision": "local",
        "table": "approved dimensions",
        "units": "mm",
        "verifiedDate": "2026-07-13",
    }
    provider = {
        "standards": {
            "iso-4762-cap": {
                "source": source,
                "values": {"M3": {"head_dia": 5.6, "head_height": 3.1, "socket": 2.5}},
            },
            "iso-4032-nut": {
                "source": source,
                "values": {"M3": {"width_af": 5.6, "thickness": 2.5}},
            },
            "iso-7089-washer": {
                "source": source,
                "values": {"M3": {"od": 7.1, "id": 3.3, "thickness": 0.6}},
            },
            "ruthex-insert": {
                "source": source,
                "values": {"M3": {"hole_dia": 4.1, "length": 5.8, "min_hole_depth": 6.8}},
            },
            "bearing-deep-groove": {
                "source": source,
                "values": {"608": {"bore": 8.1, "od": 22.1, "width": 7.1}},
            },
        }
    }
    (tmp_path / "standards-provider.json").write_text(json.dumps(provider), encoding="utf-8")

    assert std.screw("M3")["head_dia"] == 5.6
    assert std.nut("M3")["width_af"] == 5.6
    assert std.washer("M3")["od"] == 7.1
    assert std.insert("M3")["hole_dia"] == 4.1
    assert std.bearing("608")["bore"] == 8.1


def test_invalid_scalar_provider_entry_raises_instead_of_falling_back(tmp_path):
    provider = {
        "standards": {
            "iso-273-clearance": {
                "source": {
                    "sourceTitle": "Bad workspace dimensions",
                    "revision": "local",
                    "table": "bad table",
                    "units": "mm",
                    "verifiedDate": "2026-07-13",
                },
                "values": {"M3": {"close": "bad"}},
            }
        }
    }
    (tmp_path / "standards-provider.json").write_text(json.dumps(provider), encoding="utf-8")
    with pytest.raises(ValueError, match="close, medium, coarse"):
        standards.clearance_hole("M3", workspace_root=str(tmp_path))


def test_unknown_standard_lookup_requests_actionable_dimensions():
    result = standards.lookup_standard("M7 cap screw")
    assert result["status"] == "unknown"
    assert result["action"] == "request_dimensions"
    assert "thread_dia" in result["requiredDimensions"]


# -- screw heads --------------------------------------------------------------


def test_cap_screw_m3_iso4762():
    s = standards.screw("M3", head="cap")
    assert s["thread_dia"] == 3.0
    assert s["head_dia"] == 5.5
    assert s["head_height"] == 3.0
    assert s["socket"] == 2.5
    assert "4762" in s["standard"]


def test_button_screw_m4_iso7380():
    s = standards.screw("M4", head="button")
    assert s["head_dia"] == 7.6
    assert s["head_height"] == 2.2


def test_countersunk_m5_iso10642():
    s = standards.screw("M5", head="countersunk")
    assert s["head_dia"] == 10.0
    assert s["head_height"] == 2.8
    assert s["angle_deg"] == 90


def test_button_and_countersunk_below_m3_are_honest():
    # ISO 7380-1 and ISO 10642 start at M3; the library must say so, not invent.
    with pytest.raises(ValueError, match="ISO 7380"):
        standards.screw("M2", head="button")
    with pytest.raises(ValueError, match="ISO 10642"):
        standards.screw("M2.5", head="countersunk")


# -- clearance / pilot holes ---------------------------------------------------


def test_m3_clearance_series_iso273():
    assert standards.clearance_hole("M3", fit="close") == 3.2
    assert standards.clearance_hole("M3", fit="medium") == 3.4
    assert standards.clearance_hole("M3", fit="coarse") == 3.6


def test_clearance_accepts_profile_fit_names():
    # Profile vocabulary maps onto the ISO 273 series.
    assert standards.clearance_hole("M3", fit="tight") == 3.2
    assert standards.clearance_hole("M3", fit="normal") == 3.4
    assert standards.clearance_hole("M3", fit="loose") == 3.6


def test_clearance_default_resolves_builtin_profile():
    # No workspace, no explicit fit: builtin profile fit is "normal" -> medium.
    assert standards.clearance_hole("M3") == 3.4
    assert standards.clearance_hole("M5") == 5.5


def test_clearance_resolves_workspace_profile(tmp_path, monkeypatch):
    # Keep the dev machine's real global overrides out of the test.
    from solidifai_engine import paths

    monkeypatch.setattr(paths, "app_config_dir", lambda: str(tmp_path / "cfg"))
    (tmp_path / "manufacturing-profile.json").write_text(
        json.dumps({"schema": 1, "design": {"fit": "tight"}}), encoding="utf-8"
    )
    assert standards.clearance_hole("M3", workspace_root=str(tmp_path)) == 3.2
    assert standards.clearance_hole("M6", workspace_root=str(tmp_path)) == 6.4


def test_pilot_holes_are_tap_drills():
    assert standards.pilot_hole("M3") == 2.5
    assert standards.pilot_hole("M5") == 4.2


def test_unknown_size_raises():
    with pytest.raises(ValueError, match="unknown size"):
        standards.clearance_hole("M7")


# -- nuts / washers / inserts / bearings ---------------------------------------


def test_hex_nut_m5_is_iso4032_not_din934():
    n = standards.nut("M5")
    assert n["width_af"] == 8.0
    assert n["thickness"] == 4.7  # ISO 4032 (DIN 934 would be 4.0)


def test_heat_set_insert_m3():
    i = standards.insert("M3")
    assert i["hole_dia"] == 4.0
    assert i["length"] == 5.7
    assert i["min_hole_depth"] == pytest.approx(6.7)


def test_heat_set_insert_range_is_m2_to_m5():
    assert sorted(standards.HEAT_SET_INSERTS) == ["M2", "M2.5", "M3", "M4", "M5"]


def test_bearing_608():
    b = standards.bearing("608")
    assert (b["bore"], b["od"], b["width"]) == (8.0, 22.0, 7.0)


def test_bearing_6201():
    b = standards.bearing("6201")
    assert (b["bore"], b["od"], b["width"]) == (12.0, 32.0, 10.0)


# -- lookup_standard -----------------------------------------------------------


def test_lookup_standard_by_size_and_kind():
    r = standards.lookup_standard("M4 heat-set insert")
    assert r["size"] == "M4"
    assert r["heat_set_insert"]["hole_dia"] == 5.6
    assert r["heat_set_insert"]["length"] == 8.1


def test_lookup_standard_clearance_reports_profile_fit():
    r = standards.lookup_standard("M3 clearance hole")
    assert r["clearance_hole"]["dia"] == 3.4
    assert r["clearance_hole"]["fit"] == "normal"
    assert r["clearance_hole"]["series"] == {"close": 3.2, "medium": 3.4, "coarse": 3.6}


def test_lookup_standard_bearing():
    r = standards.lookup_standard("608 bearing")
    assert r["bearing"]["od"] == 22.0


def test_lookup_standard_bare_size_returns_everything():
    r = standards.lookup_standard("M3")
    for key in ("screw_heads", "clearance_hole", "pilot_hole", "nut", "washer", "heat_set_insert"):
        assert key in r, key


def test_lookup_standard_miss_is_helpful():
    r = standards.lookup_standard("wood screw #6")
    assert "error" in r
    assert "M2" in str(r["supported"])


# -- script namespace (solidifai.std) ------------------------------------------


def test_std_facade_matches_engine_values():
    from solidifai import std

    assert std.clearance_hole("M3") == 3.4
    assert std.pilot_hole("M4") == 3.3
    assert std.screw("M3")["head_dia"] == 5.5
    assert std.insert("M5")["hole_dia"] == 6.4
    assert std.bearing("625")["od"] == 16.0


def test_std_in_executed_script(tmp_path):
    from solidifai_engine.session import Session

    s = Session(str(tmp_path / "artifacts"))
    res = s.execute_script(
        "from build123d import Box, Cylinder\n"
        "from solidifai import show, std\n"
        "dia = std.clearance_hole('M3')\n"
        "assert abs(dia - 3.4) < 1e-9\n"
        "show(Box(20, 20, 5) - Cylinder(dia / 2, 20), name='plate')\n"
    )
    assert res.get("ok"), res


def test_std_resolves_workspace_profile_during_build(tmp_path, monkeypatch):
    import json as _json

    from solidifai_engine import paths
    from solidifai_engine.session import Session

    monkeypatch.setattr(paths, "app_config_dir", lambda: str(tmp_path / "cfg"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "manufacturing-profile.json").write_text(
        _json.dumps({"schema": 1, "design": {"fit": "tight"}}), encoding="utf-8"
    )
    s = Session(str(ws / "artifacts"), model_path=str(ws / "model.py"))
    res = s.execute_script(
        "from build123d import Box\n"
        "from solidifai import show, std\n"
        "assert abs(std.clearance_hole('M3') - 3.2) < 1e-9\n"
        "show(Box(10, 10, 10), name='cube')\n"
    )
    assert res.get("ok"), res


# -- engine RPC handlers (Task 5) ----------------------------------------------


def test_rpc_handlers_registered():
    from solidifai_engine.server import _HANDLERS

    assert "lookup_standard" in _HANDLERS
    assert "lookup_reference" in _HANDLERS


def test_lookup_handlers_dispatch(tmp_path):
    # Handlers are pure reads: no model, no socket. They use only
    # srv._workspace_root() and Server._require (a @staticmethod), so a stub
    # server is sufficient and avoids spinning up the UNIX socket.
    from solidifai_engine.server import _HANDLERS, Server

    class _Stub:
        _require = staticmethod(Server._require)

        def _workspace_root(self):
            return str(tmp_path)

    srv = _Stub()
    r = _HANDLERS["lookup_standard"](srv, {"query": "M3 clearance"})
    assert r["clearance_hole"]["dia"] == 3.4
    r = _HANDLERS["lookup_reference"](srv, {"object": "18650"})
    assert r["match"]["dims_mm"]["dia_max"] == 18.6


def test_lookup_reference_survives_non_string_alias(tmp_path, monkeypatch):
    """A non-string alias or id in the host-written library must read as
    unmatched, never abort the lookup loop (malformed reads as empty)."""
    from solidifai_engine import paths

    monkeypatch.setattr(paths, "app_config_dir", lambda: str(tmp_path))
    standards._USER_LIBRARY_CACHE = None
    (tmp_path / "reference-library.json").write_text(
        json.dumps({"objects": [{"id": "widget", "aliases": [123, None], "dims_mm": {}}]}),
        encoding="utf-8",
    )
    try:
        # A miss that must scan the malformed entry without raising.
        assert standards.lookup_reference("18650")["match"]["dims_mm"]["dia_max"] == 18.6
    finally:
        standards._USER_LIBRARY_CACHE = None


def test_lookup_reference_multiword_prefers_more_specific_entry():
    """A short generic alias ('micro' on the AAA cell) must not hijack a
    multi-word query when a more specific entry ('micro hdmi') also matches."""
    assert standards.lookup_reference("micro hdmi cable")["match"]["id"] == "micro-hdmi-d"
    # exact-equality path already worked; keep it covered
    assert standards.lookup_reference("micro hdmi")["match"]["id"] == "micro-hdmi-d"


def test_lookup_reference_short_alias_only_matches_whole_word():
    """A single-token alias may still resolve a query it is the only match for,
    but never mid-word."""
    assert standards.lookup_reference("micro usb port")["match"]["id"] == "aaa"
    assert standards.lookup_reference("micrometer")["match"] is None


def test_size_regex_parses_sizes_glued_to_other_text():
    """M8x20 and M2.5mm must not be misparsed (trailing \\b regression)."""
    assert standards.lookup_standard("M8x20 cap screw")["size"] == "M8"
    assert standards.lookup_standard("M2.5mm nut")["size"] == "M2.5"
    # leading boundary still guards: no false size from a plain word
    assert (
        "size" not in standards.lookup_standard("beam5 bracket")
        or standards.lookup_standard("beam5 bracket").get("size") is None
    )
