# engine/solidifai_engine/fabrication/presets.py
"""OrcaSlicer preset discovery + inheritance flattening.

The real Orca config layout is ``<config>/user/<account>/{machine,filament,process}``
plus ``<config>/system/<vendor>/{machine,filament,process}``. The printer category is
named ``machine``. User presets store only deltas via ``inherits`` and omit the
``type`` field, so they cannot be passed to the Orca CLI directly ("unknown config
type"). ``flatten`` walks the chain, merges child-over-parent, keeps the leaf
``from``, and injects ``type`` so the result is a self-contained config the CLI accepts.
"""

from __future__ import annotations

import json
from pathlib import Path

# Internal category keys (the printer category is named "machine" on disk).
CATEGORIES = ("machine", "filament", "process")
# How each category surfaces to callers / the UI.
_PUBLIC = {"machine": "printers", "filament": "filaments", "process": "processes"}


def build_index(config_dir: str, category: str) -> dict[str, str]:
    """Map preset name -> absolute file path for one category.

    Scans system presets first, then user presets so a user preset overrides a
    system preset of the same name (matching Orca's own precedence). Never raises.
    """
    index: dict[str, str] = {}
    base = Path(config_dir)
    for scope in ("system", "user"):
        # <config>/<scope>/<group>/<category>/*.json  (group = vendor or account)
        root = base / scope
        if not root.is_dir():
            continue
        for group in root.iterdir():
            cat_dir = group / category
            if not cat_dir.is_dir():
                continue
            for f in cat_dir.glob("*.json"):
                index[f.stem] = str(f)  # later scope (user) wins on collision
    return index


def list_profiles(config_dir: str) -> dict[str, list[str]]:
    """Return sorted preset names per public category (printers/filaments/processes)."""
    out: dict[str, list[str]] = {"printers": [], "filaments": [], "processes": []}
    for cat in CATEGORIES:
        out[_PUBLIC[cat]] = sorted(build_index(config_dir, cat).keys())
    return out


def flatten(config_dir: str, name: str, category: str) -> dict | None:
    """Resolve ``name``'s inheritance chain into one self-contained config dict.

    Returns None when the name is unknown in this category. Injects ``type`` and a
    clean ``name``; keeps the leaf preset's ``from``; drops ``inherits``.
    """
    index = build_index(config_dir, category)
    if name not in index:
        return None

    chain: list[dict] = []
    leaf_from: str | None = None
    cur: str | None = name
    seen: set[str] = set()
    while cur and cur not in seen and cur in index:
        seen.add(cur)
        try:
            data = json.loads(Path(index[cur]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            break
        chain.append(data)
        if leaf_from is None:
            leaf_from = data.get("from")
        cur = data.get("inherits")

    merged: dict = {}
    for data in reversed(chain):  # deepest ancestor first; child overrides
        for k, v in data.items():
            if k in ("inherits", "from"):
                continue
            merged[k] = v
    merged["type"] = category
    merged["name"] = name
    merged["from"] = leaf_from or "User"
    return merged


def write_flattened(config_dir: str, name: str, category: str, dest_path: str) -> bool:
    """Flatten ``name`` and write it to ``dest_path``. False when unresolved."""
    merged = flatten(config_dir, name, category)
    if merged is None:
        return False
    try:
        Path(dest_path).write_text(json.dumps(merged), encoding="utf-8")
    except OSError:
        return False
    return True
