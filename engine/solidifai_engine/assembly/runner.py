"""Execute skeleton.py and part build functions. Each runs against an isolated
namespace; parts additionally run inside a build_scope() so their show() calls
are captured per-node (the purity invariant)."""

from __future__ import annotations

import inspect
import os
from typing import Any

import solidifai
from solidifai import SkeletonResult


def _default_param_values(params_schema: dict) -> dict:
    return {k: v["value"] for k, v in (params_schema or {}).items()}


def _exec_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        code = f.read()
    ns: dict[str, Any] = {"__name__": "__solidifai_node__"}
    compiled = compile(code, f"<{os.path.basename(path)}>", "exec")
    exec(compiled, ns)
    return ns


def run_skeleton(skeleton_path: str, *, params: dict, parent: dict | None) -> SkeletonResult:
    # NOTE: the parameter name "parent" is RESERVED -- the runner injects the
    # parent skeleton's scalar dict via this name. Don't use it for unrelated params.
    solidifai.set_workspace_root(os.path.dirname(skeleton_path))
    ns = _exec_file(skeleton_path)
    build_fn = ns.get("build")
    if not callable(build_fn):
        raise ValueError(f"{skeleton_path!r}: skeleton defines no build()")
    raw_schema = ns.get("PARAMS")
    schema = raw_schema if isinstance(raw_schema, dict) else {}
    values = _default_param_values(schema)
    values.update(params or {})
    sig = inspect.signature(build_fn)
    if "parent" in sig.parameters:
        result = build_fn(parent=parent or {}, **values)
    else:
        result = build_fn(**values)
    if not isinstance(result, SkeletonResult):
        raise ValueError(f"{skeleton_path!r}: build() must return skeleton() (a SkeletonResult)")
    return result


def run_part(part_path: str, *, inputs: dict):
    """Build one part in an isolated scope and return (objects, assets). The part
    sees only `inputs`; its show() calls are captured by build_scope(), so the
    build is a pure function of (source, inputs) with no global side effects.
    assets is the list of import_cad paths recorded by the scope."""
    solidifai.set_workspace_root(
        os.path.dirname(os.path.dirname(part_path))
    )  # workspace root, not parts/
    ns = _exec_file(part_path)
    build_fn = ns.get("build")
    if not callable(build_fn):
        raise ValueError(f"{part_path!r}: part defines no build(inputs)")
    with solidifai.build_scope() as scope:
        build_fn(dict(inputs))
        return list(scope.objects), list(scope.assets)
