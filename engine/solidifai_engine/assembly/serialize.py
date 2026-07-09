"""Serialize a part's build result (ShownObjects) to a content-addressed BREP +
JSON sidecar on disk, and read it back. BREP is exact (lossless geometry); the
sidecar (format 2) carries per-object metadata AND each object's solid count, so
load re-splits the flattened solids back to their originating objects even when an
object holds several solids. An object carrying non-solid geometry (a face/wire
that ``.solids()`` would drop) makes the whole entry non-cacheable rather than let
load silently misattribute or lose it."""

from __future__ import annotations

import contextlib
import json
import os

from build123d import export_brep, import_brep

from solidifai import ShownObject
from solidifai_engine.render import compound_of

SIDECAR_FORMAT = 2  # bump when the sidecar shape changes so stale entries re-serialize


def _brep_path(dir_: str, key: str) -> str:
    return os.path.join(dir_, f"{key}.brep")


def _meta_path(dir_: str, key: str) -> str:
    return os.path.join(dir_, f"{key}.json")


def _solid_info(shape) -> tuple[int, bool]:
    """(solid_count, has_non_solid) for one object's shape. ``has_non_solid`` is
    True when the shape carries geometry that ``.solids()`` would drop -- detected
    by comparing the shape's face count to the faces owned by its solids (a
    face/wire-only object has faces but zero solids; a pure solid's faces all
    belong to its solids). Falls back to "non-solid iff no solids" if the shape
    cannot enumerate faces."""
    solids = shape.solids()
    n = len(solids)
    try:
        total_faces = len(shape.faces())
        solid_faces = sum(len(s.faces()) for s in solids)
        return n, (total_faces != solid_faces)
    except Exception:  # noqa: BLE001 - unmeasurable: treat "no solids" as non-solid
        return n, (n == 0)


def dump_result(dir_: str, key: str, objects: list, *, assets: dict | None = None) -> None:
    os.makedirs(dir_, exist_ok=True)
    infos = [_solid_info(o.shape) for o in objects]
    meta_final = _meta_path(dir_, key)
    meta_tmp = meta_final + ".tmp"

    if any(non_solid for _, non_solid in infos):
        # At least one object holds geometry that cannot round-trip through
        # solids(). Persist a non-cacheable marker (no BREP) so load is a clean
        # miss forever for this content -- never a silent misattribution.
        marker = {"format": SIDECAR_FORMAT, "cacheable": False, "assets": assets or {}}
        with open(meta_tmp, "w", encoding="utf-8") as f:
            json.dump(marker, f)
        os.replace(meta_tmp, meta_final)
        # Drop any stale BREP left from an earlier (differing) serialization.
        with contextlib.suppress(OSError):
            os.remove(_brep_path(dir_, key))
        return

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
        "format": SIDECAR_FORMAT,
        "cacheable": True,
        "assets": assets or {},
        "objects": [
            {
                "name": o.name,
                "material": o.material,
                "color": list(o.color) if o.color is not None else None,
                "role": o.role,
                "solid_count": n,
            }
            for o, (n, _) in zip(objects, infos, strict=True)
        ],
    }
    with open(meta_tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(meta_tmp, meta_final)


def load_meta(dir_: str, key: str) -> dict | None:
    try:
        with open(_meta_path(dir_, key), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _shown(e: dict, shape) -> ShownObject:
    return ShownObject(
        name=e["name"],
        shape=shape,
        color=tuple(e["color"]) if e["color"] is not None else None,
        material=e["material"],
        role=e.get("role", "part"),
    )


def load_result(dir_: str, key: str) -> list | None:
    meta = load_meta(dir_, key)
    if meta is None:
        return None
    if meta.get("cacheable") is False:
        # A non-cacheable entry (an object held non-solid geometry): always a clean
        # miss, never a degraded/misattributed load.
        return None
    if not os.path.exists(_brep_path(dir_, key)):
        return None
    try:
        compound = import_brep(_brep_path(dir_, key))
    except Exception:  # noqa: BLE001 - a torn/corrupt cache entry is a safe miss
        return None
    # import_brep returns a Compound whose .children is always empty; use
    # .solids() to extract sub-shapes in the same order they were written.
    solids = compound.solids()
    entries = meta["objects"]
    counts = [e.get("solid_count") for e in entries]

    if any(c is None for c in counts):
        # Legacy (format < 2) sidecar with no per-object counts: fall back to the
        # old 1:1 assumption (one solid per object). Mismatch -> safe miss.
        if len(solids) != len(entries):
            return None
        return [_shown(e, s) for e, s in zip(entries, solids, strict=True)]

    if sum(counts) != len(solids):
        # Counts disagree with the stored geometry: corrupt/incompatible -> safe miss.
        return None
    out: list = []
    idx = 0
    for e, c in zip(entries, counts, strict=True):
        obj_solids = solids[idx : idx + c]
        idx += c
        # One solid stays a bare solid (matches the historical single-solid shape);
        # several are rewrapped into one Compound so the object keeps all its solids.
        shape = obj_solids[0] if c == 1 else compound_of(obj_solids)
        out.append(_shown(e, shape))
    return out
