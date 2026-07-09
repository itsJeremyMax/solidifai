"""Flatten an assembly into a single, self-contained, runnable ``model.py``.

The emitted file is a derived export: a plain single-model script that, run in a
normal ``execute_script`` Session, reproduces the composed assembly (same parts,
same placement, same path-id names). It depends only on the public ``solidifai``
API and ``build123d`` -- NOT on engine internals -- so the exported file stays
portable and stable across engine refactors.

Approach (self-contained, chosen over importing the engine runtime):

  - The skeleton's PARAMS become the model's PARAMS (the workspace sliders).
  - Each node's source (skeleton.py and every parts/<id>.py, recursively through
    sub-assemblies) is embedded verbatim as a string and exec'd in an isolated
    namespace at build time -- the SAME execution the engine runner performs, so
    geometry is never re-derived by hand.
  - Children are placed at their attach frame with Shape.moved() (frame
    COMPOSE, matching the composer) and shown with their "<child>/<name>" path id.
    Per-segment id slugging + collision dedup is NOT re-implemented here: the flat
    model calls show() with the composed path names in the same order as the
    engine, so the flat Session's render (render._node_ids) produces byte-identical
    ids -- verified against the assembly's own model.json. A part that produces no
    geometry raises, mirroring the engine's per-part guard (see _run_part below).

Importing ``solidifai_engine.assembly.graph`` from the exported model was the
alternative; it was rejected because it couples a user-facing model.py to engine
internals (a private import path that can change), whereas inlining the sources
yields a file that runs anywhere ``solidifai`` + ``build123d`` are importable.
"""

from __future__ import annotations

import json
import os

from solidifai_engine.assembly import manifest as manifest_mod


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _collect_node(node_dir: str, node_key: str, nodes: dict) -> dict:
    """Recursively gather a node's skeleton source + children into a serializable
    spec, keyed by a flat node id. ``nodes`` maps node_key -> spec; returns the
    spec for this node. Part sources are embedded inline; sub-assemblies recurse."""
    man = manifest_mod.load_manifest(node_dir)
    spec: dict = {
        "skeleton_src": _read(os.path.join(node_dir, man.skeleton)) if man.skeleton else None,
        "children": [],
    }
    for child in man.children:
        entry = {
            "id": child.id,
            "kind": child.kind,
            "attach": child.attach,
            "inputs": list(child.inputs),
        }
        if child.kind == "part":
            entry["shape_inputs"] = list(child.shape_inputs)
            entry["src"] = _read(os.path.join(node_dir, child.source))
        else:
            sub_key = f"{node_key}__{child.id}"
            entry["node"] = sub_key
            _collect_node(os.path.join(node_dir, child.source), sub_key, nodes)
        spec["children"].append(entry)
    nodes[node_key] = spec
    return spec


def flatten_to_model(root: str, param_values: dict | None = None) -> str:
    """Return the source of a self-contained ``model.py`` that reproduces the
    assembly rooted at ``root``. Raises if there is no root skeleton (an assembly
    with no skeleton has no shared PARAMS to surface).

    ``param_values`` (the session's live values) is overlaid onto the skeleton's
    static PARAMS defaults, so the export reproduces the CURRENT composed model
    after any set_params, not just the skeleton's authored defaults. Sliders stay
    overridable (the emitted PARAMS keep their min/max/step)."""
    nodes: dict = {}
    _collect_node(root, "root", nodes)
    root_spec = nodes["root"]
    params = {}
    if root_spec["skeleton_src"]:
        params = _extract_params(root_spec["skeleton_src"])
    for name, val in (param_values or {}).items():
        if isinstance(params.get(name), dict):
            params[name] = {**params[name], "value": val}

    nodes_literal = json.dumps(nodes, indent=4)
    params_literal = json.dumps(params, indent=4)
    return _TEMPLATE.format(nodes=nodes_literal, params=params_literal)


def _extract_params(skeleton_src: str) -> dict:
    """Static PARAMS dict from a skeleton source (literal-eval, no exec). Falls back
    to {} when PARAMS is absent or not a literal -- the model still runs at the
    skeleton's own defaults."""
    import ast

    try:
        tree = ast.parse(skeleton_src)
    except SyntaxError:
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PARAMS" for t in node.targets
        ):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                return {}
            return value if isinstance(value, dict) else {}
    return {}


# The emitted model.py. _NODES holds every node's skeleton source + children
# (sources inline); _run_node mirrors the engine's top-down compose using only
# the public solidifai API. build(**PARAMS) composes the whole tree and show()s
# each placed object under its path id.
_TEMPLATE = '''"""Flattened model.py -- derived from a solidifai assembly.

Self-contained: depends only on solidifai + build123d. Regenerate with
export_flat_model; hand-edits here do not flow back to the assembly sources.
"""
from solidifai import skeleton, show, build_scope, SkeletonResult

PARAMS = {params}

# Each node: its skeleton source (or None) and its children (part sources inline).
_NODES = {nodes}


def _exec(src):
    ns = {{"__name__": "__solidifai_flat__"}}
    exec(compile(src, "<flat>", "exec"), ns)
    return ns


def _run_skeleton(src, params, parent):
    ns = _exec(src)
    build_fn = ns["build"]
    schema = ns.get("PARAMS") if isinstance(ns.get("PARAMS"), dict) else {{}}
    values = {{k: v.get("value") for k, v in schema.items()}}
    values.update(params or {{}})
    import inspect
    if "parent" in inspect.signature(build_fn).parameters:
        return build_fn(parent=parent or {{}}, **values)
    return build_fn(**values)


def _run_part(src, inputs, part_id):
    ns = _exec(src)
    with build_scope() as scope:
        ns["build"](dict(inputs))
        objs = list(scope.objects)
    # Mirror the engine's per-part "no geometry" guard (graph.build_child): a part
    # that shows nothing (or only non-solids) is an error, not a silently-dropped
    # part -- otherwise this "exact reproduction" would diverge from the assembly.
    if not objs or sum(len(o.shape.solids()) for o in objs) == 0:
        raise ValueError(part_id + ": part produced no geometry; did you forget show()?")
    return objs


def _place(objects, at, prefix):
    out = []
    for o in objects:
        name = prefix + "/" + o.name if prefix else o.name
        out.append(_Shown(name, o.shape.moved(at), o.material, o.color, o.role))
    return out


def _run_node(node_key, params, parent):
    spec = _NODES[node_key]
    if spec["skeleton_src"]:
        skel = _run_skeleton(spec["skeleton_src"], params, parent)
    else:
        skel = SkeletonResult()
    placed = []
    for child in spec["children"]:
        inputs = skel.resolve_inputs(child["inputs"])
        at = skel.frame_for(child["attach"])
        if child["kind"] == "part":
            inputs = dict(inputs)
            inputs.update(skel.resolve_shapes(child.get("shape_inputs", [])))
            objs = _run_part(child["src"], inputs, child["id"])
        else:
            objs = _run_node(child["node"], {{}}, inputs)
        placed.extend(_place(objs, at, child["id"]))
    return placed


class _Shown:
    """Carries a placed object (sub-node results stay objects between levels)."""
    def __init__(self, name, shape, material, color, role="part"):
        self.name = name
        self.shape = shape
        self.material = material
        self.color = color
        self.role = role


def build(**params):
    for o in _run_node("root", params, None):
        show(o.shape, name=o.name, material=o.material, color=o.color, role=o.role)


build(**{{k: v["value"] for k, v in PARAMS.items()}})
'''
