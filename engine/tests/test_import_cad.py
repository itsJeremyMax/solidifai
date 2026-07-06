"""Part role on shown objects + the import_cad loader."""

import pytest
from build123d import Box

import solidifai
from solidifai_engine.exports import export as engine_export


def setup_function():
    solidifai.reset_registry()
    solidifai.set_workspace_root(None)


def test_default_role_is_part():
    obj = solidifai.show(Box(1, 1, 1))
    assert obj.role == "part"


def test_reference_role_passes_through():
    obj = solidifai.show(Box(1, 1, 1), name="ref", role="reference")
    assert solidifai._registry()[-1].role == "reference"
    assert obj.role == "reference"


def test_import_step_roundtrips_to_a_solid(tmp_path):
    p = tmp_path / "block.step"
    solidifai.show(Box(10, 10, 10))
    engine_export("step", str(p))
    solidifai.reset_registry()

    solidifai.set_workspace_root(str(tmp_path))
    obj = solidifai.import_cad("block.step")  # relative -> resolved vs root
    assert float(obj.volume) > 0


def test_import_stl_loads_a_surface(tmp_path):
    p = tmp_path / "block.stl"
    solidifai.show(Box(10, 10, 10))
    engine_export("stl", str(p))
    solidifai.reset_registry()

    obj = solidifai.import_cad(str(p))  # absolute path honored as-is
    assert obj is not None  # a Face (surface mesh); no volume guarantee


def test_unsupported_extension_raises(tmp_path):
    solidifai.set_workspace_root(str(tmp_path))
    with pytest.raises(ValueError):
        solidifai.import_cad("part.iges")


def test_missing_file_raises(tmp_path):
    solidifai.set_workspace_root(str(tmp_path))
    with pytest.raises(FileNotFoundError):
        solidifai.import_cad("nope.step")
