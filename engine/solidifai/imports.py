"""Load external CAD/mesh files as build123d objects for ``model.py``.

``import_cad(path)`` is the shared loader behind both workflows: a STEP/STP/BREP
file comes in as an exact, modifiable solid; an STL comes in as a surface mesh
(a ``Face``) suitable for a ghosted reference. Relative paths resolve against the
workspace root the engine sets via ``set_workspace_root`` before each build (the
engine never chdirs -- that would be a process-global side effect under the
request lock). build123d is imported lazily so ``import solidifai`` stays light.

3MF import is intentionally not here yet: build123d has no ``import_3mf`` (it is
export-only), so it needs a separate lib3mf mesh reader. STL covers the mesh
reference case; the manifest/role/render/export path is format-agnostic, so a 3MF
loader slots in here later with nothing else to change.
"""

from __future__ import annotations

import os

_WORKSPACE_ROOT: str | None = None

# Supported extensions -> the build123d importer name (resolved lazily).
_LOADER_NAMES = {
    ".step": "import_step",
    ".stp": "import_step",
    ".brep": "import_brep",
    ".stl": "import_stl",
}


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

    ``.step``/``.stp``/``.brep`` -> exact solid (modifiable with build123d ops);
    ``.stl`` -> a surface mesh (``Face``), good for a reference fixture. ``path``
    may be absolute or relative to the workspace root. Raises ``ValueError`` for
    an unsupported extension and ``FileNotFoundError`` for a missing file.
    """
    ext = os.path.splitext(path)[1].lower()
    loader_name = _LOADER_NAMES.get(ext)
    if loader_name is None:
        supported = ", ".join(sorted(_LOADER_NAMES))
        raise ValueError(f"unsupported import format {ext!r}; expected one of {supported}")
    resolved = _resolve(path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"CAD file not found: {path!r} (resolved to {resolved!r})")
    # Local import avoids a circular import at module load (solidifai/__init__ imports this module).
    from solidifai import _record_asset

    _record_asset(resolved)
    import build123d

    return getattr(build123d, loader_name)(resolved)
