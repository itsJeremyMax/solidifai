"""The socket server dispatches fabrication methods to the session."""

import os
import tempfile

from solidifai_engine.server import Server


def _server() -> Server:
    d = tempfile.mkdtemp()
    return Server(os.path.join(d, "engine.sock"), os.path.join(d, "artifacts"))


def test_dispatch_fab_detect():
    srv = _server()
    out = srv._dispatch("fab_detect", {})
    # Returns ok:true whether or not a slicer is installed.
    assert "ok" in out
    assert "found" in out


def test_dispatch_fab_profiles():
    srv = _server()
    out = srv._dispatch("fab_profiles", {})
    assert out["ok"] is True
    assert "printers" in out and "filaments" in out


def test_dispatch_fab_estimate_passes_destination_id():
    srv = _server()
    # No model loaded — verify the error comes from the session, not dispatch.
    out = srv._dispatch("fab_estimate", {"destination_id": "my-printer"})
    assert out["ok"] is False
    assert "no model" in out["error"]


def test_dispatch_fab_estimate_default_destination():
    srv = _server()
    out = srv._dispatch("fab_estimate", {})
    assert out["ok"] is False
    assert "no model" in out["error"]


def test_dispatch_fab_orient_passes_overhang_deg():
    srv = _server()
    # No model loaded — the error must come from the session, not dispatch.
    out = srv._dispatch("fab_orient", {"overhang_deg": 30})
    assert out["ok"] is False
    assert "no model" in out["error"]


def test_dispatch_fab_orient_default_overhang():
    srv = _server()
    out = srv._dispatch("fab_orient", {})
    assert out["ok"] is False
    assert "no model" in out["error"]


def test_dispatch_list_destinations():
    srv = _server()
    out = srv._dispatch("list_destinations", {})
    assert out["ok"] is True
    assert "destinations" in out


def test_dispatch_set_destinations():
    srv = _server()
    out = srv._dispatch("set_destinations", {"destinations": []})
    assert out["ok"] is True
    assert out["count"] == 0
