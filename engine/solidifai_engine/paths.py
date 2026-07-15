"""Artifact paths and atomic file writes.

Artifacts are written to a temp sibling file (``*.tmp``) and then moved into
place with ``os.replace`` so a reader never observes a half-written file.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import PureWindowsPath

MODEL_GLB = "model.glb"
MODEL_JSON = "model.json"
CURRENT_JSON = "current.json"
GENERATIONS = "generations"
STAGING = ".staging"
JOURNAL = ".publication-journal.json"


@dataclass(frozen=True)
class Publication:
    """One immutable, self-describing model/source publication."""

    build_id: int
    source_hash: str
    publication_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    model_json: str = MODEL_JSON
    model_glb: str = MODEL_GLB


def glb_path(artifacts_dir: str) -> str:
    return os.path.join(artifacts_dir, MODEL_GLB)


def json_path(artifacts_dir: str) -> str:
    return os.path.join(artifacts_dir, MODEL_JSON)


def assets_dir(root: str) -> str:
    """Workspace dir holding copied import files (``<root>/assets``)."""
    return os.path.join(root, "assets")


def imports_path(root: str) -> str:
    """Workspace manifest of imported reference fixtures (``<root>/imports.json``)."""
    return os.path.join(root, "imports.json")


def write_temp_text(final_path: str, text: str) -> str:
    """Write ``text`` to ``final_path + '.tmp'`` (durably) without replacing the
    live file. Returns the temp path; the caller finalizes later."""
    tmp = final_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return tmp


def write_temp_json(final_path: str, obj) -> str:
    """Stage ``obj`` as JSON at ``final_path + '.tmp'`` without replacing."""
    return write_temp_text(final_path, json.dumps(obj, indent=2))


def atomic_finalize(tmp_path: str, final_path: str) -> None:
    """Move an already-written ``tmp_path`` into ``final_path``."""
    os.replace(tmp_path, final_path)


def _fsync_dir(path: str) -> None:
    """Persist a directory entry after a rename or unlink."""
    # Windows does not support opening directories this way. File fsync remains
    # mandatory; the directory durability boundary is explicitly best-effort there.
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _write_atomic_json(path: str, value: dict) -> None:
    tmp = write_temp_text(path, json.dumps(value, indent=2, sort_keys=True))
    atomic_finalize(tmp, path)
    _fsync_dir(os.path.dirname(path) or ".")


def _sha256_path(path: str) -> str | None:
    try:
        digest = sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def publication_path(artifacts_dir: str, publication_id: str) -> str:
    return os.path.join(artifacts_dir, GENERATIONS, publication_id)


def current_path(artifacts_dir: str) -> str:
    return os.path.join(artifacts_dir, CURRENT_JSON)


def read_current_publication(artifacts_dir: str) -> Publication | None:
    return _publication_from_pointer(_read_json(current_path(artifacts_dir)))


def _publication_from_pointer(value: dict | None) -> Publication | None:
    if value is None:
        return None
    try:
        return Publication(
            publication_id=str(value["publicationId"]),
            build_id=int(value["buildId"]),
            source_hash=str(value.get("sourceHash", "")),
            model_json=str(value.get("modelJson", MODEL_JSON)),
            model_glb=str(value.get("modelGlb", MODEL_GLB)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _publication_pointer(publication: Publication) -> dict:
    return {
        "schema": 1,
        "publicationId": publication.publication_id,
        "buildId": publication.build_id,
        "sourceHash": publication.source_hash,
        "modelJson": publication.model_json,
        "modelGlb": publication.model_glb,
    }


def stage_publication(
    artifacts_dir: str,
    publication: Publication,
    *,
    model_json: bytes,
    model_glb: bytes,
    model_source: str | None = None,
    model_path: str | None = None,
    write_set: dict[str, bytes | str] | None = None,
) -> str:
    """Durably stage every file a publication may change without touching live state.

    ``write_set`` is for build-driving workspace inputs (assembly manifests, imports,
    params, briefs, materials, profiles, and references). Keys are workspace-relative.
    They are journaled and applied atomically with the model/source publication.
    """
    if model_source is not None and (
        publication.source_hash != sha256(model_source.encode()).hexdigest()
    ):
        raise ValueError("publication source_hash does not match model_source")
    os.makedirs(artifacts_dir, exist_ok=True)
    staging_root = os.path.join(artifacts_dir, STAGING)
    os.makedirs(staging_root, exist_ok=True)
    staged = os.path.join(staging_root, publication.publication_id)
    if os.path.exists(staged):
        raise FileExistsError(staged)
    os.mkdir(staged)
    _write_bytes(os.path.join(staged, publication.model_json), model_json)
    _write_bytes(os.path.join(staged, publication.model_glb), model_glb)
    inputs: dict[str, str] = {}
    write_set = dict(write_set or {})
    if model_path is not None:
        root = workspace_root(artifacts_dir)
        write_set[relative_workspace_path(root, model_path)] = model_source or ""
    elif model_source is not None:
        write_set.setdefault("model.py", model_source)
    staged_inputs = os.path.join(staged, "inputs")
    for relative, value in write_set.items():
        _validate_relative_path(relative)
        target = os.path.join(staged_inputs, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        payload = value.encode() if isinstance(value, str) else value
        _write_bytes(target, payload)
        inputs[relative] = sha256(payload).hexdigest()
    manifest = {
        "schema": 1,
        "publicationId": publication.publication_id,
        "buildId": publication.build_id,
        "sourceHash": publication.source_hash,
        "modelJson": publication.model_json,
        "modelGlb": publication.model_glb,
        "jsonSha256": sha256(model_json).hexdigest(),
        "glbSha256": sha256(model_glb).hexdigest(),
        "inputs": inputs,
        # Compare with the selected immutable generation, not live mirrors. A
        # failed mirror write may leave those stale while the pointer is valid.
        "deletions": sorted(_publication_inputs(artifacts_dir) - set(inputs)),
    }
    _write_bytes(os.path.join(staged, "manifest.json"), json.dumps(manifest, indent=2).encode())
    _fsync_dir(staged)
    _fsync_dir(staging_root)
    return staged


def _publication_inputs(artifacts_dir: str) -> set[str]:
    current = read_current_publication(artifacts_dir)
    if current is None:
        return set()
    manifest_path = os.path.join(
        publication_path(artifacts_dir, current.publication_id), "manifest.json"
    )
    manifest = _read_json(manifest_path)
    inputs = manifest.get("inputs") if manifest else None
    return set(inputs) if isinstance(inputs, dict) else set()


def _load_staged(staged: str) -> tuple[Publication, dict]:
    manifest = _read_json(os.path.join(staged, "manifest.json"))
    if not manifest:
        raise ValueError("publication staging manifest is missing or invalid")
    publication = Publication(
        publication_id=str(manifest["publicationId"]),
        build_id=int(manifest["buildId"]),
        source_hash=str(manifest.get("sourceHash", "")),
        model_json=str(manifest.get("modelJson", MODEL_JSON)),
        model_glb=str(manifest.get("modelGlb", MODEL_GLB)),
    )
    if _sha256_path(os.path.join(staged, publication.model_json)) != manifest.get("jsonSha256"):
        raise ValueError("staged model JSON hash mismatch")
    if _sha256_path(os.path.join(staged, publication.model_glb)) != manifest.get("glbSha256"):
        raise ValueError("staged model GLB hash mismatch")
    return publication, manifest


def _copy_atomic(source: str, destination: str) -> None:
    tmp = destination + ".tmp"
    try:
        with open(source, "rb") as handle:
            _write_bytes(tmp, handle.read())
        atomic_finalize(tmp, destination)
        _fsync_dir(os.path.dirname(destination) or ".")
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def workspace_root(artifacts_dir: str) -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(artifacts_dir)))


def _validate_relative_path(relative: str) -> None:
    windows = PureWindowsPath(relative)
    if (
        not relative
        or os.path.isabs(relative)
        or windows.is_absolute()
        or windows.drive
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ValueError(f"unsafe write-set path {relative!r}")


def relative_workspace_path(root: str, path: str) -> str:
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, "/")
    _validate_relative_path(relative)
    return relative


def workspace_write_set(root: str) -> dict[str, bytes | str]:
    """Capture build-driving workspace inputs as immutable generation entries."""
    names = {
        "model.py",
        "skeleton.py",
        "assembly.json",
        "settings.json",
        "imports.json",
        "build_brief.json",
        "part_materials.json",
        "requirements.json",
    }
    captured: dict[str, bytes | str] = {}
    for directory, _, files in os.walk(root):
        relative_dir = os.path.relpath(directory, root)
        if relative_dir.startswith((".solidifai", ".git", "exports")):
            continue
        for name in files:
            relative = name if relative_dir == "." else f"{relative_dir}/{name}"
            if (
                name in names
                or relative.startswith(("parts/", "assets/"))
                or "/parts/" in relative
                or "/assets/" in relative
            ):
                with open(os.path.join(directory, name), "rb") as handle:
                    captured[relative] = handle.read()
    return captured


@contextlib.contextmanager
def staged_workspace(root: str):
    """Provide an isolated writable workspace for a build-coupled mutation.

    Its final input set is handed to publication; the real workspace is only
    materialized after the immutable generation pointer is committed.
    """
    parent = os.path.dirname(os.path.abspath(root))
    staged = tempfile.mkdtemp(prefix=".solidifai-build-", dir=parent)
    try:
        shutil.rmtree(staged)
        shutil.copytree(
            root, staged, ignore=shutil.ignore_patterns(".solidifai", ".git", "exports")
        )
        yield staged
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def materialize_publication(
    artifacts_dir: str, staged: str, publication: Publication, manifest: dict
) -> None:
    for relative, expected_hash in manifest.get("inputs", {}).items():
        _validate_relative_path(relative)
        source = os.path.join(staged, "inputs", relative)
        destination = os.path.join(workspace_root(artifacts_dir), relative)
        if _sha256_path(source) != expected_hash:
            raise ValueError(f"staged input hash mismatch for {relative}")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        _copy_atomic(source, destination)
    for relative in manifest.get("deletions", []):
        _validate_relative_path(relative)
        destination = os.path.join(workspace_root(artifacts_dir), relative)
        if os.path.isdir(destination):
            shutil.rmtree(destination)
        else:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(destination)
        _fsync_dir(os.path.dirname(destination) or ".")


def _write_mirrors(artifacts_dir: str, generation: str, publication: Publication) -> None:
    _copy_atomic(os.path.join(generation, publication.model_glb), glb_path(artifacts_dir))
    _copy_atomic(os.path.join(generation, publication.model_json), json_path(artifacts_dir))


def _journal_path(artifacts_dir: str) -> str:
    return os.path.join(artifacts_dir, JOURNAL)


def _write_journal(artifacts_dir: str, journal: dict) -> None:
    _write_atomic_json(_journal_path(artifacts_dir), journal)


def _clear_journal(artifacts_dir: str) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.unlink(_journal_path(artifacts_dir))
        _fsync_dir(artifacts_dir)


def publication_pending(artifacts_dir: str) -> bool:
    """Whether the selected publication still has compatibility mirrors pending."""
    return _read_json(_journal_path(artifacts_dir)) is not None


def publication_matches_workspace(artifacts_dir: str, publication: Publication) -> bool:
    """Verify that root mirrors exactly match a selected generation's inputs."""
    manifest = _read_json(
        os.path.join(publication_path(artifacts_dir, publication.publication_id), "manifest.json")
    )
    if manifest is None:
        return False
    inputs = manifest.get("inputs")
    deletions = manifest.get("deletions", [])
    if not isinstance(inputs, dict) or not isinstance(deletions, list):
        return False
    root = workspace_root(artifacts_dir)
    try:
        for relative, expected_hash in inputs.items():
            _validate_relative_path(relative)
            if (
                not isinstance(expected_hash, str)
                or _sha256_path(os.path.join(root, relative)) != expected_hash
            ):
                return False
        for relative in deletions:
            _validate_relative_path(relative)
            if os.path.exists(os.path.join(root, relative)):
                return False
    except ValueError:
        return False
    return not publication.source_hash or publication.source_hash in inputs.values()


def stale_mirror_matches_prior_source(
    artifacts_dir: str, relative: str, disk_hash: str, source_hash: str
) -> bool:
    """Accept only the prior generation's source while a pointer's mirrors retry.

    This distinguishes a known stale mirror from an arbitrary out-of-band edit.
    """
    current = read_current_publication(artifacts_dir)
    journal = _read_json(_journal_path(artifacts_dir))
    if current is None or current.source_hash != source_hash or not journal:
        return False
    if journal.get("phase") != "pointer":
        return False
    pending = journal.get("publication")
    if not isinstance(pending, dict) or pending.get("publication_id") != current.publication_id:
        return False
    prior = _publication_from_pointer(journal.get("prior"))
    if prior is None:
        return False
    manifest_path = os.path.join(
        publication_path(artifacts_dir, prior.publication_id), "manifest.json"
    )
    manifest = _read_json(manifest_path)
    inputs = manifest.get("inputs") if manifest else None
    return isinstance(inputs, dict) and inputs.get(relative) == disk_hash


def commit_publication(artifacts_dir: str, staged: str) -> Publication:
    """Make a staged source + artifact pair visible as one pointer-selected generation."""
    publication, manifest = _load_staged(staged)
    prior = read_current_publication(artifacts_dir)
    journal = {
        "schema": 1,
        "staged": staged,
        "publication": asdict(publication),
        "prior": _publication_pointer(prior) if prior else None,
        "phase": "intent",
    }
    _write_journal(artifacts_dir, journal)
    generations = os.path.join(artifacts_dir, GENERATIONS)
    os.makedirs(generations, exist_ok=True)
    generation = publication_path(artifacts_dir, publication.publication_id)
    if not os.path.exists(generation):
        os.replace(staged, generation)
        _fsync_dir(generations)
        _fsync_dir(artifacts_dir)
    journal["phase"] = "generation"
    _write_journal(artifacts_dir, journal)
    _write_atomic_json(current_path(artifacts_dir), _publication_pointer(publication))
    journal["phase"] = "pointer"
    _write_journal(artifacts_dir, journal)
    # Compatibility roots are never part of success/failure semantics. The current
    # pointer selects a validated immutable generation before this best-effort copy.
    try:
        materialize_publication(artifacts_dir, generation, publication, manifest)
        _write_mirrors(artifacts_dir, generation, publication)
    except OSError:
        return publication
    _clear_journal(artifacts_dir)
    prune_publications(artifacts_dir)
    return publication


def recover_publication(artifacts_dir: str) -> Publication | None:
    """Finish an interrupted valid publication, otherwise retain the prior pointer."""
    current = read_current_publication(artifacts_dir)
    journal = _read_json(_journal_path(artifacts_dir))
    prior = _publication_from_pointer(journal.get("prior")) if journal else None

    def recover_prior() -> Publication | None:
        if prior is None:
            return None
        fallback_generation = publication_path(artifacts_dir, prior.publication_id)
        fallback, manifest = _load_staged(fallback_generation)
        materialize_publication(artifacts_dir, fallback_generation, fallback, manifest)
        _write_mirrors(artifacts_dir, fallback_generation, fallback)
        _write_atomic_json(current_path(artifacts_dir), _publication_pointer(fallback))
        _clear_journal(artifacts_dir)
        return fallback

    if current is not None:
        generation = publication_path(artifacts_dir, current.publication_id)
        try:
            publication, manifest = _load_staged(generation)
            materialize_publication(artifacts_dir, generation, publication, manifest)
            _write_mirrors(artifacts_dir, generation, publication)
            _clear_journal(artifacts_dir)
            return current
        except (OSError, ValueError):
            with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
                return recover_prior()
            return None
    if not journal:
        return None
    if journal.get("phase") == "pointer":
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
            return recover_prior()
        return None
    staged = journal.get("staged")
    if not isinstance(staged, str):
        _clear_journal(artifacts_dir)
        return read_current_publication(artifacts_dir)
    try:
        publication, manifest = (
            _load_staged(staged)
            if os.path.exists(staged)
            else _load_staged(
                publication_path(artifacts_dir, str(journal["publication"]["publication_id"]))
            )
        )
        generation = publication_path(artifacts_dir, publication.publication_id)
        if not os.path.exists(generation):
            os.makedirs(os.path.dirname(generation), exist_ok=True)
            os.replace(staged, generation)
            _fsync_dir(os.path.dirname(generation))
        _write_atomic_json(current_path(artifacts_dir), _publication_pointer(publication))
    except (OSError, ValueError, KeyError, TypeError):
        _clear_journal(artifacts_dir)
        return read_current_publication(artifacts_dir)
    try:
        materialize_publication(artifacts_dir, generation, publication, manifest)
        _write_mirrors(artifacts_dir, generation, publication)
    except OSError:
        return publication
    _clear_journal(artifacts_dir)
    prune_publications(artifacts_dir)
    return publication


def prune_publications(artifacts_dir: str, keep: int = 4) -> None:
    """Remove only older immutable generations; current and recovery predecessor stay."""
    generations = os.path.join(artifacts_dir, GENERATIONS)
    if not os.path.isdir(generations):
        return
    protected = {p.publication_id for p in [read_current_publication(artifacts_dir)] if p}
    journal = _read_json(_journal_path(artifacts_dir)) or {}
    prior = journal.get("prior")
    if isinstance(prior, dict) and isinstance(prior.get("publicationId"), str):
        protected.add(prior["publicationId"])
    entries = sorted(
        (entry for entry in os.scandir(generations) if entry.is_dir()),
        key=lambda entry: entry.stat().st_mtime_ns,
        reverse=True,
    )
    protected.update(entry.name for entry in entries[:keep])
    for entry in entries:
        if entry.name not in protected:
            shutil.rmtree(entry.path)
    _fsync_dir(generations)


def app_config_dir() -> str:
    """App-level config directory, created lazily.

    Honors ``SOLIDIFAI_CONFIG_DIR`` (set by the host) so the engine and app share
    one location; the platform fallback is for standalone runs (tests, MCP, CLI).

    macOS:   ~/Library/Application Support/solidifai
    Linux:   $XDG_CONFIG_HOME/solidifai  (or ~/.config/solidifai)
    Windows: %APPDATA%/solidifai
    """
    override = os.environ.get("SOLIDIFAI_CONFIG_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return override

    import platform

    system = platform.system()
    if system == "Darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    elif system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    d = os.path.join(base, "solidifai")
    os.makedirs(d, exist_ok=True)
    return d
