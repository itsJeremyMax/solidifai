"""Read-only access to the host-managed slicer override store (slicers.json).

The desktop host owns this file (Settings -> Slicers); the engine only reads it so
detect / quote / open use the same binary the user configured. Shape::

    {"schema": 1, "slicers": {"orca": {"executablePath": "/path/to/binary"}}}
"""

from __future__ import annotations

import json
import os

from solidifai_engine import paths

SLICERS_NAME = "slicers.json"


def _path() -> str:
    return os.path.join(paths.app_config_dir(), SLICERS_NAME)


def override_executable(provider_id: str) -> str | None:
    """The user-configured executable for ``provider_id``, or None. Never raises."""
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    slicers = data.get("slicers") if isinstance(data, dict) else None
    entry = slicers.get(provider_id) if isinstance(slicers, dict) else None
    if isinstance(entry, dict):
        path = entry.get("executablePath")
        if isinstance(path, str) and path.strip():
            return path
    return None
