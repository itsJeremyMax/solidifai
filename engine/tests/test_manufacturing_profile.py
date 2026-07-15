import json

import pytest

from solidifai_engine import manufacturing_profile as mp


def test_builtin_defaults_match_asset():
    d = mp.builtin_defaults()
    assert d["design"]["wallMm"] == 2.4
    assert d["design"]["fit"] == "normal"
    assert d["fits"]["normalMm"] == 0.2
    assert d["process"]["settings"]["overhangDeg"] == 45
    assert d["process"]["id"] == "fdm"
    assert "material" not in d  # material is echoed, never stored here


def test_resolve_returns_builtins_when_no_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    prof = mp.resolve(str(tmp_path / "ws"))
    assert prof["design"]["wallMm"] == 2.4
    assert prof["schema"] == 2
    assert prof["process"] == {
        "id": "fdm",
        "settings": {"nozzleMm": 0.4, "layerMm": 0.2, "overhangDeg": 45, "infillPct": 20},
    }


def test_schema_one_process_normalizes_to_v2_and_accepts_dotted_legacy_updates(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "manufacturing-profile.json").write_text(
        json.dumps({"schema": 1, "process": {"kind": "cnc", "overhangDeg": 55}})
    )
    prof = mp.resolve(str(ws))
    assert prof["process"]["id"] == "cnc"
    assert prof["process"]["settings"]["overhangDeg"] == 55


@pytest.mark.parametrize("settings", [42, "invalid", ["nozzleMm"], None])
def test_schema_two_non_object_process_settings_normalize_to_empty_mapping(settings):
    assert mp._normalize({"schema": 2, "process": {"id": "cnc", "settings": settings}}) == {
        "process": {"id": "cnc", "settings": {}}
    }


def test_schema_two_invalid_process_id_is_preserved_for_validation_diagnostics():
    assert mp._normalize({"schema": 2, "process": {"id": "laser", "settings": []}}) == {
        "process": {"id": "laser", "settings": {}}
    }


def test_sparse_schema_one_process_settings_preserve_lower_layer_process(tmp_path, monkeypatch):
    config = tmp_path / "config"
    ws = tmp_path / "ws"
    config.mkdir()
    ws.mkdir()
    (config / "manufacturing-profile.json").write_text(
        json.dumps({"schema": 1, "process": {"kind": "cnc"}})
    )
    (ws / "manufacturing-profile.json").write_text(
        json.dumps({"schema": 1, "process": {"overhangDeg": 55}})
    )
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
    prof = mp.resolve(str(ws))
    assert prof["process"]["id"] == "cnc"
    assert prof["process"]["settings"]["overhangDeg"] == 55


def test_workspace_overrides_global_overrides_builtin(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "manufacturing-profile.json").write_text(
        json.dumps({"design": {"wallMm": 3.0, "filletMm": 2.0}})
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "manufacturing-profile.json").write_text(json.dumps({"design": {"wallMm": 1.6}}))
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
    prof = mp.resolve(str(ws))
    assert prof["design"]["wallMm"] == 1.6  # workspace wins
    assert prof["design"]["filletMm"] == 2.0  # global fills in
    assert prof["design"]["minFeatureMm"] == 1.0  # builtin fills in
    assert prof["process"]["settings"]["overhangDeg"] == 45  # untouched section preserved


def test_malformed_file_falls_back_silently(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "manufacturing-profile.json").write_text("{not json")
    prof = mp.resolve(str(ws))
    assert prof["design"]["wallMm"] == 2.4  # dropped to builtin, no raise


def test_fit_clearance_maps_selected_fit():
    assert mp.fit_clearance({"design": {"fit": "tight"}, "fits": {"tightMm": 0.1}}) == 0.1
    assert mp.fit_clearance({"design": {"fit": "loose"}, "fits": {"looseMm": 0.4}}) == 0.4
    assert mp.fit_clearance({}) == 0.2


def test_effective_echoes_default_material(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    prof = mp.effective(str(tmp_path / "ws"))
    assert prof["material"]["id"] == "pla"  # composed from list_effective
    assert prof["material"]["label"] == "PLA"
    assert prof["design"]["wallMm"] == 2.4  # plus the resolved profile


def test_set_handler_delegates_to_control_then_returns_effective(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    from solidifai_engine import control, server

    seen = {}
    monkeypatch.setattr(
        control,
        "write",
        lambda scope, workspace_root, values, unset: seen.update(
            scope=scope, workspace_root=workspace_root, values=values, unset=unset
        ),
    )
    ws = tmp_path / "ws"
    ws.mkdir()

    class FakeSrv:
        def _workspace_root(self_inner):
            return str(ws)

        def _require(self_inner, p, k):
            return p[k]

        def _refresh_resolver(self_inner):
            pass

    out = server._HANDLERS["set_manufacturing_profile"](
        FakeSrv(), {"values": {"design": {"wallMm": 1.6}}, "unset": ["process.infillPct"]}
    )
    assert seen["scope"] == "workspace"
    assert seen["values"] == {"design": {"wallMm": 1.6}}
    assert seen["unset"] == ["process.infillPct"]
    assert out["material"]["id"]  # returns effective() view (incl. material echo)


def test_handlers_registered_and_callable(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    from solidifai_engine import control, server

    assert "get_manufacturing_profile" in server._HANDLERS
    assert "set_manufacturing_profile" in server._HANDLERS

    # Patch control.write so the handler doesn't try to reach the host socket.
    monkeypatch.setattr(control, "write", lambda **kw: None)

    class FakeSrv:
        def _workspace_root(self_inner):
            return str(tmp_path / "ws")

        def _require(self_inner, params, key):
            return params[key]

        def _refresh_resolver(self_inner):
            pass

    srv = FakeSrv()
    got = server._HANDLERS["set_manufacturing_profile"](
        srv, {"values": {"design": {"wallMm": 1.6}}}
    )
    # set_manufacturing_profile now delegates to Rust; it returns effective() which
    # uses the on-disk profile (no override written here) so wallMm is the builtin.
    assert got["material"]["id"] == "pla"
    got2 = server._HANDLERS["get_manufacturing_profile"](srv, {})
    assert got2["design"]["wallMm"] == 2.4  # builtin (no override on disk)


def test_orient_overhang_prefers_profile_then_param(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path / "config"))
    from solidifai_engine import manufacturing_profile as mp
    from solidifai_engine import server

    ws = tmp_path / "ws"
    ws.mkdir()
    # Write the profile file directly (the writer lives in Rust; use raw JSON here).
    (ws / "manufacturing-profile.json").write_text(
        json.dumps({"process": {"overhangDeg": 55}}), encoding="utf-8"
    )

    class FakeSrv:
        def _workspace_root(self_inner):
            return str(ws)

    assert server._orient_overhang(FakeSrv(), {}) == 55.0  # from profile
    assert server._orient_overhang(FakeSrv(), {"overhang_deg": 30}) == 30.0  # explicit wins

    class NoProfileSrv:
        def _workspace_root(self_inner):
            return str(tmp_path / "fresh")

    assert server._orient_overhang(NoProfileSrv(), {}) == 45.0  # builtin default, no profile


def test_fab_orient_mcp_omits_overhang_when_unset(monkeypatch):
    from solidifai_mcp import server as mcp_server

    seen = {}
    monkeypatch.setattr(
        mcp_server,
        "_call",
        lambda method, params=None: seen.update(method=method, params=params) or {},
    )
    fn = getattr(mcp_server.fab_orient, "fn", mcp_server.fab_orient)  # unwrap if @mcp.tool wraps it
    fn()
    assert seen["method"] == "fab_orient"
    assert not seen["params"]  # {} or None: no overhang_deg injected -> engine uses the profile
    fn(30)
    assert seen["params"] == {"overhang_deg": 30}


def test_python_resolver_matches_shared_parity_cases(tmp_path, monkeypatch):
    """Pin the Python resolver to the same global<=workspace fixture the Rust
    provisioner's test uses, so the two implementations can never silently drift."""
    from pathlib import Path

    cases = json.loads(
        Path(__file__)
        .with_name("manufacturing_profile_parity_cases.json")
        .read_text(encoding="utf-8")
    )
    for i, case in enumerate(cases):
        config = tmp_path / f"c{i}-config"
        ws = tmp_path / f"c{i}-ws"
        config.mkdir()
        ws.mkdir()
        if case["global"]:
            (config / mp.PROFILE_NAME).write_text(json.dumps(case["global"]), encoding="utf-8")
        if case["workspace"]:
            (ws / mp.PROFILE_NAME).write_text(json.dumps(case["workspace"]), encoding="utf-8")
        monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(config))
        got = mp.resolve(str(ws))
        assert got == case["expected"], f"parity case {case['name']!r} diverged: {got}"


def test_mcp_set_forwards_values_and_unset(monkeypatch):
    from solidifai_mcp import server as mcp_server

    seen = {}
    monkeypatch.setattr(
        mcp_server,
        "_call",
        lambda method, params=None: seen.update(method=method, params=params) or {},
    )
    fn = getattr(mcp_server.set_manufacturing_profile, "fn", mcp_server.set_manufacturing_profile)
    fn({"design": {"wallMm": 3.0}}, unset=["process.infillPct"], scope="workspace")
    assert seen["method"] == "set_manufacturing_profile"
    assert seen["params"] == {
        "values": {"design": {"wallMm": 3.0}},
        "unset": ["process.infillPct"],
        "scope": "workspace",
    }
