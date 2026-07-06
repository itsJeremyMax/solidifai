"""App-level named destinations store.

Destinations belong to the user's machine, not to a workspace, so they live in
the app config directory rather than any per-workspace file.

A destination is::

    {id, name, kind, provider, printerProfile?, filamentProfile?,
     processProfile?, connection?}

``kind`` defaults to "local". ``connection`` is reserved for future remote
providers and is not vendor-specific.
"""

from __future__ import annotations

import json
import os

from solidifai_engine import paths

DEST_NAME = "destinations.json"
SCHEMA = 1


def config_dir() -> str:
    """Return the app-level config directory. Monkeypatch this in tests."""
    return paths.app_config_dir()


def _dest_path() -> str:
    return os.path.join(config_dir(), DEST_NAME)


def load() -> list:
    """Load destinations list, or ``[]`` when absent or malformed. Never raises."""
    try:
        with open(_dest_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    raw = data.get("destinations") if isinstance(data, dict) else None
    return raw if isinstance(raw, list) else []


def write(destinations: list) -> None:
    """Atomically write the destinations list."""
    path = _dest_path()
    payload = {"schema": SCHEMA, "destinations": destinations}
    tmp = paths.write_temp_json(path, payload)
    paths.atomic_finalize(tmp, path)


def add(dest: dict) -> list:
    """Append a destination, write, and return the new list."""
    current = load()
    current.append(dest)
    write(current)
    return current


def remove(dest_id: str) -> list:
    """Remove the destination with ``dest_id``, write, and return the new list."""
    current = [d for d in load() if d.get("id") != dest_id]
    write(current)
    return current
