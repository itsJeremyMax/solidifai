import os
from pathlib import Path

import pytest
from build123d import Box

from solidifai import reset_registry, show
from solidifai_engine.exports import (
    SUPPORTED,
    export,
    options_schema,
    validate_options,
)
from solidifai_engine.session import Session


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
