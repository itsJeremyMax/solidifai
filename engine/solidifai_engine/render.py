"""Render the current registry to GLB + model.json artifacts.

The registry (populated by ``solidifai.show``) is combined into a single
``Compound`` which is tessellated to a binary glTF. Properties are computed on
the same compound and merged into ``model.json``. Both files are written
atomically (temp + ``os.replace``) so a watching renderer never reads a partial
artifact.
"""

from __future__ import annotations

import contextlib
import copy
import math
import os
import re
from datetime import UTC, datetime
from typing import Any

from build123d import Compound, Unit, export_gltf

from solidifai import _registry
from solidifai_engine import materials as _materials
from solidifai_engine import paths
from solidifai_engine.props import build_volume_com, mass_grams, properties

UNITS = "mm"

# Mesh resolution for the GLB export (mm). Also the yardstick for the
# meshability guard below, so the two stay in step.
_GLB_LINEAR_DEFLECTION = 1e-3
# Reject a build whose bounding-box diagonal exceeds this many mesh steps: the
# tessellation would produce a runaway triangle count and hang. A real part at
# any plausible size (even a few metres) is orders of magnitude under this; only
# pathological geometry (a metre-scale sphere, a non-finite dimension) trips it.
_MESH_SIZE_BUDGET = 1e8


def _guard_meshable(objects: list) -> None:
    """Fail a build fast, with a clear message, when its geometry cannot be
    tessellated in bounded time -- a non-finite dimension (NaN/Inf from a bad
    parameter) or a size so large it explodes the triangle count. Cheap: reads
    each shape's bounding box (no meshing). The process-isolation worker is the
    backstop for kernel faults this static check cannot see; this just turns the
    common, detectable cases into an instant error instead of a killed worker."""
    for o in objects:
        try:
            bb = o.shape.bounding_box()
        except Exception:  # noqa: BLE001 - unbboxable: let tessellation try (worker guards it)
            continue
        diag = math.sqrt(
            (bb.max.X - bb.min.X) ** 2 + (bb.max.Y - bb.min.Y) ** 2 + (bb.max.Z - bb.min.Z) ** 2
        )
        if not math.isfinite(diag):
            raise ValueError(
                f"{o.name!r} has non-finite geometry: a dimension came out as NaN or "
                f"infinity. Check the values (or math) feeding it."
            )
        if diag / _GLB_LINEAR_DEFLECTION > _MESH_SIZE_BUDGET:
            raise ValueError(
                f"{o.name!r} is too large to mesh at this resolution ({diag:.3g} mm across). "
                f"Scale it down, or export STEP (which needs no mesh)."
            )


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
    used: set[str] = set()
    ids: list[str] = []
    for obj in objects:
        base = "/".join(_slug(s) for s in obj.name.split("/"))
        node = base
        while node in used:
            seen[base] = seen.get(base, 0) + 1
            node = f"{base}_{seen[base]}"
        used.add(node)
        ids.append(node)
    return ids


def compound_of(shapes) -> Compound:
    """Wrap ``shapes`` in a Compound WITHOUT stealing them from their current tree.

    build123d's ``Compound(children=...)`` reparents each child via anytree, which
    empties whatever registry/snapshot compound already owns those shapes (and fails
    outright when the same shape appears twice). ``copy.copy`` shares the underlying
    TopoDS (cheap) but hands back a fresh tree node, so the originals stay put. This
    is the trap ``capture.py`` documents and avoids per-mesh."""
    return Compound(children=[copy.copy(s) for s in shapes])


def _compound_from_registry(objects) -> Compound:
    return compound_of([o.shape for o in objects])


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

    # Fail fast on geometry that would hang the tessellator (non-finite or
    # astronomically large), before any meshing or mass integration runs.
    _guard_meshable(objects)

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
            linear_deflection=_GLB_LINEAR_DEFLECTION,
            angular_deflection=0.1,
        )

        # The model summary (bbox/volume/manifold) reflects your DESIGN, so it is
        # computed from part-role objects only -- a reference is an open surface
        # (an STL Face) that would otherwise flip manifold and stretch the bbox.
        part_objects = [o for o in objects if getattr(o, "role", "part") != "reference"]
        summary_objects = part_objects or objects
        props = properties(_compound_from_registry(part_objects) if part_objects else compound)
        # Volume + center of mass come from per-object aggregation, not the
        # compound's own integrals: OCC integrates SIGNED volume, so a mirrored
        # (negative-determinant) solid cancels out and reports garbage. Each solid's
        # own .volume is unsigned and correct (this is also how mass is summed).
        agg_volume, agg_com = build_volume_com([o.shape for o in summary_objects])

        json_objects = []
        total_mass = 0.0
        labels: set[str] = set()
        # label -> density for part-role objects only, so the build-level material
        # label/density is read from a PART, never from resolved[0] (which may be a
        # role="reference" import with a different material when a reference is shown first).
        part_density: dict[str, float] = {}
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
                part_density[mat.label] = mat.density
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
            build_label = next(iter(labels))
            build_density = part_density[build_label]
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
            "volume": agg_volume,
            "centerOfMass": agg_com,
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
