"""Artifact paths and atomic file writes.

Artifacts are written to a temp sibling file (``*.tmp``) and then moved into
place with ``os.replace`` so a reader never observes a half-written file.
"""

from __future__ import annotations

import json
import os

MODEL_GLB = "model.glb"
MODEL_JSON = "model.json"


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
