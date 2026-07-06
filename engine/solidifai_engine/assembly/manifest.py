"""Read/write/validate assembly.json (the per-node tree wiring). Pure data: it
never executes skeleton or part code."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from solidifai_engine import paths

MANIFEST_NAME = "assembly.json"
_KINDS = ("part", "assembly")
# A child id maps onto the filesystem (parts/<id>.py, <id>/), so it must be a
# single safe path segment. This mirrors Session._CHILD_ID_RE.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class ChildEntry:
    id: str
    kind: str  # "part" | "assembly"
    source: str  # "parts/<id>.py" for a part, "<id>/" for a sub-assembly
    attach: str | None = None  # name of a skeleton frame; None = node origin
    inputs: list[str] = field(default_factory=list)  # skeleton scalars this node may read
    shape_inputs: list[str] = field(default_factory=list)  # skeleton shapes this node may read


@dataclass
class Manifest:
    skeleton: str | None  # "skeleton.py" or None (degenerate / no shared truth)
    children: list[ChildEntry]
    version: int = 2


def manifest_path(node_dir: str) -> str:
    return os.path.join(node_dir, MANIFEST_NAME)


def load_manifest(node_dir: str) -> Manifest:
    path = manifest_path(node_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(f"no assembly manifest at {path!r}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    root_real = os.path.realpath(node_dir)
    children: list[ChildEntry] = []
    for raw in data.get("children", []):
        child_id = raw.get("id")
        kind = raw.get("kind")
        if kind not in _KINDS:
            raise ValueError(f"child {child_id!r}: bad kind {kind!r}; expected one of {_KINDS}")
        # Containment + id validation at the single chokepoint every consumer
        # (graph build/flatten/tree, parallel, history restore, diff) passes
        # through, so a hand-edited manifest fails loudly everywhere rather than
        # letting graph.build_node read/exec code outside the workspace.
        if not isinstance(child_id, str) or not _ID_RE.match(child_id):
            raise ValueError(
                f"child {child_id!r}: invalid id; use letters, digits, hyphen, underscore"
            )
        source = raw["source"]
        source_real = os.path.realpath(os.path.join(node_dir, source))
        if os.path.commonpath([root_real, source_real]) != root_real:
            raise ValueError(f"child {child_id!r}: source {source!r} escapes the node directory")
        children.append(
            ChildEntry(
                id=child_id,
                kind=kind,
                source=source,
                attach=raw.get("attach"),
                inputs=list(raw.get("inputs") or []),
                shape_inputs=list(raw.get("shape_inputs") or []),
            )
        )
    return Manifest(
        skeleton=data.get("skeleton"),
        children=children,
        version=int(data.get("version", 1)),
    )


def child_by_id(man: Manifest, child_id: str) -> ChildEntry | None:
    return next((c for c in man.children if c.id == child_id), None)


def upsert_child(man: Manifest, entry: ChildEntry) -> None:
    """Replace the child with entry.id in place, or append if new (order stable)."""
    for i, c in enumerate(man.children):
        if c.id == entry.id:
            man.children[i] = entry
            return
    man.children.append(entry)


def remove_child(man: Manifest, child_id: str) -> bool:
    before = len(man.children)
    man.children[:] = [c for c in man.children if c.id != child_id]
    return len(man.children) != before


def write_manifest(node_dir: str, man: Manifest) -> None:
    data = {
        "version": man.version,
        "skeleton": man.skeleton,
        "children": [
            {
                "id": c.id,
                "kind": c.kind,
                "source": c.source,
                "attach": c.attach,
                "inputs": c.inputs,
                **({"shape_inputs": c.shape_inputs} if c.shape_inputs else {}),
            }
            for c in man.children
        ],
    }
    text = json.dumps(data, indent=2) + "\n"
    final = manifest_path(node_dir)
    tmp = paths.write_temp_text(final, text)
    paths.atomic_finalize(tmp, final)
