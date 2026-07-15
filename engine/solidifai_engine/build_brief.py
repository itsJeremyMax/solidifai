"""Persisted build brief: the plan Sol commits to before building.

Sol authors the brief (parts and why, key dims, interfaces, make-it-real) and writes it
here via propose_build. self-verify reads it back to check the model against it, and the
host watches the file to render the read-only Plan panel. The engine writes it directly:
agent-authored, per-workspace, engine always up. That is a deliberate exception to the
Rust-sole-writer rule that governs manufacturing-profile.json (which the GUI must edit
globally with no engine running). Do not route this through the control channel.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

from solidifai_engine import paths

SCHEMA_V1 = 1
SCHEMA_V2 = 2
CURRENT_SCHEMA = SCHEMA_V2
# Compatibility name retained for callers that write the legacy contract.
SCHEMA = SCHEMA_V1
BRIEF_NAME = "build_brief.json"
TIERS = ("skip", "stream", "pause")
INTERFACE_KINDS = ("pivot", "slide", "snap", "thread", "press", "fixed")
# Legacy v1 product caps remain part of the historical propose_build contract.
MAX_PARTS = 64
MAX_KEY_DIMS = 256
MAX_INTERFACES = 256
# V2 bounds transport work rather than the product model. A real assembly may
# need more than any arbitrary category cap, but no request should exhaust the
# engine or Plan panel.
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
MAX_UPDATE_ITEMS = 512
MAX_NESTING_DEPTH = 16
V2_SECTIONS = (
    "parts",
    "requirements",
    "dimensions",
    "interfaces",
    "references",
    "assumptions",
    "manufacturing",
    "obligations",
)
# Prose caps: the brief is structured, not an essay. summary/make_real carry a
# sentence or two; per-part why/role a phrase. Rejecting (not truncating) sends
# the agent an actionable error so it moves detail into the structured fields.
MAX_SUMMARY = 500
MAX_PROSE = 500
MAX_PART_TEXT = 300
MAX_PART_NAME = 120
MAX_DIM_NAME = 120
MAX_UNIT = 32
MAX_DIM_DRIVES = 200
# Sol reads the readable names in the skill copy ("press-fit", "snap-fit"); normalize
# those to the canonical enum so a brief is not rejected for a synonym.
_KIND_ALIASES = {
    "press-fit": "press",
    "pressfit": "press",
    "snap-fit": "snap",
    "snapfit": "snap",
    "screw": "thread",
    "threaded": "thread",
    "hinge": "pivot",
    "rotate": "pivot",
    "sliding": "slide",
}


def build_brief_path(root: str) -> str:
    return os.path.join(root, BRIEF_NAME)


def _normalize_kind(kind: Any) -> str:
    k = str(kind or "").strip().lower()
    return _KIND_ALIASES.get(k, k)


def _capped_text(value: Any, cap: int, field: str) -> str:
    """A trimmed prose field, rejected past its cap with a message that tells the
    agent where the detail belongs instead."""
    text = str(value or "").strip()
    if len(text) > cap:
        raise ValueError(
            f"{field} too long ({len(text)} chars, max {cap}): keep it to a sentence "
            "or two; detail belongs in parts, key_dims, and interfaces"
        )
    return text


def _finite_or_none(value: Any, field: str) -> float | int | None:
    """Coerce an optional numeric field: None passes through; otherwise require a
    finite int/float. Reject bool, non-numeric, NaN, and ±inf so the brief stays
    strict-JSON (serde_json / JSON.parse reject NaN/Infinity tokens)."""
    if value is None:
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number or null, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite, got {value!r}")
    return value


def validate_v1(brief: Any) -> dict:
    """Normalize and validate an incoming brief. Raises ValueError on a bad shape."""
    if not isinstance(brief, dict):
        raise ValueError("brief must be an object")
    tier = brief.get("tier")
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    summary = _capped_text(brief.get("summary", ""), MAX_SUMMARY, "summary")
    if not summary:
        raise ValueError("summary is required")
    parts = brief.get("parts") or []
    if not isinstance(parts, list) or not parts:
        raise ValueError("parts must be a non-empty list")
    if len(parts) > MAX_PARTS:
        raise ValueError(f"too many parts (max {MAX_PARTS})")
    norm_parts = []
    for p in parts:
        if not isinstance(p, dict) or not str(p.get("name", "")).strip():
            raise ValueError("each part needs a name")
        norm_parts.append(
            {
                "name": _capped_text(p["name"], MAX_PART_NAME, "part.name"),
                "role": _capped_text(p.get("role", ""), MAX_PART_TEXT, "part.role"),
                "why": _capped_text(p.get("why", ""), MAX_PART_TEXT, "part.why"),
            }
        )
    key_dims = brief.get("key_dims") or []
    if not isinstance(key_dims, list):
        raise ValueError("key_dims must be a list")
    if len(key_dims) > MAX_KEY_DIMS:
        raise ValueError(f"too many key_dims (max {MAX_KEY_DIMS})")
    norm_dims = []
    for d in key_dims:
        if not isinstance(d, dict) or not str(d.get("name", "")).strip():
            raise ValueError("each key_dim needs a name")
        dim = {
            "name": _capped_text(d["name"], MAX_DIM_NAME, "key_dim.name"),
            "value": _finite_or_none(d.get("value"), "key_dim.value"),
            "unit": _capped_text(d.get("unit", "mm"), MAX_UNIT, "key_dim.unit") or "mm",
        }
        if d.get("drives"):
            dim["drives"] = _capped_text(d["drives"], MAX_DIM_DRIVES, "key_dim.drives")
        norm_dims.append(dim)
    interfaces = brief.get("interfaces") or []
    if not isinstance(interfaces, list):
        raise ValueError("interfaces must be a list")
    if len(interfaces) > MAX_INTERFACES:
        raise ValueError(f"too many interfaces (max {MAX_INTERFACES})")
    norm_ifaces = []
    for it in interfaces:
        if not isinstance(it, dict):
            raise ValueError("each interface must be an object")
        kind = _normalize_kind(it.get("kind"))
        if kind not in INTERFACE_KINDS:
            raise ValueError(
                f"interface kind must be one of {INTERFACE_KINDS}, got {it.get('kind')!r}"
            )
        between = it.get("between") or []
        if not isinstance(between, list) or len(between) != 2:
            raise ValueError("interface.between must be [a, b]")
        if not all(isinstance(m, str) and m.strip() for m in between):
            raise ValueError("interface.between members must be non-empty part names")
        norm_ifaces.append(
            {
                "between": [
                    _capped_text(between[0], MAX_PART_NAME, "interface.between"),
                    _capped_text(between[1], MAX_PART_NAME, "interface.between"),
                ],
                "kind": kind,
                "clearance": _finite_or_none(it.get("clearance"), "interface.clearance"),
            }
        )
    return {
        "summary": summary,
        "parts": norm_parts,
        "key_dims": norm_dims,
        "interfaces": norm_ifaces,
        "make_real": _capped_text(brief.get("make_real", ""), MAX_PROSE, "make_real"),
        "tier": tier,
    }


# Public legacy spelling: v1 callers retain their exact validator and payload.
validate = validate_v1


def _safe_json(value: Any) -> None:
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"brief must be strict JSON: {exc}") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} byte transport limit")


def _check_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise ValueError(f"brief exceeds nesting depth limit ({MAX_NESTING_DEPTH})")
    if isinstance(value, dict):
        for nested in value.values():
            _check_depth(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _check_depth(nested, depth + 1)


def _id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _required_expected_revision(expected_revision: Any) -> int:
    if expected_revision is None:
        raise ValueError("expectedRevision is required for schema-v2 mutations")
    if (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
    ):
        raise ValueError("expectedRevision must be a non-negative integer")
    return expected_revision


def validate_v2(brief: Any) -> dict:
    """Validate the extensible, stable-ID build brief contract without product caps."""
    if not isinstance(brief, dict):
        raise ValueError("brief must be an object")
    _safe_json(brief)
    _check_depth(brief)
    if brief.get("schema") != SCHEMA_V2:
        raise ValueError("v2 brief schema must be 2")
    revision = brief.get("revision", 0)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise ValueError("revision must be a non-negative integer")
    tier = brief.get("tier")
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}, got {tier!r}")
    summary = _capped_text(brief.get("summary", ""), MAX_SUMMARY, "summary")
    if not summary:
        raise ValueError("summary is required")

    normalized: dict[str, Any] = {
        "schema": SCHEMA_V2,
        "revision": revision,
        "summary": summary,
        "tier": tier,
    }
    all_ids: set[str] = set()
    for section in V2_SECTIONS:
        entries = brief.get(section, [])
        if not isinstance(entries, list):
            raise ValueError(f"{section} must be a list")
        records: list[dict] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"each {section} entry must be an object")
            record = dict(entry)  # Keep additive fields for future contract revisions.
            entry_id = _id(record.get("id"), f"{section}.id")
            if entry_id in all_ids:
                raise ValueError(f"duplicate id {entry_id!r}")
            all_ids.add(entry_id)
            record["id"] = entry_id
            records.append(record)
        normalized[section] = records

    parts = {part["id"]: part for part in normalized["parts"]}
    for part in parts.values():
        if not isinstance(part.get("name"), str) or not part["name"].strip():
            raise ValueError("each part needs a name")
        children = part.get("children", [])
        if not isinstance(children, list) or not all(isinstance(child, str) for child in children):
            raise ValueError("part.children must be a list of part ids")
        if len(set(children)) != len(children):
            raise ValueError("part.children contains duplicate ids")
        for child in children:
            if child not in parts or child == part["id"]:
                raise ValueError(f"part.children references unknown part {child!r}")
        part["children"] = children
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(part_id: str) -> None:
        if part_id in visiting:
            raise ValueError(f"part.children contains a hierarchy cycle at {part_id!r}")
        if part_id in visited:
            return
        visiting.add(part_id)
        for child in parts[part_id]["children"]:
            visit(child)
        visiting.remove(part_id)
        visited.add(part_id)

    for part_id in parts:
        visit(part_id)
    for interface in normalized["interfaces"]:
        if not isinstance(interface.get("kind"), str) or not interface["kind"].strip():
            raise ValueError("interface.kind must be a non-empty string")
        participants = interface.get("participants")
        if not isinstance(participants, list):
            raise ValueError("interface.participants must be a list of part ids")
        if not all(
            isinstance(participant, str) and participant in parts for participant in participants
        ):
            raise ValueError("interface.participants references unknown part")
        unresolved = interface.get("unresolved_participants", [])
        if not isinstance(unresolved, list) or not all(
            isinstance(participant, str) and participant.strip() for participant in unresolved
        ):
            raise ValueError("interface.unresolved_participants must be a list of names")
        if len(participants) < 2 and not (interface.get("conformance") == "unknown" and unresolved):
            raise ValueError("interface.participants must name at least two parts")
    for assumption in normalized["assumptions"]:
        if assumption.get("risk") == "high" and not str(assumption.get("disposition", "")).strip():
            raise ValueError("high-risk assumption requires a disposition")
    return normalized


def _stable_id(value: Any, used: set[str], fallback: str) -> str:
    base = (
        "".join(char.lower() if char.isalnum() else "-" for char in str(value or fallback)).strip(
            "-"
        )
        or fallback
    )
    candidate, suffix = base, 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def migrate_v1_to_v2(brief: Any) -> dict:
    """Pure, deterministic migration. Reading a v1 file never writes it back."""
    v1 = validate_v1({key: value for key, value in dict(brief).items() if key != "schema"})
    used: set[str] = set()
    parts = []
    names: dict[str, str] = {}
    for index, part in enumerate(v1["parts"]):
        part_id = _stable_id(part["name"], used, f"part-{index + 1}")
        names.setdefault(part["name"], part_id)
        parts.append({"id": part_id, **part, "children": []})
    dimensions = [
        {"id": _stable_id(dim["name"], used, f"dimension-{index + 1}"), **dim}
        for index, dim in enumerate(v1["key_dims"])
    ]
    interfaces = []
    for index, interface in enumerate(v1["interfaces"]):
        original_participants = interface["between"]
        unresolved = [name for name in original_participants if name not in names]
        migrated_interface = {
            "id": _stable_id(f"interface-{index + 1}", used, f"interface-{index + 1}"),
            "kind": interface["kind"],
            "participants": [names[name] for name in original_participants if name in names],
            "clearance": interface["clearance"],
        }
        if unresolved:
            # `unresolved_participants` preserves v1 names that cannot truthfully
            # become part IDs; `conformance: unknown` keeps the fit addressable.
            migrated_interface["unresolved_participants"] = unresolved
            migrated_interface["conformance"] = "unknown"
        interfaces.append(migrated_interface)
    manufacturing = []
    if v1["make_real"]:
        manufacturing.append(
            {
                "id": _stable_id("manufacturing", used, "manufacturing"),
                "description": v1["make_real"],
            }
        )
    return validate_v2(
        {
            "schema": SCHEMA_V2,
            "revision": 0,
            "summary": v1["summary"],
            "tier": v1["tier"],
            "parts": parts,
            "requirements": [],
            "dimensions": dimensions,
            "interfaces": interfaces,
            "references": [],
            "assumptions": [],
            "manufacturing": manufacturing,
            "obligations": [],
        }
    )


def validate_update(section: str, upserts: Any, remove_ids: Any) -> tuple[list[dict], list[str]]:
    if section not in V2_SECTIONS:
        raise ValueError(f"section must be one of {V2_SECTIONS}")
    if not isinstance(upserts, list) or not all(isinstance(item, dict) for item in upserts):
        raise ValueError("upserts must be a list of objects")
    if not isinstance(remove_ids, list) or not all(
        isinstance(item, str) and item for item in remove_ids
    ):
        raise ValueError("remove_ids must be a list of ids")
    if len(upserts) + len(remove_ids) > MAX_UPDATE_ITEMS:
        raise ValueError(f"too many update items (max {MAX_UPDATE_ITEMS})")
    return upserts, remove_ids


def write_build_brief(root: str, brief: Any, *, expected_revision: int | None = None) -> dict:
    """Atomically persist a validated brief. Returns the normalized brief."""
    schema = brief.get("schema", SCHEMA_V1) if isinstance(brief, dict) else SCHEMA_V1
    if schema == SCHEMA_V1:
        norm = validate_v1(brief)
        payload = {"schema": SCHEMA_V1, **norm}
    elif schema == SCHEMA_V2:
        expected = _required_expected_revision(expected_revision)
        current = load_build_brief(root, target_schema=SCHEMA_V2)
        current_revision = current["revision"] if current is not None else 0
        if expected != current_revision:
            raise ValueError(f"revision conflict: expected {expected}, current {current_revision}")
        payload = validate_v2({**brief, "revision": current_revision + 1})
        norm = payload
    else:
        raise ValueError(f"unsupported build brief schema {schema!r}")
    path = build_brief_path(root)
    # allow_nan=False so any future gap that lets a non-finite number through validate
    # fails loudly here rather than writing NaN/Infinity tokens that strict JSON readers reject.
    tmp = paths.write_temp_text(path, json.dumps(payload, indent=2, allow_nan=False))
    paths.atomic_finalize(tmp, path)
    return norm


def load_build_brief(root: str, target_schema: int | None = None) -> dict | None:
    """Read the persisted brief, or None when absent, unreadable, corrupt, or not an
    object. Never raises (mirrors requirements.load_requirements)."""
    path = build_brief_path(root)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if target_schema is None:
        return data
    schema = data.get("schema", SCHEMA_V1)
    if target_schema == schema:
        return data
    if target_schema == SCHEMA_V2 and schema == SCHEMA_V1:
        try:
            return migrate_v1_to_v2(data)
        except ValueError:
            return None
    return None


def update_build_brief(
    root: str,
    section: str,
    upserts: list[dict],
    remove_ids: list[str] | None = None,
    *,
    expected_revision: int | None = None,
) -> dict:
    """Apply one v2 section patch atomically, migrating v1 only on mutation."""
    expected = _required_expected_revision(expected_revision)
    upserts, remove_ids = validate_update(section, upserts, remove_ids or [])
    current = load_build_brief(root, target_schema=SCHEMA_V2)
    if current is None:
        raise ValueError("no build brief to update")
    revision = current["revision"]
    if expected != revision:
        raise ValueError(f"revision conflict: expected {expected}, current {revision}")
    records = {record["id"]: record for record in current[section]}
    for record_id in remove_ids:
        records.pop(record_id, None)
    for record in upserts:
        record_id = _id(record.get("id"), f"{section}.id")
        records[record_id] = dict(record)
    updated = dict(current)
    updated[section] = list(records.values())
    updated["revision"] = revision + 1
    payload = validate_v2(updated)
    path = build_brief_path(root)
    tmp = paths.write_temp_text(path, json.dumps(payload, indent=2, allow_nan=False))
    paths.atomic_finalize(tmp, path)
    return payload
