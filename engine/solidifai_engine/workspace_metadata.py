"""Per-workspace workspace.json: the workspace's own record of itself (name,
description, tags) plus a staged name proposal. Canonical source of truth; the
Rust registry only caches it. Written by the engine when Sol acts; by Rust when
the user acts on a closed workspace. Mirrors part_materials.py for load/write.

On-disk keys are camelCase so Python, Rust (serde), and TS read one format."""

from __future__ import annotations

import json
import os

from solidifai_engine import paths

META_NAME = "workspace.json"
SCHEMA = 1
MAX_TAGS = 12
MAX_TAG_LEN = 24
MAX_DESC_LEN = 280


def meta_path(root: str) -> str:
    return os.path.join(root, META_NAME)


def defaults() -> dict:
    return {
        "schema": SCHEMA,
        "name": "",
        "createdAt": 0,
        "description": "",
        "descriptionSource": "sol",
        "tags": [],
        "tagsSource": "sol",
        "proposedName": None,
        "proposedNameDismissed": None,
    }


def _coerce(data: dict) -> dict:
    """Layer a loaded dict over defaults, coercing types defensively."""
    m = defaults()
    if not isinstance(data, dict):
        return m
    if isinstance(data.get("name"), str):
        m["name"] = data["name"]
    if isinstance(data.get("createdAt"), (int, float)):
        m["createdAt"] = int(data["createdAt"])
    if isinstance(data.get("description"), str):
        m["description"] = data["description"]
    if data.get("descriptionSource") in ("sol", "user"):
        m["descriptionSource"] = data["descriptionSource"]
    if isinstance(data.get("tags"), list):
        m["tags"] = [t for t in data["tags"] if isinstance(t, str)]
    if data.get("tagsSource") in ("sol", "user"):
        m["tagsSource"] = data["tagsSource"]
    if isinstance(data.get("proposedName"), str):
        m["proposedName"] = data["proposedName"]
    if isinstance(data.get("proposedNameDismissed"), str):
        m["proposedNameDismissed"] = data["proposedNameDismissed"]
    return m


def load_metadata(root: str) -> dict:
    """Saved metadata layered over defaults, or defaults when absent/malformed.
    Never raises."""
    try:
        with open(meta_path(root), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return defaults()
    return _coerce(data)


def write_metadata(root: str, metadata: dict) -> None:
    """Atomically write workspace.json (temp + replace), schema-tagged."""
    payload = _coerce(metadata)
    payload["schema"] = SCHEMA
    tmp = paths.write_temp_text(meta_path(root), json.dumps(payload, indent=2))
    paths.atomic_finalize(tmp, meta_path(root))


def normalize_tags(tags) -> list:
    seen: list[str] = []
    for t in tags or []:
        s = str(t).strip().lower()[:MAX_TAG_LEN]
        if s and s not in seen:
            seen.append(s)
        if len(seen) >= MAX_TAGS:
            break
    return seen


def normalize_description(desc) -> str:
    return str(desc or "").strip()[:MAX_DESC_LEN]


def _resolve_proposed(cur: dict, proposed) -> str | None:
    if proposed is None:
        return None
    s = str(proposed).strip()
    if not s:
        return None
    name = (cur.get("name") or "").strip().lower()
    dismissed = (cur.get("proposedNameDismissed") or "").strip().lower()
    if s.lower() == name or s.lower() == dismissed:
        return None
    return s


def apply_patch(cur: dict, patch: dict, *, force: bool) -> dict:
    """Apply a Sol-authored partial update. Proactive (force=False) writes a
    field only if it is empty or already sol-owned; force=True overrides and
    reclaims the field for sol. proposedName has no provenance and is guarded
    against name/dismissed collisions."""
    out = _coerce(cur)
    if "description" in patch and (force or out["descriptionSource"] in ("", "sol")):
        out["description"] = normalize_description(patch["description"])
        out["descriptionSource"] = "sol"
    if "tags" in patch and (force or out["tagsSource"] in ("", "sol")):
        out["tags"] = normalize_tags(patch["tags"])
        out["tagsSource"] = "sol"
    if "proposedName" in patch:
        out["proposedName"] = _resolve_proposed(out, patch["proposedName"])
    return out


def apply_user_patch(cur: dict, patch: dict) -> dict:
    """Apply a user UI edit: write the fields and mark them user-owned."""
    out = _coerce(cur)
    if "description" in patch:
        out["description"] = normalize_description(patch["description"])
        out["descriptionSource"] = "user"
    if "tags" in patch:
        out["tags"] = normalize_tags(patch["tags"])
        out["tagsSource"] = "user"
    return out


def set_name(cur: dict, name: str) -> dict:
    """Set the canonical name (user-initiated rename / accept). Clears any
    pending proposal. Rejects empty."""
    s = str(name).strip()
    if not s:
        raise ValueError("workspace name cannot be empty")
    out = _coerce(cur)
    out["name"] = s
    out["proposedName"] = None
    return out


def dismiss_proposed_name(cur: dict) -> dict:
    """Move the staged proposal into proposedNameDismissed and clear it."""
    out = _coerce(cur)
    if out["proposedName"]:
        out["proposedNameDismissed"] = out["proposedName"]
    out["proposedName"] = None
    return out
