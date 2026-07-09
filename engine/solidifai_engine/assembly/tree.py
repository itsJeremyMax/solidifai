"""Read-only nested description of an assembly: skeleton params/scalars/frames and
children (recursively). Executes skeleton code to read its declared outputs but
never builds part geometry, so it is cheap and side-effect free."""

from __future__ import annotations

import os

from solidifai_engine.assembly import manifest as manifest_mod
from solidifai_engine.assembly import runner


def _skeleton_desc(node_dir: str, man, parent: dict | None) -> dict | None:
    if not man.skeleton:
        return None
    ns = runner._exec_file(os.path.join(node_dir, man.skeleton))
    raw_params = ns.get("PARAMS")
    params = raw_params if isinstance(raw_params, dict) else {}
    # Run the skeleton with default param values to enumerate scalars + frames.
    values = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in params.items()}
    result = runner.run_skeleton(
        os.path.join(node_dir, man.skeleton), params=values, parent=parent or {}
    )
    return {
        "params": params,
        "scalars": sorted(result.scalars.keys()),
        "frames": sorted(result.frames.keys()),
        "shapes": sorted(result.shapes.keys()),
        # Declared joints (full records: kind/frame/axis/limits/between) so
        # check_interfaces can validate them and check_motion can drive them.
        "joints": list(getattr(result, "joints", []) or []),
    }


def assembly_tree(node_dir: str, *, parent: dict | None = None) -> dict:
    man = manifest_mod.load_manifest(node_dir)
    skel = _skeleton_desc(node_dir, man, parent)
    children = []
    for c in man.children:
        entry = {
            "id": c.id,
            "kind": c.kind,
            "source": c.source,
            "attach": c.attach,
            "inputs": list(c.inputs),
            "shape_inputs": list(c.shape_inputs),
            # Every placement of this one definition: [{frame, mirror}, ...]. A
            # legacy single-placement child resolves to one occurrence at attach.
            "occurrences": [
                {"frame": o.frame, "mirror": o.mirror}
                for o in manifest_mod.effective_occurrences(c)
            ],
        }
        if c.kind == "assembly":
            # The sub-skeleton only needs its input keys present to run and
            # enumerate frame/scalar names. Use 1 (not 0) so a skeleton that
            # divides by a parent value does not raise ZeroDivisionError.
            sub_parent = {name: 1 for name in c.inputs}
            sub = assembly_tree(os.path.join(node_dir, c.source), parent=sub_parent)
            entry["skeleton"] = sub["skeleton"]
            entry["children"] = sub["children"]
        children.append(entry)
    return {"skeleton": skel, "children": children}
