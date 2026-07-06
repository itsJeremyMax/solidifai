"""Per-workspace part_materials.json: per-part material overrides, applied at
render time over what model.py set. Kept separate from model.py (like
settings.py for params) so a UI assignment writes a tiny JSON diff instead of
rewriting source. Keyed by the part's stable id (the slugified object name that
render.py writes into model.json)."""

from __future__ import annotations

import json
import os

from solidifai_engine import paths

OVERRIDES_NAME = "part_materials.json"
SCHEMA = 1


def overrides_path(root: str) -> str:
    return os.path.join(root, OVERRIDES_NAME)


def load_overrides(root: str) -> dict:
    """Saved ``{partId: materialId}`` map, or ``{}`` when absent or malformed.
    Never raises. Non-string values are dropped."""
    try:
        with open(overrides_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    raw = data.get("overrides") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}


def write_overrides(root: str, overrides: dict) -> None:
    """Atomically write the override map to part_materials.json (temp + replace)."""
    path = overrides_path(root)
    payload = {"schema": SCHEMA, "overrides": overrides}
    tmp = paths.write_temp_text(path, json.dumps(payload, indent=2))
    paths.atomic_finalize(tmp, path)
