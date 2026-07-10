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

SCHEMA = 1
BRIEF_NAME = "build_brief.json"
TIERS = ("skip", "stream", "pause")
INTERFACE_KINDS = ("pivot", "slide", "snap", "thread", "press", "fixed")
# Caps so a runaway LLM cannot write a multi-MB brief the Plan panel must render.
MAX_PARTS = 64
MAX_KEY_DIMS = 256
MAX_INTERFACES = 256
# Prose caps: the brief is structured, not an essay. summary/make_real carry a
# sentence or two; per-part why/role a phrase. Rejecting (not truncating) sends
# the agent an actionable error so it moves detail into the structured fields.
MAX_SUMMARY = 500
MAX_PROSE = 500
MAX_PART_TEXT = 300
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


def validate(brief: Any) -> dict:
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
                "name": str(p["name"]).strip(),
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
            "name": str(d["name"]).strip(),
            "value": _finite_or_none(d.get("value"), "key_dim.value"),
            "unit": str(d.get("unit", "mm")).strip() or "mm",
        }
        if d.get("drives"):
            dim["drives"] = str(d["drives"]).strip()
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
                "between": [between[0].strip(), between[1].strip()],
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


def write_build_brief(root: str, brief: Any) -> dict:
    """Atomically persist a validated brief. Returns the normalized brief."""
    norm = validate(brief)
    payload = {"schema": SCHEMA, **norm}
    path = build_brief_path(root)
    # allow_nan=False so any future gap that lets a non-finite number through validate
    # fails loudly here rather than writing NaN/Infinity tokens that strict JSON readers reject.
    tmp = paths.write_temp_text(path, json.dumps(payload, indent=2, allow_nan=False))
    paths.atomic_finalize(tmp, path)
    return norm


def load_build_brief(root: str) -> dict | None:
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
    return data if isinstance(data, dict) else None
