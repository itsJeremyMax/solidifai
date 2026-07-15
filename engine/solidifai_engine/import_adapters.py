"""Executable CAD import adapters and their public capabilities."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

RoleCapability = Literal["modifiable_solid", "reference_mesh", "sketch"]


@dataclass(frozen=True)
class ImportAdapter:
    format_id: str
    extensions: tuple[str, ...]
    role_capability: RoleCapability
    loader: Callable[[str], Any]


_CANDIDATES = (
    ("step", (".step", ".stp"), "modifiable_solid", "import_step"),
    ("brep", (".brep",), "modifiable_solid", "import_brep"),
    ("stl", (".stl",), "reference_mesh", "import_stl"),
    ("svg", (".svg",), "sketch", "import_svg"),
)
_RECOMMENDED_INTERCHANGE_FORMATS = ("step", "stl", "svg")


def _adapters() -> tuple[ImportAdapter, ...]:
    """Return only loaders executable in the installed build123d package."""
    import build123d

    return tuple(
        ImportAdapter(format_id, extensions, role, loader)
        for format_id, extensions, role, loader_name in _CANDIDATES
        if callable(loader := getattr(build123d, loader_name, None))
    )


def _format_id(path_or_format: str) -> str:
    extension = os.path.splitext(path_or_format)[1].lower()
    return extension.lstrip(".") if extension else path_or_format.lower().lstrip(".")


def unsupported_diagnostic(path_or_format: str) -> dict:
    """A serializable error payload for an input without an executable adapter."""
    format_id = _format_id(path_or_format) or "unknown"
    return {
        "code": "unsupported_format",
        "format": format_id,
        "message": f"unsupported import format {format_id!r}",
        "recommendedFormats": list(_RECOMMENDED_INTERCHANGE_FORMATS),
    }


def get_adapter(path_or_format: str) -> ImportAdapter:
    """Resolve a registered adapter by extension or format id."""
    format_id = _format_id(path_or_format)
    for adapter in _adapters():
        if format_id == adapter.format_id or f".{format_id}" in adapter.extensions:
            return adapter
    diagnostic = unsupported_diagnostic(path_or_format)
    raise ValueError(
        f"{diagnostic['message']}; convert to one of {', '.join(diagnostic['recommendedFormats'])}"
    )


def import_capabilities() -> dict[str, dict]:
    """Return package-truthful format metadata for clients and file pickers."""
    return {
        adapter.format_id: {
            "extensions": list(adapter.extensions),
            "roleCapability": adapter.role_capability,
        }
        for adapter in _adapters()
    }
