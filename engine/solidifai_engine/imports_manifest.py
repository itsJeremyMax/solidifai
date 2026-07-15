"""Read/write the workspace imports manifest (``imports.json``).

The manifest is the declarative store of imported *reference* fixtures (parts you
fit around, not modify). Each entry: ``{id, name, path, format}`` where ``path``
is workspace-relative (``assets/<file>``). Entries are always reference role;
designed parts live in ``model.py``. Reads never raise -- a missing or corrupt
file yields an empty list -- so a bad manifest degrades to "no references"
instead of breaking the build.
"""

from __future__ import annotations

import json
import re

from solidifai_engine import paths

SCHEMA = 1


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "import"


def load(root: str) -> list[dict]:
    """Return the manifest entries (``[]`` when missing or unreadable)."""
    try:
        with open(paths.imports_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    items = data.get("imports", [])
    return [e for e in items if isinstance(e, dict) and e.get("id") and e.get("path")]


def _write(root: str, entries: list[dict]) -> None:
    tmp = paths.write_temp_json(paths.imports_path(root), {"schema": SCHEMA, "imports": entries})
    paths.atomic_finalize(tmp, paths.imports_path(root))


def add(root: str, entry: dict) -> dict:
    """Append ``entry`` (a collision-safe ``id`` is assigned from its name/id).

    The v1 ``id``/``name``/``path``/``format`` records remain valid. New callers
    may additionally persist ``required`` and a small source ``provenance`` map.
    """
    if "required" in entry and not isinstance(entry["required"], bool):
        raise ValueError("import.required must be a boolean")
    provenance = entry.get("provenance")
    if provenance is not None and (
        not isinstance(provenance, dict)
        or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in provenance.items()
        )
    ):
        raise ValueError("import.provenance must be a string-to-string object")
    entries = load(root)
    used = {e["id"] for e in entries}
    base = _slug(entry.get("id") or entry.get("name") or "import")
    eid, n = base, 1
    while eid in used:
        eid = f"{base}-{n}"
        n += 1
    saved = {**entry, "id": eid}
    entries.append(saved)
    _write(root, entries)
    return saved


def remove(root: str, import_id: str) -> bool:
    """Drop the entry with ``import_id``. Returns True if one was removed."""
    entries = load(root)
    kept = [e for e in entries if e["id"] != import_id]
    if len(kept) == len(entries):
        return False
    _write(root, kept)
    return True
