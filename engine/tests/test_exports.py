import json
import os
from pathlib import Path

import pytest
from build123d import Box

from solidifai import reset_registry, show
from solidifai_engine import session as session_module
from solidifai_engine.exports import (
    SUPPORTED,
    export,
    options_schema,
    validate_options,
)
from solidifai_engine.session import Session


def test_export_catalog_is_the_only_schema_and_quality_source():
    from solidifai_engine import exports

    source = Path(exports.__file__).read_text(encoding="utf-8")
    assert "def _f(" not in source
    assert "_GLTF_FIELDS =" not in source
    assert 'QUALITY = {\n    "stl":' not in source


def setup_function():
    reset_registry()


def _current_model():
    show(Box(20, 20, 20), name="Cube")


def test_export_glb(tmp_path):
    _current_model()
    p = str(tmp_path / "out.glb")
    export("glb", p)
    assert os.path.getsize(p) > 0
    with open(p, "rb") as f:
        assert f.read(4) == b"glTF"


def test_export_step(tmp_path):
    _current_model()
    p = str(tmp_path / "out.step")
    export("step", p)
    assert os.path.getsize(p) > 0
    with open(p, "rb") as f:
        assert b"ISO-10303" in f.read()


def test_export_stl(tmp_path):
    _current_model()
    p = str(tmp_path / "out.stl")
    export("stl", p)
    assert os.path.getsize(p) > 0


def test_session_export_default_path_lands_in_workspace_exports(tmp_path):
    workspace = tmp_path / "my_widget"
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    model_path = str(workspace / "model.py")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    sess = Session(artifacts, model_path=model_path)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10, 10, 10), name='C')\n"
    )

    res = sess.export("step")  # no path -> default into <workspace>/exports/
    assert res["ok"] is True
    # slug comes from the workspace folder name (parent of model.py): "my_widget"
    assert res["path"] == os.path.join(str(workspace), "exports", "my_widget.step")
    assert os.path.getsize(res["path"]) > 0


def test_session_export_relative_path_resolves_under_workspace_exports(tmp_path):
    workspace = tmp_path / "widget"
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    model_path = str(workspace / "model.py")
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    sess = Session(artifacts, model_path=model_path)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10, 10, 10), name='C')\n"
    )

    # A bare filename (what an agent might pass) lands in the exports folder.
    res = sess.export("stl", "handoff.stl")
    assert res["ok"] is True
    assert res["path"] == os.path.join(str(workspace), "exports", "handoff.stl")
    assert os.path.getsize(res["path"]) > 0


def test_session_export_explicit_path_still_honored(tmp_path):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    sess = Session(artifacts)  # no model_path -> root is None
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10, 10, 10), name='C')\n"
    )
    out = str(tmp_path / "explicit.stl")
    res = sess.export("stl", out)
    assert res["ok"] is True
    assert res["path"] == out
    assert os.path.getsize(out) > 0


# -- schema + validation ------------------------------------------


def test_supported_formats():
    assert set(SUPPORTED) == {"step", "stl", "glb", "gltf", "brep", "3mf"}


def test_canonical_export_catalog_exposes_every_format_and_defaults():
    catalog = options_schema()
    assert set(catalog) == set(SUPPORTED)
    assert catalog["gltf"]["linear_deflection"]["default"] == 0.001


def test_options_schema_step_fields():
    fields = options_schema("step")
    assert set(fields) == {"unit", "precision_mode", "write_pcurves", "timestamp"}
    assert fields["unit"]["default"] == "mm"


def test_validate_fills_defaults():
    o = validate_options("stl", {})
    assert o["ascii"] is False
    assert o["quality"] == "standard"
    assert o["tolerance"] == 0.01
    assert o["angular_tolerance"] == 0.1


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError, match="Unknown option 'foo' for STL"):
        validate_options("stl", {"foo": 1})


def test_catalog_preserves_glb_validation_label():
    with pytest.raises(ValueError, match="Unknown option 'foo' for GLB"):
        validate_options("glb", {"foo": 1})


def test_validate_rejects_bad_unit():
    with pytest.raises(ValueError, match="unit must be one of"):
        validate_options("step", {"unit": "lightyears"})


def test_quality_expands_to_tolerance():
    assert validate_options("stl", {"quality": "draft"})["tolerance"] == 0.05
    assert validate_options("stl", {"quality": "fine"})["tolerance"] == 0.001


def test_explicit_tolerance_sets_quality_custom():
    o = validate_options("stl", {"tolerance": 0.02})
    assert o["tolerance"] == 0.02
    assert o["quality"] == "custom"


def test_brep_has_no_options():
    assert options_schema("brep") == {}
    assert validate_options("brep", {}) == {}


# -- session forwards options ------------------------------------------


def test_session_export_forwards_options(tmp_path):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    sess = Session(artifacts)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10, 10, 10), name='C')\n"
    )
    out = str(tmp_path / "ascii.stl")
    res = sess.export("stl", out, {"ascii": True})
    assert res["ok"] is True
    with open(out, "rb") as f:
        assert f.read(6) == b"solid "


def test_strict_export_blocks_unready_build_but_legacy_export_is_unchanged(tmp_path):
    workspace = tmp_path / "widget"
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    model_path = str(workspace / "model.py")
    os.makedirs(workspace, exist_ok=True)
    sess = Session(artifacts, model_path=model_path)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(1, 1, 1))\n"
    )

    legacy = sess.export("stl", "legacy.stl")
    strict = sess.export("stl", "strict.stl", strict_export=True)

    assert legacy["ok"] is True
    assert strict == {"ok": False, "error": "export blocked by readiness", "findingIds": ["brief"]}


def test_legacy_export_does_not_evaluate_or_persist_readiness(tmp_path, monkeypatch):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    sess = Session(artifacts)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(1, 1, 1))\n"
    )
    monkeypatch.setattr(
        sess,
        "get_readiness",
        lambda: (_ for _ in ()).throw(AssertionError("legacy export evaluated readiness")),
    )

    assert sess.export("stl", str(tmp_path / "legacy.stl"))["ok"] is True


def test_strict_export_consumes_host_verified_nonce_once_and_audits_it(tmp_path):
    workspace = tmp_path / "widget"
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    model_path = str(workspace / "model.py")
    os.makedirs(workspace, exist_ok=True)
    calls = []

    def consume(nonce, *, workspace_id, build_id, format):
        calls.append((nonce, workspace_id, build_id, format))
        return {"ok": len(calls) == 1, "nonceId": "override-1"}

    sess = Session(artifacts, model_path=model_path, override_verifier=consume)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(1, 1, 1))\n"
    )

    first = sess.export("stl", "approved.stl", strict_export=True, override_nonce="opaque")
    second = sess.export("stl", "reused.stl", strict_export=True, override_nonce="opaque")

    assert first["ok"] is True
    assert second == {"ok": False, "error": "export override rejected", "findingIds": ["brief"]}
    assert calls == [
        ("opaque", str(workspace), 1, "stl"),
        ("opaque", str(workspace), 1, "stl"),
    ]
    audit = json.loads((workspace / ".solidifai" / "export-overrides.jsonl").read_text())
    assert audit["nonceId"] == "override-1"
    assert audit["buildId"] == 1
    assert audit["findingIds"] == ["brief"]


def _override_session(tmp_path):
    root = tmp_path / "widget"
    root.mkdir()
    session = Session(
        str(root / ".solidifai" / "artifacts"),
        model_path=str(root / "model.py"),
        override_verifier=lambda *_args, **_kwargs: {"ok": True, "nonceId": "override-1"},
    )
    session.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(1, 1, 1))\n"
    )
    return session, root


def test_override_audit_failure_keeps_destination_unchanged(tmp_path, monkeypatch):
    session, root = _override_session(tmp_path)
    destination = root / "exports" / "override.stl"
    destination.parent.mkdir()
    destination.write_bytes(b"existing")

    monkeypatch.setattr(
        session,
        "_record_export_override",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("audit unavailable")),
    )

    result = session.export("stl", str(destination), strict_export=True, override_nonce="opaque")

    assert result == {"ok": False, "error": "export override audit failed"}
    assert destination.read_bytes() == b"existing"


def test_override_export_failure_has_authorization_and_failure_audit(tmp_path, monkeypatch):
    session, root = _override_session(tmp_path)
    destination = root / "exports" / "failed.stl"
    monkeypatch.setattr(
        session_module,
        "exports_export",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("writer failed")),
    )

    result = session.export("stl", str(destination), strict_export=True, override_nonce="opaque")

    assert result["ok"] is False and "writer failed" in result["error"]
    assert not destination.exists()
    records = [
        json.loads(line)
        for line in (root / ".solidifai" / "export-overrides.jsonl").read_text().splitlines()
    ]
    assert [record["outcome"] for record in records] == ["authorized", "failed"]


def test_successful_override_is_audited_before_destination_is_visible(tmp_path, monkeypatch):
    session, root = _override_session(tmp_path)
    destination = root / "exports" / "approved.stl"

    def write_temp(_format, temporary_path, _options, *, objects):
        records = [
            json.loads(line)
            for line in (root / ".solidifai" / "export-overrides.jsonl").read_text().splitlines()
        ]
        assert records[-1]["outcome"] == "authorized"
        assert not destination.exists()
        Path(temporary_path).write_bytes(b"temporary export")
        return temporary_path

    monkeypatch.setattr(session_module, "exports_export", write_temp)

    result = session.export("stl", str(destination), strict_export=True, override_nonce="opaque")

    assert result == {"ok": True, "path": str(destination)}
    assert destination.read_bytes() == b"temporary export"


def test_legacy_export_does_not_use_override_audit(tmp_path, monkeypatch):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    session = Session(artifacts)
    session.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(1, 1, 1))\n"
    )
    monkeypatch.setattr(
        session,
        "_record_export_override",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy audit")),
    )

    assert session.export("stl", str(tmp_path / "legacy.stl"))["ok"] is True


def test_session_export_invalid_option_returns_error(tmp_path):
    artifacts = str(tmp_path / ".solidifai" / "artifacts")
    sess = Session(artifacts)
    sess.execute_script(
        "from build123d import Box\nfrom solidifai import show\nshow(Box(10, 10, 10), name='C')\n"
    )
    res = sess.export("stl", str(tmp_path / "x.stl"), {"nope": 1})
    assert res["ok"] is False
    assert "Unknown option" in res["error"]


# -- round-trip + option behavior ------------------------------------------


def test_export_brep(tmp_path):
    _current_model()
    p = str(tmp_path / "out.brep")
    export("brep", p)
    assert os.path.getsize(p) > 0


def test_export_3mf(tmp_path):
    _current_model()
    p = str(tmp_path / "out.3mf")
    export("3mf", p)
    # 3MF is a zip container; first bytes are the local file header "PK".
    with open(p, "rb") as f:
        assert f.read(2) == b"PK"


def test_export_gltf_text(tmp_path):
    _current_model()
    p = str(tmp_path / "out.gltf")
    export("gltf", p)
    with open(p, "rb") as f:
        head = f.read(64)
    assert head.lstrip()[:1] == b"{"  # JSON glTF, not the binary GLB magic


def test_export_stl_ascii(tmp_path):
    _current_model()
    p = str(tmp_path / "out_ascii.stl")
    export("stl", p, {"ascii": True})
    with open(p, "rb") as f:
        assert f.read(6) == b"solid "


def test_export_stl_binary_default(tmp_path):
    _current_model()
    p = str(tmp_path / "out_bin.stl")
    export("stl", p)
    with open(p, "rb") as f:
        assert f.read(6) != b"solid "


def test_export_step_fixed_timestamp_is_written(tmp_path):
    # OCCT's STEP body is not byte-deterministic, but the header timestamp is
    # honored. Assert the fixed timestamp flows through into the file.
    _current_model()
    p = str(tmp_path / "a.step")
    export("step", p, {"timestamp": "2020-01-01T00:00:00"})
    data = Path(p).read_bytes()
    assert b"2020-01-01T00:00:00" in data


def test_export_3mf_mesh_type_and_part(tmp_path):
    _current_model()
    p = str(tmp_path / "role.3mf")
    export("3mf", p, {"mesh_type": "support", "part_number": "KB-1", "unit": "in"})
    assert os.path.getsize(p) > 0


# -- write-failure and path-normalization guards ---------------------------


def test_export_raises_when_writer_produces_no_file(tmp_path, monkeypatch):
    # build123d's stl/brep/gltf writers return False instead of raising on a
    # failed write, leaving a missing or empty file. A no-op writer stands in
    # for that: export must surface it as an error, not report success.
    from solidifai_engine import exports as _exp

    _current_model()
    monkeypatch.setitem(_exp._WRITERS, "stl", lambda s, p, o: None)
    with pytest.raises(Exception):  # noqa: B017 - any raise beats a silent ok
        export("stl", str(tmp_path / "out.stl"))


def test_export_dotdot_path_writes_a_real_file(tmp_path):
    # A '..' traversal through a not-yet-created "exports" dir must not write
    # through a still-missing directory. Normalizing the path once makes the
    # makedirs target and the writer target agree, so the file lands.
    _current_model()
    raw = str(tmp_path / "exports" / ".." / "leaked.stl")
    out = export("stl", raw)
    assert out == os.path.abspath(raw)
    assert os.path.getsize(out) > 0
