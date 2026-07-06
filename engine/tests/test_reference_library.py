"""User reference library layered over the packaged seed (lookup side)."""

import json

import pytest

from solidifai_engine import standards


@pytest.fixture
def user_lib(tmp_path, monkeypatch):
    """Point the engine's config dir at a temp dir and reset lookup caches."""
    monkeypatch.setenv("SOLIDIFAI_CONFIG_DIR", str(tmp_path))
    standards._USER_LIBRARY_CACHE = None

    def write(objects):
        path = tmp_path / "reference-library.json"
        path.write_text(
            json.dumps({"schema": 1, "units": "mm", "objects": objects}),
            encoding="utf-8",
        )
        return path

    yield write
    standards._USER_LIBRARY_CACHE = None


PI = {
    "id": "raspberry-pi-5",
    "aliases": ["pi 5", "rpi5"],
    "category": "sbc",
    "dims_mm": {"pcb": [85.0, 56.0, 1.4], "height_max": 18.0},
    "source": "https://datasheets.raspberrypi.com/rpi5.pdf",
    "origin": "learned",
    "verified_at": "2026-06-11",
    "verified_in": "cyberdeck",
}


def test_learned_entry_resolves_with_provenance(user_lib):
    user_lib([PI])
    out = standards.lookup_reference("raspberry pi 5")
    assert out["match"]["dims_mm"]["pcb"][:2] == [85.0, 56.0]
    assert out["match"]["origin"] == "learned"


def test_learned_alias_resolves(user_lib):
    user_lib([PI])
    assert standards.lookup_reference("rpi5")["match"]["id"] == "raspberry-pi-5"


def test_user_entry_shadows_seed(user_lib):
    user_lib(
        [
            {
                **PI,
                "id": "18650",
                "aliases": [],
                "category": "cell",
                "dims_mm": {"dia_max": 19.0, "length_max": 65.2},
            }
        ]
    )
    assert standards.lookup_reference("18650")["match"]["dims_mm"]["dia_max"] == 19.0


def test_seed_still_resolves_without_library(user_lib):
    # no file written
    assert standards.lookup_reference("usb-c")["match"] is not None


def test_user_exact_alias_outranks_seed_id(user_lib):
    # User entries are searched first and an exact alias hit breaks like an
    # exact id hit, so a user entry deliberately aliased "usb-c" outranks the
    # seed's id match. The user library is authoritative for the user's own
    # vocabulary; pin that choice.
    user_lib([{**PI, "aliases": ["usb-c"]}])
    assert standards.lookup_reference("usb-c")["match"]["id"] == "raspberry-pi-5"


def test_malformed_library_never_breaks_lookup(user_lib, tmp_path):
    (tmp_path / "reference-library.json").write_text("{nope", encoding="utf-8")
    assert standards.lookup_reference("usb-c")["match"] is not None


def test_mtime_change_reloads(user_lib, tmp_path):
    path = user_lib([PI])
    assert standards.lookup_reference("raspberry pi 5")["match"] is not None
    import os
    import time

    user_lib([])  # rewrite empty
    os.utime(path, (time.time() + 2, time.time() + 2))  # force visible mtime bump
    assert standards.lookup_reference("raspberry pi 5")["match"] is None


def test_miss_lists_available_and_points_at_save(user_lib):
    user_lib([PI])
    out = standards.lookup_reference("nonexistent-gizmo")
    assert out["match"] is None
    assert "raspberry-pi-5" in out["available"]
    assert "save_reference" in out["note"]


# -- save_reference handler (delegates the write to the host) -----------------

import json as _json


def _make_srv(tmp_path, workspace_name="cyberdeck"):
    """Return a minimal fake Server whose workspace root has a workspace.json."""
    from solidifai_engine.workspace_metadata import META_NAME

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / META_NAME).write_text(
        _json.dumps({"schema": 1, "name": workspace_name}), encoding="utf-8"
    )

    class FakeSrv:
        def _workspace_root(self_inner):
            return str(ws)

        def _require(self_inner, p, k):
            if k not in p:
                raise ValueError(f"missing param {k!r}")
            return p[k]

    return FakeSrv()


def test_save_reference_stamps_provenance_and_delegates(tmp_path, monkeypatch):
    from solidifai_engine import control
    from solidifai_engine.server import _HANDLERS

    sent = {}

    def fake_write_reference(entry):
        sent.update(entry)
        return {"schema": 1, "units": "mm", "objects": [entry]}

    monkeypatch.setattr(control, "write_reference", fake_write_reference)
    srv = _make_srv(tmp_path)
    out = _HANDLERS["save_reference"](srv, {"entry": dict(PI, origin=None)})
    assert sent["origin"] == "learned"
    assert sent["verified_in"] == "cyberdeck"
    assert len(sent["verified_at"]) == 10  # YYYY-MM-DD
    assert out["saved"]["id"] == "raspberry-pi-5"


def test_save_reference_requires_core_fields(tmp_path):
    from solidifai_engine.server import _HANDLERS

    srv = _make_srv(tmp_path)
    with pytest.raises(ValueError, match="source"):
        _HANDLERS["save_reference"](
            srv, {"entry": {"id": "x", "category": "c", "dims_mm": {"d": 1}}}
        )


def test_save_reference_fails_soft_without_host(tmp_path, monkeypatch):
    from solidifai_engine.server import _HANDLERS

    monkeypatch.delenv("SOLIDIFAI_CONTROL_SOCK", raising=False)
    srv = _make_srv(tmp_path)
    with pytest.raises(RuntimeError, match="library unavailable"):
        _HANDLERS["save_reference"](srv, {"entry": PI})
