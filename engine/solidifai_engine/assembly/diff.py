"""Structural diff between two snapshots of an assembly's fileset.

Compares two ``{repo-relative path: text}`` maps (e.g. the current working tree
vs a past commit's tree) and classifies the changes into three buckets:

  - structural: children added / removed / rewired (attach, inputs, or shape_inputs changed),
    read from the two ``assembly.json`` manifests.
  - skeleton:   whether ``skeleton.py`` changed, plus the PARAMS keys
    added / removed / changed.
  - parts:      ``parts/*.py`` sources added / removed / changed (by text).

This is a pure-data classification: it never executes skeleton or part code. For
nested sub-assemblies it classifies the ROOT node's manifest and reports nested
part-source changes by path; a per-node structural breakdown for deeper nodes is
a future extension (noted, not faked).
"""

from __future__ import annotations

import ast
import json
import re


def _load_manifest_children(text: str | None) -> dict[str, dict]:
    """Parse an assembly.json blob into ``{child_id: {attach, inputs, source}}``.
    A missing/unparseable manifest yields no children (so it reads as "added all"
    against a populated side, which is the correct structural story)."""
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    out: dict[str, dict] = {}
    for raw in data.get("children", []) or []:
        cid = raw.get("id")
        if not isinstance(cid, str):
            continue
        out[cid] = {
            "attach": raw.get("attach"),
            "inputs": list(raw.get("inputs") or []),
            "shape_inputs": list(raw.get("shape_inputs") or []),
            "source": raw.get("source"),
            # Normalize occurrences to a comparable form (absent key -> None) so a
            # change in placement count/frames/mirrors reads as a rewiring.
            "occurrences": _norm_occurrences(raw.get("occurrences")),
        }
    return out


def _norm_occurrences(raw) -> list | None:
    if not isinstance(raw, list):
        return None
    return [
        {"frame": o.get("frame"), "mirror": o.get("mirror")} for o in raw if isinstance(o, dict)
    ]


def _wiring_changed(a: dict, b: dict) -> bool:
    return (
        a.get("attach") != b.get("attach")
        or a.get("inputs") != b.get("inputs")
        or a.get("shape_inputs") != b.get("shape_inputs")
        or a.get("occurrences") != b.get("occurrences")
    )


def _skeleton_params(text: str | None) -> dict:
    """Best-effort PARAMS dict from skeleton source, read statically (no exec) by
    literal-eval of the top-level ``PARAMS = {...}`` assignment. Returns {} when it
    is absent or not a literal; the caller still reports source-level changes."""
    if not text:
        return {}
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "PARAMS":
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    return {}
                return value if isinstance(value, dict) else {}
    return {}


def _diff_skeleton(old: str | None, new: str | None) -> dict:
    old_p, new_p = _skeleton_params(old), _skeleton_params(new)
    added = sorted(set(new_p) - set(old_p))
    removed = sorted(set(old_p) - set(new_p))
    changed = sorted(k for k in set(old_p) & set(new_p) if old_p[k] != new_p[k])
    return {
        "changed": (old or "") != (new or ""),
        "params_added": added,
        "params_removed": removed,
        "params_changed": changed,
    }


_PART_RE = re.compile(r"(?:^|/)parts/([^/]+)\.py$")


def _part_sources(files: dict[str, str]) -> dict[str, str]:
    """Map ``part id -> source text`` for every parts/<id>.py in a snapshot. The id
    is the file stem; a nested sub-assembly's parts keep their full path as the key
    so they do not collide with a root part of the same stem."""
    out: dict[str, str] = {}
    for path, text in files.items():
        m = _PART_RE.search(path)
        if not m:
            continue
        # Root parts key on the bare id (matches the manifest child id); nested
        # parts key on the full path so two "pin.py" in different nodes are distinct.
        key = m.group(1) if path == f"parts/{m.group(1)}.py" else path
        out[key] = text
    return out


def structural_diff(root: str, old_files: dict[str, str], new_files: dict[str, str]) -> dict:
    """Classify the change between two assembly fileset snapshots.

    ``old_files``/``new_files`` are ``{repo-relative path: text}`` maps. ``root`` is
    unused for the comparison itself (the snapshots carry everything) but kept in the
    signature so callers can pass the workspace root for future per-node recursion.
    Returns ``{structural, skeleton, parts}``; never raises on malformed input."""
    old_children = _load_manifest_children(old_files.get("assembly.json"))
    new_children = _load_manifest_children(new_files.get("assembly.json"))

    added = sorted(set(new_children) - set(old_children))
    removed = sorted(set(old_children) - set(new_children))
    rewired = sorted(
        cid
        for cid in set(old_children) & set(new_children)
        if _wiring_changed(old_children[cid], new_children[cid])
    )

    skeleton = _diff_skeleton(old_files.get("skeleton.py"), new_files.get("skeleton.py"))

    old_parts = _part_sources(old_files)
    new_parts = _part_sources(new_files)
    parts = {
        "added": sorted(set(new_parts) - set(old_parts)),
        "removed": sorted(set(old_parts) - set(new_parts)),
        "changed": sorted(
            pid for pid in set(old_parts) & set(new_parts) if old_parts[pid] != new_parts[pid]
        ),
    }

    return {
        "structural": {"added": added, "removed": removed, "rewired": rewired},
        "skeleton": skeleton,
        "parts": parts,
    }
