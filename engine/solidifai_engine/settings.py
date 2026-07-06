"""Per-workspace settings.json: the CURRENT parameter values, layered over the
model.py PARAMS defaults on open. Kept separate from model.py so a slider tweak
writes a tiny JSON diff instead of rewriting source."""

from __future__ import annotations

import json
import os

from solidifai_engine import paths

SETTINGS_NAME = "settings.json"
SCHEMA = 1  # on-disk format version; written but not yet validated on read


def settings_path(root: str) -> str:
    return os.path.join(root, SETTINGS_NAME)


def load_params(root: str) -> dict:
    """Saved ``{key: value}`` map, or ``{}`` when the file is absent or malformed.
    Never raises — a missing/corrupt file simply means 'use defaults'."""
    try:
        with open(settings_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    params = data.get("params")
    return dict(params) if isinstance(params, dict) else {}


def write_params(root: str, params: dict) -> None:
    """Atomically write the current values to settings.json (temp + os.replace)."""
    path = settings_path(root)
    payload = {"schema": SCHEMA, "params": params}
    tmp = paths.write_temp_text(path, json.dumps(payload, indent=2))
    paths.atomic_finalize(tmp, path)


def merge(defaults: dict, saved: dict) -> dict:
    """Layer ``saved`` over ``defaults``: keep saved values for keys that still
    exist in defaults, drop unknown keys, fall back to defaults for the rest."""
    merged = dict(defaults)
    for key, value in saved.items():
        if key in defaults:
            merged[key] = value
    return merged
