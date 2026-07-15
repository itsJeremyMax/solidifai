"""Load external CAD/mesh files as build123d objects for ``model.py``.

``import_cad(path)`` resolves only adapters that are executable in the packaged
build123d dependency set. Relative paths resolve against the workspace root the
engine sets via ``set_workspace_root`` before each build (the engine never chdirs
-- that would be a process-global side effect under the request lock).
"""

from __future__ import annotations

import os

from solidifai_engine.import_adapters import get_adapter

_WORKSPACE_ROOT: str | None = None


def set_workspace_root(root: str | None) -> None:
    """Set the base dir that ``import_cad`` resolves relative paths against."""
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = root


def workspace_root() -> str | None:
    """The workspace root the engine set for the current build (None for bare
    sessions); lets sibling helpers (std) resolve per-workspace config."""
    return _WORKSPACE_ROOT


def _resolve(path: str) -> str:
    if os.path.isabs(path):
        return path
    base = _WORKSPACE_ROOT or os.getcwd()
    return os.path.join(base, path)


def import_cad(path: str):
    """Load a CAD/mesh file as a build123d object.

    ``path`` may be absolute or relative to the workspace root. Raises
    ``ValueError`` for an unavailable extension and ``FileNotFoundError`` for a
    missing file. See ``import_capabilities`` for the package's current formats.
    """
    adapter = get_adapter(path)
    resolved = _resolve(path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"CAD file not found: {path!r} (resolved to {resolved!r})")
    # Local import avoids a circular import at module load (solidifai/__init__ imports this module).
    from solidifai import _record_asset

    _record_asset(resolved)
    return adapter.loader(resolved)
