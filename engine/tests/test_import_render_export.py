"""Role-aware render (opacity/mass), export filter, DFM skip."""

import json

from build123d import Box

import solidifai
from solidifai_engine import imports_manifest, paths
from solidifai_engine.exports import export as engine_export
from solidifai_engine.session import Session

_MODEL = (
    "from build123d import Box\n"
    "import solidifai\n"
    "solidifai.show(Box(20, 20, 20), name='Body', material='pla')\n"
)


def _write_stl(path: str):
    solidifai.reset_registry()
    solidifai.show(Box(8, 8, 8))
    engine_export("stl", path)
    solidifai.reset_registry()


def _write_box(path: str, size_xyz: tuple[float, float, float], fmt: str = "stl"):
    solidifai.reset_registry()
    solidifai.show(Box(*size_xyz))
    engine_export(fmt, path)
    solidifai.reset_registry()


def _session_with_reference(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_MODEL, encoding="utf-8")
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    s.run_file(str(root / "model.py"))
    src = tmp_path / "pcb.stl"
    _write_stl(str(src))
    s.import_reference(str(src))
    return s, root


def _model_json(s):
    with open(paths.json_path(s.artifacts_dir), encoding="utf-8") as f:
        return json.load(f)


def test_model_json_role_and_opacity(tmp_path):
    s, root = _session_with_reference(tmp_path)
    objs = {o["name"]: o for o in _model_json(s)["objects"]}
    assert objs["Body"]["role"] == "part"
    assert objs["Body"]["appearance"]["opacity"] == 1.0
    ref = next(o for o in objs.values() if o["role"] == "reference")
    assert ref["appearance"]["opacity"] == 0.35
    assert ref["mass"] is None  # references carry no mass


def test_model_summary_stays_watertight_with_open_reference(tmp_path):
    # The Body is a watertight box; an open STL Face reference must NOT flip the
    # model's manifold flag (summary is computed from parts only).
    s, root = _session_with_reference(tmp_path)
    assert _model_json(s)["manifold"] is True


def test_export_excludes_references(tmp_path):
    s, root = _session_with_reference(tmp_path)
    out = s.export("step", str(tmp_path / "out.step"))
    assert out["ok"], out
    # Re-import the exported STEP: it should contain only the Body (1 solid),
    # never the reference.
    solidifai.set_workspace_root(str(tmp_path))
    reimported = solidifai.import_cad(out["path"])
    assert len(reimported.solids()) == 1


def test_dfm_skips_references(tmp_path):
    s, root = _session_with_reference(tmp_path)
    rep = s.analyze_dfm()
    ref = next(p for p in rep["parts"] if p["process"] == "reference")
    assert ref["evaluated"] is False
    assert ref["violations"] == []
    body = next(p for p in rep["parts"] if p["partName"] == "Body")
    assert body["evaluated"] is True


def test_interference_includes_references(tmp_path):
    s, root = _session_with_reference(tmp_path)
    rep = s.check_interferences()
    names = {p["name"] for p in rep["parts"]}
    assert "Body" in names
    assert any(n != "Body" for n in names)  # the reference is analyzed too


def test_measure_excludes_reference_mass_from_total(tmp_path):
    s, _root = _session_with_reference(tmp_path)

    rep = s.measure()

    assert rep["ok"] is True
    assert rep["summary"]["parts"] == 1
    assert rep["total"]["volume"] == 8000.0
    reference = next(p for p in rep["parts"] if p.get("role") == "reference")
    assert reference == {
        "partId": reference["partId"],
        "partName": reference["partName"],
        "role": "reference",
    }


def test_stress_check_omits_reference_bodies(tmp_path):
    s, _root = _session_with_reference(tmp_path)

    rep = s.stress_check()

    assert rep["ok"] is True
    assert rep["summary"]["parts"] == 1
    assert [part["partName"] for part in rep["parts"]] == ["Body"]


def test_min_wall_requirements_ignore_reference_bodies(tmp_path):
    root = tmp_path / "ws-thin-ref"
    root.mkdir()
    (root / "model.py").write_text(_MODEL, encoding="utf-8")
    session = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert session.run_file(str(root / "model.py"))["ok"] is True
    thin_ref = tmp_path / "shim.stl"
    _write_box(str(thin_ref), (8, 8, 0.2))
    assert session.import_reference(str(thin_ref))["ok"] is True
    session.set_requirements([{"id": "wall", "quantity": "min_wall", "op": ">=", "bound": 1.0}])

    rep = session.check_requirements()

    by_id = {item["id"]: item for item in rep["requirements"]}
    assert by_id["wall"]["pass"] is True
