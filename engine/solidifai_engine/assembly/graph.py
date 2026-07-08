"""Walk a node's manifest into its composed object list. Top-down: run the
skeleton, then build each child against only the skeleton outputs it declared
and place it at its attach frame. No child reads another child."""

from __future__ import annotations

import os

from solidifai import SkeletonResult
from solidifai_engine.assembly import compose, runner
from solidifai_engine.assembly import manifest as manifest_mod


def build_child(node_dir: str, skel, child, *, cache=None, disk=None) -> tuple[list, str | None]:
    """Build (or fetch from cache) one part child's local-frame objects against an
    already-run skeleton. Returns (objects, key); key is the content-cache key for a
    part (None for a sub-assembly, which is not cached at this level).

    This is the single source of truth for the per-part cache key and the L1->L2
    get / run / put sequence, so an isolated build (the authoring round) and the
    whole-assembly compose use IDENTICAL keys and reuse each other's results."""
    inputs = skel.resolve_inputs(child.inputs)
    if child.kind != "part":
        # A sub-assembly: recurse, passing this node's resolved scalars as the child's
        # parent. Published shapes flow to parts, not across the sub-assembly boundary.
        sub_dir = os.path.join(node_dir, child.source)
        return build_node(sub_dir, params={}, parent=inputs, cache=cache, disk=disk), None

    # A part also consumes any skeleton shapes it declared, merged into the same
    # inputs dict it already receives (build(inputs) is unchanged).
    inputs.update(skel.resolve_shapes(child.shape_inputs))

    part_path = os.path.join(node_dir, child.source)
    objs = None
    key = None
    if cache is not None or disk is not None:
        # compute key only when a cache layer is active
        from solidifai_engine.assembly.cache import part_key

        with open(part_path, encoding="utf-8") as f:
            src = f.read()
        key = part_key(src, inputs, path=child.source)
        if cache is not None:
            objs = cache.get(key)
        if objs is None and disk is not None:
            objs = disk.get(key)
            if objs is not None and cache is not None:
                # promote L2 hit into L1 for subsequent calls this session, carrying
                # L2's asset fingerprint so the promoted entry revalidates an edited
                # asset exactly like a direct-build entry (a reopened workspace has a
                # cold L1 but warm L2, so this is the only place the fingerprint lands).
                cache.put(key, objs, disk.fingerprint(key))
    if objs is None:
        from solidifai_engine.assembly.cache import asset_fingerprint

        objs, assets = runner.run_part(part_path, inputs=inputs)
        # A part that shows nothing (or only non-solids) has no geometry to
        # compose. Catch it here with a readable message rather than letting
        # an empty Compound reach export_brep, which raises an opaque OCC
        # "Write_s()" TypeError and would also poison the cache.
        if not objs or sum(len(o.shape.solids()) for o in objs) == 0:
            raise ValueError(f"part {child.id!r} produced no geometry; did you forget show()?")
        assets_fp = asset_fingerprint(assets)
        if key is not None and cache is not None:
            cache.put(key, objs, assets_fp)
        if key is not None and disk is not None:
            disk.put(key, objs, assets_fp)
    return objs, key


def build_node(node_dir: str, *, params: dict, parent: dict | None, cache=None, disk=None) -> list:
    man = manifest_mod.load_manifest(node_dir)

    if man.skeleton:
        skel = runner.run_skeleton(
            os.path.join(node_dir, man.skeleton), params=params, parent=parent
        )
    else:
        skel = SkeletonResult()  # degenerate node: parts attach at origin, no shared scalars

    placed: list = []
    for child in man.children:
        objs, _key = build_child(node_dir, skel, child, cache=cache, disk=disk)
        placed.extend(compose.place(objs, at=skel.frame_for(child.attach), path_prefix=child.id))
    return placed
