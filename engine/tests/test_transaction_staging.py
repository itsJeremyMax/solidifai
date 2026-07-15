"""Build-coupled workspace mutations publish only after the generation pointer."""

import json
import shutil

from build123d import Box

import solidifai
from solidifai_engine import paths
from solidifai_engine.exports import export as engine_export
from solidifai_engine.session import Session

ASSEMBLY_FIXTURE = "tests/fixtures/assembly_enclosure"
MODEL = (
    "from build123d import Box\n"
    "import solidifai\n"
    "solidifai.show(Box(20, 20, 20), name='Body', material='pla')\n"
)


def _fail_commit(monkeypatch):
    def fail(*_args):
        raise OSError("full")

    monkeypatch.setattr(paths, "commit_publication", fail)


def _assembly_session(tmp_path):
    root = tmp_path / "workspace"
    shutil.copytree(ASSEMBLY_FIXTURE, root)
    artifacts = root / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    session = Session(str(artifacts), model_path=str(root / "assembly.json"))
    session.startup()
    return session, root, artifacts


def _model_session(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    model = root / "model.py"
    model.write_text(MODEL)
    artifacts = root / ".solidifai" / "artifacts"
    session = Session(str(artifacts), model_path=str(model))
    assert session.run_file(str(model))["ok"]
    return session, root, artifacts


def _pointer(artifacts):
    return json.loads((artifacts / "current.json").read_text())


def test_part_and_manifest_stay_unmodified_when_publication_fails(tmp_path, monkeypatch):
    session, root, artifacts = _assembly_session(tmp_path)
    prior_part = (root / "parts" / "base.py").read_text()
    prior_manifest = (root / "assembly.json").read_text()
    prior_pointer = _pointer(artifacts)
    prior_objects = session._objects
    _fail_commit(monkeypatch)

    result = session.set_part("base", "raise RuntimeError('bad pending part')\n")

    assert result["ok"] is False
    assert (root / "parts" / "base.py").read_text() == prior_part
    assert (root / "assembly.json").read_text() == prior_manifest
    assert _pointer(artifacts) == prior_pointer
    assert session._objects is prior_objects


def test_occurrences_and_parameter_settings_stay_unmodified_when_publication_fails(
    tmp_path, monkeypatch
):
    session, root, artifacts = _assembly_session(tmp_path)
    prior_manifest = (root / "assembly.json").read_text()
    settings_path = root / "settings.json"
    prior_settings = settings_path.read_text() if settings_path.exists() else None
    prior_pointer = _pointer(artifacts)
    _fail_commit(monkeypatch)

    occurrence = session.set_occurrences("base", [{"frame": None, "mirror": None}])
    params = session.set_params({"body_w": 80.0})

    assert occurrence["ok"] is False
    assert params["ok"] is False
    assert (root / "assembly.json").read_text() == prior_manifest
    assert (settings_path.read_text() if settings_path.exists() else None) == prior_settings
    assert _pointer(artifacts) == prior_pointer
    assert session.get_params()["values"]["body_w"] == 60.0


def test_import_manifest_and_asset_stay_unmodified_when_publication_fails(tmp_path, monkeypatch):
    source = tmp_path / "reference.stl"
    solidifai.show(Box(3, 3, 3))
    engine_export("stl", str(source))
    solidifai.reset_registry()
    session, root, artifacts = _model_session(tmp_path)
    prior_pointer = _pointer(artifacts)
    _fail_commit(monkeypatch)

    result = session.import_reference(str(source))

    assert result["ok"] is False
    assert not (root / "assets" / "reference.stl").exists()
    assert not (root / "imports.json").exists()
    assert _pointer(artifacts) == prior_pointer


def test_material_override_stays_unmodified_when_publication_fails(tmp_path, monkeypatch):
    session, root, artifacts = _model_session(tmp_path)
    prior_pointer = _pointer(artifacts)
    _fail_commit(monkeypatch)

    result = session.set_part_material("body", "aluminum")

    assert result["ok"] is False
    assert not (root / "part_materials.json").exists()
    assert session._material_overrides == {}
    assert _pointer(artifacts) == prior_pointer


def test_removed_part_is_a_generation_tombstone(tmp_path):
    session, root, artifacts = _assembly_session(tmp_path)
    prior = _pointer(artifacts)

    assert session.remove_part("lid")["ok"] is True
    assert session.remove_part("hinge")["ok"] is True
    result = session.remove_part("base")

    assert result["ok"] is True
    assert result["empty"] is True
    assert not (root / "parts" / "base.py").exists()
    current = _pointer(artifacts)
    assert current["publicationId"] != prior["publicationId"]
    model = json.loads(
        (artifacts / "generations" / current["publicationId"] / "model.json").read_text()
    )
    assert model["objects"] == []


def test_empty_subassembly_scaffold_is_materialized_after_staged_publish(tmp_path):
    session, root, artifacts = _assembly_session(tmp_path)
    prior = _pointer(artifacts)

    result = session.add_subassembly("latch", attach="base_frame", inputs=["body_w"])

    assert result["ok"] is True
    assert (root / "latch" / "assembly.json").exists()
    manifest = json.loads((root / "assembly.json").read_text())
    assert any(
        child["id"] == "latch" and child["kind"] == "assembly" for child in manifest["children"]
    )
    current = _pointer(artifacts)
    assert current["publicationId"] != prior["publicationId"]
    published = json.loads(
        (artifacts / "generations" / current["publicationId"] / "manifest.json").read_text()
    )
    assert {"assembly.json", "latch/assembly.json"} <= set(published["inputs"])


def test_nested_assembly_sources_and_manifests_are_published_and_tombstoned(tmp_path):
    root = tmp_path / "workspace"
    artifacts = root / ".solidifai" / "artifacts"
    nested = root / "hinge"
    (nested / "parts").mkdir(parents=True)
    (root / "assembly.json").write_text('{"schema": 1, "children": []}')
    (nested / "assembly.json").write_text('{"schema": 1, "children": []}')
    (nested / "parts" / "pin.py").write_text("# pin\n")
    artifacts.mkdir(parents=True)

    first = paths.Publication(build_id=1, source_hash="")
    first_stage = paths.stage_publication(
        str(artifacts),
        first,
        model_json=b"{}",
        model_glb=b"glb",
        write_set=paths.workspace_write_set(str(root)),
    )
    paths.commit_publication(str(artifacts), first_stage)
    first_manifest = json.loads(
        (artifacts / "generations" / first.publication_id / "manifest.json").read_text()
    )
    assert {"assembly.json", "hinge/assembly.json", "hinge/parts/pin.py"} <= set(
        first_manifest["inputs"]
    )

    (nested / "parts" / "pin.py").unlink()
    second = paths.Publication(build_id=2, source_hash="")
    second_stage = paths.stage_publication(
        str(artifacts),
        second,
        model_json=b"{}",
        model_glb=b"glb",
        write_set=paths.workspace_write_set(str(root)),
    )
    paths.commit_publication(str(artifacts), second_stage)
    second_manifest = json.loads(
        (artifacts / "generations" / second.publication_id / "manifest.json").read_text()
    )
    assert "hinge/parts/pin.py" in second_manifest["deletions"]


def test_history_records_the_materialized_assembly_generation(tmp_path):
    session, root, _artifacts = _assembly_session(tmp_path)

    edited = (root / "parts" / "base.py").read_text().replace('name="Base"', 'name="Edited Base"')
    assert session.set_part("base", edited)["ok"]

    assert session.history is not None
    source = session.history._blob_at(session.history.commits[-1], "parts/base.py")
    assert source == (root / "parts" / "base.py").read_bytes()


def test_invalid_current_pointer_recovers_journal_prior_generation(tmp_path):
    session, _root, artifacts = _assembly_session(tmp_path)
    prior = _pointer(artifacts)
    (artifacts / "current.json").write_text("{}")
    (artifacts / ".publication-journal.json").write_text(
        json.dumps({"schema": 1, "phase": "pointer", "prior": prior, "staged": "missing"})
    )

    recovered = paths.recover_publication(str(artifacts))

    assert recovered is not None
    assert recovered.publication_id == prior["publicationId"]
    assert _pointer(artifacts)["publicationId"] == prior["publicationId"]


def test_set_params_accepts_authoritative_source_after_stale_mirror(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    model = root / "model.py"
    old = (
        "from build123d import Box\nimport solidifai\n"
        "PARAMS = {'size': {'value': 10, 'min': 1, 'max': 20}}\n"
        "def build(size=10): solidifai.show(Box(size, size, size))\nbuild()\n"
    )
    new = old.replace("'value': 10", "'value': 12").replace("size=10", "size=12")
    model.write_text(old)
    artifacts = root / ".solidifai" / "artifacts"
    session = Session(str(artifacts), model_path=str(model))
    assert session.run_file(str(model))["ok"]

    original_copy = paths._copy_atomic

    def fail_source_mirror(source, destination):
        if destination == str(model):
            raise OSError("mirror unavailable")
        original_copy(source, destination)

    monkeypatch.setattr(paths, "_copy_atomic", fail_source_mirror)
    assert session.execute_script(new)["ok"]
    assert model.read_text() == old

    monkeypatch.setattr(paths, "_copy_atomic", original_copy)
    assert session.set_params({"size": 13})["ok"]


def test_failed_publication_does_not_create_history_or_checkpoint(tmp_path, monkeypatch):
    session, _root, _artifacts = _assembly_session(tmp_path)
    assert session.history is not None
    commits = list(session.history.commits)
    _fail_commit(monkeypatch)

    assert session.set_part("base", "raise RuntimeError('bad')\n")["ok"] is False
    assert session.history.commits == commits


def test_startup_records_recovered_model_source_once_and_undoes_it(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    model = root / "model.py"
    old = "from build123d import Box\nimport solidifai\nsolidifai.show(Box(10, 10, 10))\n"
    new = old.replace("10, 10, 10", "20, 20, 20")
    model.write_text(old)
    artifacts = root / ".solidifai" / "artifacts"
    session = Session(str(artifacts), model_path=str(model))
    assert session.run_file(str(model))["ok"]
    assert session.history is not None
    commits_before = len(session.history.commits)
    original_copy = paths._copy_atomic

    def fail_model_mirror(source, destination):
        if destination == str(model):
            raise OSError("mirror unavailable")
        original_copy(source, destination)

    monkeypatch.setattr(paths, "_copy_atomic", fail_model_mirror)
    assert session.execute_script(new)["ok"]
    assert len(session.history.commits) == commits_before
    monkeypatch.setattr(paths, "_copy_atomic", original_copy)

    reopened = Session(str(artifacts), model_path=str(model))
    reopened.startup()
    assert reopened.history is not None
    assert len(reopened.history.commits) == commits_before + 1
    assert reopened.history._blob_at(reopened.history.commits[-1], "model.py") == new.encode()

    reopened.startup()
    assert len(reopened.history.commits) == commits_before + 1
    assert reopened.undo()["ok"]
    assert model.read_text() == old


def test_startup_records_recovered_assembly_structure_once(tmp_path, monkeypatch):
    session, root, artifacts = _assembly_session(tmp_path)
    assert session.history is not None
    commits_before = len(session.history.commits)
    old = (root / "parts" / "base.py").read_text()
    new = old.replace('name="Base"', 'name="Recovered Base"')
    original_copy = paths._copy_atomic

    def fail_part_mirror(source, destination):
        if destination == str(root / "parts" / "base.py"):
            raise OSError("mirror unavailable")
        original_copy(source, destination)

    monkeypatch.setattr(paths, "_copy_atomic", fail_part_mirror)
    assert session.set_part("base", new)["ok"]
    assert len(session.history.commits) == commits_before
    monkeypatch.setattr(paths, "_copy_atomic", original_copy)

    reopened = Session(str(artifacts), model_path=str(root / "assembly.json"))
    reopened.startup()
    assert reopened.history is not None
    assert len(reopened.history.commits) == commits_before + 1
    assert reopened.history._blob_at(reopened.history.commits[-1], "parts/base.py") == new.encode()
    assert (
        reopened.history._blob_at(reopened.history.commits[-1], "assembly.json")
        == (root / "assembly.json").read_bytes()
    )

    reopened.startup()
    assert len(reopened.history.commits) == commits_before + 1


def test_startup_reconstructs_missing_root_mirrors_from_current_generation(tmp_path):
    session, root, artifacts = _assembly_session(tmp_path)
    expected = (root / "parts" / "base.py").read_text()
    (root / "parts" / "base.py").unlink()

    reopened = Session(str(artifacts), model_path=str(root / "assembly.json"))
    reopened.startup()

    assert (root / "parts" / "base.py").read_text() == expected
    assert reopened.last_ok is True
