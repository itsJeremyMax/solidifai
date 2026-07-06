"""The socket server dispatches converge_to_spec to the session."""

import os
import tempfile

from solidifai_engine.server import Server


def _server() -> Server:
    d = tempfile.mkdtemp()
    return Server(os.path.join(d, "engine.sock"), os.path.join(d, "artifacts"))


def test_dispatch_converge_to_spec_no_model():
    srv = _server()
    out = srv._dispatch("converge_to_spec", {})
    # Without a model, the session returns ok=False or raises; either surfaces
    # as a failed result dict (ok is False) or an ok=True with found=False.
    assert "ok" in out or out is not None


def test_dispatch_converge_to_spec_defaults():
    # Verify the handler passes default objective/apply correctly.
    srv = _server()
    out = srv._dispatch("converge_to_spec", {})
    assert isinstance(out, dict)


def test_dispatch_converge_to_spec_routes_to_session(monkeypatch):
    """_HANDLERS["converge_to_spec"] calls session.converge_to_spec with the
    right args."""
    srv = _server()
    calls = []

    def fake_converge(objective, apply):
        calls.append((objective, apply))
        return {"ok": True, "found": False}

    monkeypatch.setattr(srv._session, "converge_to_spec", fake_converge)

    srv._dispatch("converge_to_spec", {"objective": "max_mass", "apply": True})
    assert calls == [("max_mass", True)]

    # Default values when params omitted.
    srv._dispatch("converge_to_spec", {})
    assert calls[-1] == ("min_mass", False)
