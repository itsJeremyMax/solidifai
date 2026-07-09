"""Serialize a part's build result (ShownObjects) to a content-addressed BREP +
JSON sidecar on disk, and read it back. BREP is exact (lossless geometry); the
sidecar carries the per-shape metadata in the same order as the compound's
solids."""

from __future__ import annotations

import json
import os

from build123d import export_brep, import_brep

from solidifai import ShownObject
from solidifai_engine.render import compound_of


def _brep_path(dir_: str, key: str) -> str:
    return os.path.join(dir_, f"{key}.brep")


def _meta_path(dir_: str, key: str) -> str:
    return os.path.join(dir_, f"{key}.json")


def dump_result(dir_: str, key: str, objects: list, *, assets: dict | None = None) -> None:
    os.makedirs(dir_, exist_ok=True)
    # Wrap COPIES: these shapes come from the in-memory node cache and are reused;
    # a plain Compound(children=...) would reparent them out of the cache.
    compound = compound_of([o.shape for o in objects])
    # Atomic write: write to a .tmp then os.replace so a crash mid-write never
    # leaves a torn file that would corrupt the cache on the next open.
    brep_final = _brep_path(dir_, key)
    brep_tmp = brep_final + ".tmp"
    export_brep(compound, brep_tmp)
    os.replace(brep_tmp, brep_final)
    meta = {
        "assets": assets or {},
        "objects": [
            {
                "name": o.name,
                "material": o.material,
                "color": list(o.color) if o.color is not None else None,
                "role": o.role,
            }
            for o in objects
        ],
    }
    meta_final = _meta_path(dir_, key)
    meta_tmp = meta_final + ".tmp"
    with open(meta_tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(meta_tmp, meta_final)


def load_meta(dir_: str, key: str) -> dict | None:
    try:
        with open(_meta_path(dir_, key), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_result(dir_: str, key: str) -> list | None:
    meta = load_meta(dir_, key)
    if meta is None or not os.path.exists(_brep_path(dir_, key)):
        return None
    try:
        compound = import_brep(_brep_path(dir_, key))
    except Exception:  # noqa: BLE001 - a torn/corrupt cache entry is a safe miss
        return None
    # import_brep returns a Compound whose .children is always empty; use
    # .solids() to extract sub-shapes in the same order they were written.
    shapes = compound.solids()
    entries = meta["objects"]
    if len(shapes) != len(entries):
        # Mismatched counts: corrupt or incompatible entry; safe miss beats wrong geometry.
        return None
    return [
        ShownObject(
            name=e["name"],
            shape=shape,
            color=tuple(e["color"]) if e["color"] is not None else None,
            material=e["material"],
            role=e.get("role", "part"),
        )
        for shape, e in zip(shapes, entries, strict=True)
    ]
