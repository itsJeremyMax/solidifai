"""Best-effort parallel pre-pass that warms the disk cache for the parts a build
will need, so the normal build_node finds them in L2 and skips the kernel.

The disk cache is the IPC: fork workers build cache-MISS parts and write their
BREP into <root>/.solidifai-cache/. The pool is OPTIONAL and BEST-EFFORT; any
failure leaves parts unwarmed and build_node builds them in-process."""

from __future__ import annotations

import multiprocessing
import os

from solidifai import SkeletonResult
from solidifai_engine.assembly import manifest as manifest_mod
from solidifai_engine.assembly import runner, serialize
from solidifai_engine.assembly.cache import asset_fingerprint, part_key

WARM_TIMEOUT_S = 120.0


def enumerate_part_builds(node_dir, *, params, parent, cache, disk, workspace_root=None):
    """Dry-run the DAG (skeletons only) and return [(part_path, inputs, key)] for
    leaf parts not already in cache (L1) or disk (L2). Builds no geometry.
    workspace_root is the tree root, threaded so nested skeletons resolve assets
    against it (matches graph.build_node)."""
    ws_root = workspace_root or node_dir
    man = manifest_mod.load_manifest(node_dir)
    if man.skeleton:
        skel = runner.run_skeleton(
            os.path.join(node_dir, man.skeleton),
            params=params,
            parent=parent,
            workspace_root=ws_root,
        )
    else:
        skel = SkeletonResult()
    out = []
    for child in man.children:
        inputs = skel.resolve_inputs(child.inputs)
        if child.kind == "part":
            inputs = dict(inputs)
            inputs.update(skel.resolve_shapes(child.shape_inputs))
            part_path = os.path.join(node_dir, child.source)
            with open(part_path, encoding="utf-8") as f:
                src = f.read()
            key = part_key(src, inputs)
            in_l1 = cache is not None and cache._store.get(key) is not None
            in_l2 = disk is not None and disk.peek(key)
            if not in_l1 and not in_l2:
                out.append((part_path, inputs, key))
        else:
            # Sub-assembly: recurse with this child's resolved inputs as its parent scalars.
            out.extend(
                enumerate_part_builds(
                    os.path.join(node_dir, child.source),
                    params={},
                    parent=inputs,
                    cache=cache,
                    disk=disk,
                    workspace_root=ws_root,
                )
            )
    return out


def _build_one(args):
    """Worker: build one part and write it to the disk cache. Runs in a fork
    child (inherits the parent's loaded OCC). Returns the key on success, None
    on any failure (the part is left for the in-process fallback)."""
    part_path, inputs, key, cache_dir = args
    try:
        objs, assets, features = runner.run_part(part_path, inputs=inputs)
        serialize.dump_result(
            cache_dir, key, objs, assets=asset_fingerprint(assets), features=features
        )
        return key
    except Exception:  # noqa: BLE001 - a worker failure must never break the build
        return None


def warm_cache_parallel(
    misses, disk, *, min_parts: int = 2, timeout: float = WARM_TIMEOUT_S
) -> int:
    """Best-effort: build the `misses` in a fork pool, writing into the disk
    cache. Returns the count warmed. A no-op below `min_parts`. Any pool error,
    timeout, or worker crash is swallowed -- build_node then builds the unwarmed
    parts in-process, so correctness never depends on this."""
    if disk is None or len(misses) < min_parts:
        return 0
    args = [(pp, inputs, key, disk.dir) for pp, inputs, key in misses]
    try:
        ctx = multiprocessing.get_context("fork")
        workers = min(len(args), max(1, (os.cpu_count() or 2) - 1))
        with ctx.Pool(processes=workers) as pool:
            results = pool.map_async(_build_one, args)
            done = results.get(timeout=timeout)
        return sum(1 for r in done if r is not None)
    except Exception:  # noqa: BLE001 - fork unavailable / worker crash / timeout -> sequential fallback
        return 0
