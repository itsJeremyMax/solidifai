"""Read/write/validate assembly.json (the per-node tree wiring). Pure data: it
never executes skeleton or part code.

Occurrences (instancing). A child is ONE part definition placed at N frames. By
default a child has no ``occurrences`` key and is placed once at ``attach`` --
byte-identical to every pre-instancing manifest. When ``occurrences`` is present
it is a list of ``{"frame": <skeleton frame name | null>, "mirror": <null | "xy"
| "yz" | "zx">}`` entries and SUPERSEDES the single ``attach`` placement: the
part is built once (the content-only cache key dedupes N uses to one build) and
placed at each occurrence's frame, mirrored about the named local plane first for
a mirrored occurrence. ``attach`` is kept in sync with ``occurrences[0]["frame"]``
so the primary instance's frame stays readable by every consumer (diff, tree,
get_part_info) and ``attach(id, frame)`` re-points occurrences[0]. Use
``effective_occurrences`` everywhere placement happens so the absent-key single
case and the explicit-list case flow through one code path."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from solidifai_engine import paths

MANIFEST_NAME = "assembly.json"
_KINDS = ("part", "assembly")
# The build123d planes a mirrored occurrence may reflect about, in the part's
# local frame. "zx" is accepted as an alias for the XZ plane.
_MIRROR_PLANES = (None, "xy", "yz", "zx")
# A child id maps onto the filesystem (parts/<id>.py, <id>/), so it must be a
# single safe path segment. This mirrors Session._CHILD_ID_RE.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class Occurrence:
    """One placement of a part definition: a skeleton frame plus an optional
    local-plane mirror. ``frame=None`` places at the node origin; ``mirror=None``
    is an unmirrored (right-handed) copy."""

    frame: str | None = None
    mirror: str | None = None  # None | "xy" | "yz" | "zx"


@dataclass
class ChildEntry:
    id: str
    kind: str  # "part" | "assembly"
    source: str  # "parts/<id>.py" for a part, "<id>/" for a sub-assembly
    attach: str | None = None  # name of a skeleton frame; None = node origin
    inputs: list[str] = field(default_factory=list)  # skeleton scalars this node may read
    shape_inputs: list[str] = field(default_factory=list)  # skeleton shapes this node may read
    # None = single placement at `attach` (legacy/default). A non-None list places
    # the one part definition at each occurrence; occurrences[0].frame mirrors attach.
    occurrences: list[Occurrence] | None = None


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
        occurrences = _parse_occurrences(child_id, raw.get("occurrences"))
        children.append(
            ChildEntry(
                id=child_id,
                kind=kind,
                source=source,
                attach=raw.get("attach"),
                inputs=list(raw.get("inputs") or []),
                shape_inputs=list(raw.get("shape_inputs") or []),
                occurrences=occurrences,
            )
        )
    return Manifest(
        skeleton=data.get("skeleton"),
        children=children,
        version=int(data.get("version", 1)),
    )


def _parse_occurrences(child_id, raw) -> list[Occurrence] | None:
    """Validate + build the occurrence list for a child, or None when the key is
    absent (the single-placement-at-attach default). Validated at the same load
    chokepoint every consumer passes through, so a hand-edited bad mirror/frame
    fails loudly rather than deep inside compose."""
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"child {child_id!r}: occurrences must be a non-empty list")
    out: list[Occurrence] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"child {child_id!r}: occurrence {i} must be an object")
        frame = entry.get("frame")
        if frame is not None and not isinstance(frame, str):
            raise ValueError(f"child {child_id!r}: occurrence {i} frame must be a string or null")
        mirror = entry.get("mirror")
        if mirror not in _MIRROR_PLANES:
            raise ValueError(
                f"child {child_id!r}: occurrence {i} mirror {mirror!r} must be one of "
                f"null, 'xy', 'yz', 'zx'"
            )
        out.append(Occurrence(frame=frame, mirror=mirror))
    return out


def effective_occurrences(child: ChildEntry) -> list[Occurrence]:
    """The placements for a child, single code path for absent-key and explicit
    forms: the explicit ``occurrences`` list when set, else exactly one occurrence
    at ``attach`` (unmirrored). Every placer (compose, flatten, interfaces) reads
    this so a legacy single-occurrence child behaves identically."""
    if child.occurrences:
        return child.occurrences
    return [Occurrence(frame=child.attach, mirror=None)]


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
                # Emit occurrences only when explicitly set, so a legacy single-
                # placement child round-trips byte-for-byte (no new key).
                **(
                    {"occurrences": [{"frame": o.frame, "mirror": o.mirror} for o in c.occurrences]}
                    if c.occurrences is not None
                    else {}
                ),
            }
            for c in man.children
        ],
    }
    text = json.dumps(data, indent=2) + "\n"
    final = manifest_path(node_dir)
    tmp = paths.write_temp_text(final, text)
    paths.atomic_finalize(tmp, final)
