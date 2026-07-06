"""Spot-check the standards library against published values.

Every expected number here was verified against the standard or vendor source
named in standards.py at authoring time; these tests pin the data against
accidental edits, and pin fit resolution against the manufacturing profile.
"""

import json

import pytest

from solidifai_engine import standards

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
