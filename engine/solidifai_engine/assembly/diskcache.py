"""L2 content-addressed disk cache of part results under <root>/.solidifai-cache/.
A hit requires the BREP+sidecar to exist AND every recorded asset to still hash
the same, so an edited import_cad asset invalidates the entry."""

from __future__ import annotations

import os

from solidifai_engine.assembly import serialize
from solidifai_engine.assembly.cache import asset_fingerprint

CACHE_DIRNAME = ".solidifai-cache"


class DiskCache:
    def __init__(self, root: str) -> None:
        self.dir = os.path.join(root, CACHE_DIRNAME)
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        meta = serialize.load_meta(self.dir, key)
        if meta is None:
            self.misses += 1
            return None
        recorded = meta.get("assets", {})
        if recorded and asset_fingerprint(list(recorded)) != recorded:
            # an asset changed: stale entry
            self.misses += 1
            return None
        objs = serialize.load_result(self.dir, key)
        if objs is None:
            self.misses += 1
            return None
        self.hits += 1
        return objs

    def peek(self, key: str) -> bool:
        """True if a valid entry for `key` exists (sidecar present + assets still
        match), without loading the BREP or counting a hit/miss."""
        meta = serialize.load_meta(self.dir, key)
        if meta is None:
            return False
        recorded = meta.get("assets", {})
        if recorded and asset_fingerprint(list(recorded)) != recorded:
            return False
        return os.path.exists(serialize._brep_path(self.dir, key))

    def fingerprint(self, key: str) -> dict | None:
        """The asset fingerprint persisted with `key`'s entry (meta['assets']), or
        None when there is no entry. Lets an L2->L1 promotion carry the same
        revalidation an in-session put would; an empty map short-circuits like a
        direct-build asset-free entry."""
        meta = serialize.load_meta(self.dir, key)
        if meta is None:
            return None
        return meta.get("assets")

    def put(self, key: str, objects: list, assets_fp: dict) -> None:
        serialize.dump_result(self.dir, key, objects, assets=assets_fp)
