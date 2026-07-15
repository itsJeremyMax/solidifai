"""Session import ops: stage / import_reference / remove / apply."""

from build123d import Box

import solidifai
from solidifai_engine import imports_manifest
from solidifai_engine.exports import export as engine_export
from solidifai_engine.session import Session

_MODEL = (
    "from build123d import Box\n"
    "import solidifai\n"
    "solidifai.show(Box(20, 20, 20), name='Body', material='pla')\n"
)


def _write_geom(path: str, fmt: str):
    """Make a real CAD/mesh file on disk to import (before any session build)."""
    solidifai.reset_registry()
    solidifai.show(Box(8, 8, 8))
    engine_export(fmt, path)
    solidifai.reset_registry()


def _session(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_MODEL, encoding="utf-8")
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert s.run_file(str(root / "model.py"))["ok"]
    return s, root


def test_import_reference_copies_records_and_shows(tmp_path):
    src = tmp_path / "pcb.stl"
    _write_geom(str(src), "stl")
    s, root = _session(tmp_path)

    res = s.import_reference(str(src))
    assert res["ok"], res
    assert (root / "assets" / "pcb.stl").exists()
    assert len(imports_manifest.load(str(root))) == 1

    refs = [o for o in s._objects if o.role == "reference"]
    parts = [o for o in s._objects if o.role == "part"]
    assert len(refs) == 1
    assert any(p.name == "Body" for p in parts)  # the designed part is still there


def test_reference_survives_rebuild(tmp_path):
    src = tmp_path / "pcb.stl"
    _write_geom(str(src), "stl")
    s, root = _session(tmp_path)
    s.import_reference(str(src))

    s.run_file(str(root / "model.py"))  # simulate reload / rebuild
    assert any(o.role == "reference" for o in s._objects)


def test_remove_import(tmp_path):
    src = tmp_path / "pcb.stl"
    _write_geom(str(src), "stl")
    s, root = _session(tmp_path)
    entry = s.import_reference(str(src))["import"]

    assert s.remove_import(entry["id"])["ok"]
    assert not any(o.role == "reference" for o in s._objects)
    assert imports_manifest.load(str(root)) == []


def test_stage_import_copies_without_manifest(tmp_path):
    src = tmp_path / "bracket.step"
    _write_geom(str(src), "step")
    s, root = _session(tmp_path)

    res = s.stage_import(str(src))
    assert res["ok"], res
    assert res["path"] == "assets/bracket.step"
    assert res["format"] == "step"
    assert (root / "assets" / "bracket.step").exists()
    assert imports_manifest.load(str(root)) == []  # staging alone records nothing


def test_stage_stp_preserves_legacy_manifest_format(tmp_path):
    src = tmp_path / "bracket.stp"
    _write_geom(str(src), "step")
    s, _root = _session(tmp_path)

    assert s.stage_import(str(src))["format"] == "stp"


def test_bad_reference_path_is_skipped_not_fatal(tmp_path):
    s, root = _session(tmp_path)
    imports_manifest.add(
        str(root), {"name": "ghost", "path": "assets/missing.stl", "format": "stl"}
    )

    assert s.run_file(str(root / "model.py"))["ok"]  # build survives a missing reference
    assert not any(o.role == "reference" for o in s._objects)


def test_required_bad_reference_is_reported_and_blocks_readiness(tmp_path):
    bad_step = tmp_path / "broken.step"
    bad_step.write_text("not a STEP file", encoding="utf-8")
    s, root = _session(tmp_path)
    s.propose_build(
        {
            "schema": 2,
            "parts": [],
            "requirements": [],
            "dimensions": [],
            "interfaces": [],
            "references": [{"id": "board", "required": True}],
            "assumptions": [],
            "manufacturing": [],
            "obligations": [],
        },
        expected_revision=0,
    )

    result = s.import_reference(str(bad_step), name="board", required=True)

    assert result["ok"]
    assert s.get_reference_status()["board"]["status"] == "failed"
    assert s.get_readiness()["level"] == "blocked"
    assert imports_manifest.load(str(root))[0]["required"] is True


def test_unsupported_format_rejected(tmp_path):
    src = tmp_path / "thing.iges"
    src.write_text("not real", encoding="utf-8")
    s, root = _session(tmp_path)
    assert s.import_reference(str(src))["ok"] is False


# -- script-shown references (the inside-out-packaging convention) -----------

_MODEL_WITH_REF = (
    "from build123d import Box\n"
    "import solidifai\n"
    "solidifai.show(Box(20, 20, 20) - Box(16, 16, 16), name='Shell')\n"
    "solidifai.show(Box(12, 12, 12), name='ref: pcb', role='reference')\n"
)


def _ref_session(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_MODEL_WITH_REF, encoding="utf-8")
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert s.run_file(str(root / "model.py"))["ok"]
    return s, root


def test_script_shown_reference_survives_rooted_build(tmp_path):
    # show(..., role="reference") in model.py must survive the build in a
    # workspace-rooted session (ghosted, not exported, but still visible to
    # interference/containment checks) — the manifest refresh must not sweep it.
    s, _root = _ref_session(tmp_path)
    assert [o.name for o in s._objects if o.role == "reference"] == ["ref: pcb"]


def test_script_reference_coexists_with_manifest_reference(tmp_path):
    src = tmp_path / "pcb.stl"
    _write_geom(str(src), "stl")
    s, root = _ref_session(tmp_path)
    assert s.import_reference(str(src))["ok"]

    refs = [o for o in s._objects if o.role == "reference"]
    assert len(refs) == 2  # script ref + manifest ref

    s.run_file(str(root / "model.py"))  # rebuild: refresh must not duplicate
    refs = [o for o in s._objects if o.role == "reference"]
    assert len(refs) == 2
