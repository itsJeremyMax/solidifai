"""Render the current registry to GLB + model.json artifacts.

The registry (populated by ``solidifai.show``) is combined into a single
``Compound`` which is tessellated to a binary glTF. Properties are computed on
the same compound and merged into ``model.json``. Both files are written
atomically (temp + ``os.replace``) so a watching renderer never reads a partial
artifact.
"""

from __future__ import annotations

import contextlib
import os
import re
from datetime import UTC, datetime
from typing import Any

from build123d import Compound, Unit, export_gltf

from solidifai import _registry
from solidifai_engine import materials as _materials
from solidifai_engine import paths
from solidifai_engine.props import mass_grams, properties

UNITS = "mm"


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "object"


def _kind(shape: Any) -> str:
    return type(shape).__name__


def _node_ids(objects) -> list[str]:
    """Collision-safe ids aligned with ``objects`` (matches model.json ids).
    Each '/'-separated path segment is slugged independently so assembly path
    ids like 'hinge/pin/pin' keep their separators while flat names are
    unchanged."""
    seen: dict[str, int] = {}
    ids: list[str] = []
    for obj in objects:
        node = "/".join(_slug(s) for s in obj.name.split("/"))
        if node in seen:
            seen[node] += 1
            node = f"{node}_{seen[node]}"
        else:
            seen[node] = 0
        ids.append(node)
    return ids


def _compound_from_registry(objects) -> Compound:
    shapes = [o.shape for o in objects]
    return Compound(children=shapes)


def render_to(
    artifacts_dir: str,
    build_id: int,
    *,
    params: dict | None = None,
    duration_ms: int = 0,
    warnings: list | None = None,
    overrides: dict | None = None,
    objects: list | None = None,  # explicit object list (composed assembly)
    node_ids: list | None = None,  # explicit ids aligned with objects
) -> dict:
    """Render the current registry into ``artifacts_dir``.

    Returns a small status dict ``{"ok": True, "buildId": build_id}``. Raises if
    the registry is empty or tessellation fails; callers handle that as a failed
    build (which must not bump buildId or overwrite last-good artifacts).

    Pass ``objects`` + ``node_ids`` to render a pre-built composed assembly
    without touching the registry. When omitted the existing single-model
    registry path is used unchanged.
    """
    objects = list(objects) if objects is not None else list(_registry())
    if not objects:
        raise ValueError("nothing to render: registry is empty (did you call show()?)")

    overrides = overrides or {}
    # Compute the collision-safe ids ONCE, up front: they key the per-part
    # overrides during resolution below AND become the ids/nodes in model.json,
    # so both must agree. An unknown override id simply has no matching object.
    node_ids = list(node_ids) if node_ids is not None else _node_ids(objects)

    compound = _compound_from_registry(objects)

    glb_final = paths.glb_path(artifacts_dir)
    json_final = paths.json_path(artifacts_dir)
    glb_tmp = glb_final + ".tmp"
    json_tmp = json_final + ".tmp"

    try:
        # Resolve all materials FIRST (validate-all-before-work, like views.py):
        # an unknown material raises here, before any tessellation, so a failed
        # build never writes temps or bumps buildId. A per-part override wins
        # over what model.py set; an unknown override id has no matching node and
        # is ignored.
        # A per-part override REPLACES the material entirely, so its own color
        # wins (resolve with color=None). Only the author's show(color=) tints a
        # part that has no override.
        resolved = []
        for o, node in zip(objects, node_ids, strict=True):
            override = overrides.get(node)
            if override is not None:
                resolved.append(_materials.RESOLVER.resolve(override, color=None))
            else:
                resolved.append(_materials.RESOLVER.resolve(o.material, color=o.color))

        export_gltf(
            compound,
            glb_tmp,
            binary=True,
            unit=Unit.MM,
            linear_deflection=1e-3,
            angular_deflection=0.1,
        )

        # The model summary (bbox/volume/manifold) reflects your DESIGN, so it is
        # computed from part-role objects only -- a reference is an open surface
        # (an STL Face) that would otherwise flip manifold and stretch the bbox.
        part_objects = [o for o in objects if getattr(o, "role", "part") != "reference"]
        props = properties(_compound_from_registry(part_objects) if part_objects else compound)

        json_objects = []
        total_mass = 0.0
        labels: set[str] = set()
        for obj, mat, node in zip(objects, resolved, node_ids, strict=True):
            role = getattr(obj, "role", "part")
            appearance = dict(_materials.RESOLVER.appearance(mat))
            # References render ghosted; parts opaque.
            appearance["opacity"] = 0.35 if role == "reference" else 1.0
            if role == "reference":
                # A reference is someone else's part: no mass, excluded from the total.
                mass_entry = None
            else:
                obj_mass = mass_grams(float(obj.shape.volume), mat.density)
                total_mass += obj_mass
                labels.add(mat.label)
                mass_entry = {"value": obj_mass, "material": mat.label, "density": mat.density}
            json_objects.append(
                {
                    "id": node,
                    "name": obj.name,
                    "kind": _kind(obj.shape),
                    "node": node,
                    "visible": True,
                    "role": role,
                    "appearance": appearance,
                    "mass": mass_entry,
                }
            )

        # Build-level mass: sum of per-object masses. When every object shares one
        # material, name it; otherwise "mixed" (density 0) — the frontend Inspector
        # shows this label and the value.
        if len(labels) == 1:
            build_label, build_density = resolved[0].label, resolved[0].density
        else:
            build_label, build_density = "mixed", 0

        model = {
            "schema": 2,
            "buildId": build_id,
            "generatedAt": datetime.now(UTC).isoformat(),
            "units": UNITS,
            "build": {
                "ok": True,
                "durationMs": int(duration_ms),
                "warnings": list(warnings or []),
            },
            "objects": json_objects,
            "bbox": props["bbox"],
            "volume": props["volume"],
            "centerOfMass": props["centerOfMass"],
            "mass": {
                "value": round(total_mass, 4),
                "material": build_label,
                "density": build_density,
            },
            "valid": props["valid"],
            "manifold": props["manifold"],
            "params": params if params is not None else {"schema": {}, "values": {}},
        }

        paths.write_temp_json(json_final, model)
    except BaseException:
        _cleanup(glb_tmp, json_tmp)
        raise

    # Commit phase: both temps are complete, so replace the live files. Order is
    # intentional -- GLB first, then JSON. The Rust watcher triggers on
    # model.json changes, so finalizing the GLB before the JSON guarantees that
    # when the new JSON (and its buildId) becomes visible, the matching GLB is
    # already in place. On the rare chance the second replace fails, clean up the
    # orphan json temp.
    paths.atomic_finalize(glb_tmp, glb_final)
    try:
        paths.atomic_finalize(json_tmp, json_final)
    except BaseException:
        _cleanup(json_tmp)
        raise

    return {"ok": True, "buildId": build_id}


def _cleanup(*temp_paths: str) -> None:
    for tmp in temp_paths:
        with contextlib.suppress(OSError):
            os.remove(tmp)
