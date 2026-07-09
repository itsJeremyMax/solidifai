"""In-memory content-addressed cache of per-part build results. Key is the part
source plus its resolved scalar inputs; the value is the live ShownObject list a
part produced in its local frame. The attach frame is intentionally excluded so a
moved (but otherwise unchanged) part is reused and only recomposed."""

from __future__ import annotations

import contextlib
import hashlib
import weakref

ENGINE_BUILD_VERSION = "b4"  # bump to invalidate all cached results across an engine change


def _canon_scalar(v) -> str:
    """Canonical string for a scalar input, TYPE-TAGGED so distinct types never
    collapse to one form. Without the tag ``True``, ``1`` and ``"1"`` all render
    as ``"1.0"`` (float coercion), which is a false cache hit -> stale geometry
    when a skeleton switches a published scalar's type. Tag order matters: bool is
    a subclass of int, so it must be checked before the numeric branch."""
    if isinstance(v, bool):
        return f"bool:{v}"
    if isinstance(v, str):
        # check before float() so a numeric string ("1") never coerces to num:1.0
        return f"str:{v!r}"
    try:
        return f"num:{float(v)!r}"
    except (TypeError, ValueError):
        return f"repr:{v!r}"


def _is_geometry(v) -> bool:
    """True when v is a build123d shape (Sketch/Face/Wire/Solid/Part/Compound...),
    as opposed to a scalar. Lazy import so the scalar-only path needs no build123d;
    duck-type fallback so a real shape is never misrouted to the scalar branch if
    the import ever fails."""
    try:
        from build123d import Shape
    except Exception:  # noqa: BLE001
        return hasattr(v, "wrapped") and hasattr(v, "bounding_box")
    return isinstance(v, Shape)


# Digest memo keyed by shape IDENTITY (build123d shapes hash/eq by identity). A
# published profile handed to several parts in one compose is serialized once, not
# once per consumer (O(parts x shapes) -> O(distinct shapes)). Weak keys so an
# entry vanishes when its shape is collected -- no cross-build staleness and no id
# reuse, since a new skeleton run builds fresh shape objects.
_DIGEST_MEMO: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _shape_digest(shape) -> str:
    """SHA-256 of a shape's BREP bytes. Deterministic for an identically-built
    shape, so the same published profile hashes equal (cache hit) and a changed
    one differs (rebuild). Memoized by shape identity within/across a compose so
    each distinct shape is serialized once. Raises a clean ValueError on an
    empty/invalid shape rather than letting a raw OCC error escape."""
    try:
        hit = _DIGEST_MEMO.get(shape)
    except TypeError:  # a shape that is not weak-referenceable/hashable: skip memo
        hit = None
    if hit is not None:
        return hit
    import io

    from build123d import export_brep

    buf = io.BytesIO()
    try:
        ok = export_brep(shape, buf)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            f"a published shape could not be serialized for hashing "
            f"(empty or invalid geometry): {exc}"
        ) from exc
    data = buf.getvalue()
    if ok is False or not data:
        raise ValueError(
            "a published shape could not be serialized for hashing (empty or invalid geometry)"
        )
    digest = hashlib.sha256(data).hexdigest()
    # non-weak-referenceable shape: correctness holds, just no memo
    with contextlib.suppress(TypeError):
        _DIGEST_MEMO[shape] = digest
    return digest


def part_key(source_text: str, inputs: dict, path: str = "", assets: dict | None = None) -> str:
    """Stable content key for a leaf part: source + canonical scalar inputs +
    consumed-geometry BREP hashes + asset content hashes + engine version.

    ``path`` is accepted for call-site compatibility but is DELIBERATELY NOT part
    of the key: content (source + inputs + shape digests + asset fingerprints +
    engine version) uniquely determines a pure part's geometry. Folding in the
    node-relative path both defeated instancing dedup (20 identical brackets got
    20 keys) and created a false cross-node invariant (two different sub-assemblies
    with an identically-wired part collided on one node-relative path). Dropping it
    makes reuse safe and removes the collision.

    The attach frame is likewise excluded -- a moved but otherwise unchanged part
    is a cache hit and only needs recomposition. A consumed published shape DOES
    change the built geometry, so its BREP hash is part of the key."""
    scalars: dict = {}
    shapes: dict = {}
    for k, v in inputs.items():
        (shapes if _is_geometry(v) else scalars)[k] = v
    items = ";".join(f"{k}={_canon_scalar(v)}" for k, v in sorted(scalars.items()))
    geom_items = ";".join(f"{k}={_shape_digest(v)}" for k, v in sorted(shapes.items()))
    asset_items = ";".join(f"{k}={v}" for k, v in sorted((assets or {}).items()))
    blob = f"{ENGINE_BUILD_VERSION}\x00{source_text}\x00{items}\x00{geom_items}\x00{asset_items}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def asset_fingerprint(paths) -> dict:
    """Map each asset path -> sha256 of its current contents (skips missing)."""
    fp: dict[str, str] = {}
    for p in paths:
        try:
            with open(p, "rb") as f:
                fp[p] = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            continue
    return fp


class NodeCache:
    """Per-session dict of part_key -> (list[ShownObject], asset fingerprint).
    hits/misses are observable for tests and telemetry. The stored asset
    fingerprint gives L1 the same post-hoc revalidation the DiskCache has, so an
    imported CAD asset edited mid-session is not served stale from L1 (which is
    checked before L2)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[list, dict | None, list]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        objects, assets_fp, _features = entry
        if assets_fp and asset_fingerprint(list(assets_fp)) != assets_fp:
            # a recorded asset changed on disk: stale entry, treat as a miss
            self.misses += 1
            return None
        self.hits += 1
        return objects

    def features(self, key: str) -> list:
        """The declared FeatureRecords stored with ``key`` (live faces, part-local
        frame), or [] when there is no entry. Consulted only after a get() hit."""
        entry = self._store.get(key)
        return list(entry[2]) if entry is not None else []

    def put(
        self, key: str, objects: list, assets_fp: dict | None = None, features: list | None = None
    ) -> None:
        self._store[key] = (objects, assets_fp, list(features or []))
