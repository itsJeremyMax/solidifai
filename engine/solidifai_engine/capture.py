"""Pure geometry/validation logic behind ``Session.capture_views``.

Extracted from ``session.py`` so the mesh-assembly and view/focus/highlight
resolution can be unit-tested without a full Session, and so
``Session.capture_views`` stays a thin validate -> assemble -> resolve ->
render -> shape pipeline. Every function here is pure (or, for
``assemble_capture_mesh``, side-effect-free on its inputs): failures raise
``CaptureError`` / ``ValueError`` with the exact messages the (still) public
error envelope surfaces, rather than returning ``{"ok": False, ...}`` dicts
themselves — that shaping stays the caller's job.
"""

from __future__ import annotations

import concurrent.futures
from typing import NamedTuple

import solidifai
from solidifai_engine import features as feature_geom
from solidifai_engine import materials as _materials
from solidifai_engine import section as section_mod

# Tessellation linear deflection (mm) for capture_views renders. Fine enough to
# be faithful for visual debugging, coarse enough to render fast.
TESS_TOLERANCE = 0.1

# Hard ceiling for the section boolean (it runs on a worker thread). OCC
# booleans cannot be interrupted, so on timeout the worker is abandoned and
# the capture returns an error promptly. The abandoned thread keeps computing
# (and may hold the GIL), so a follow-up request can still stall until the
# boolean finishes; what the timeout buys is the error response, not a kill.
SECTION_TIMEOUT_S = 30.0

# Section default camera: the face view on the removed (+axis) side, looking
# square at the cut plane.
_SECTION_FACE_VIEW = {"x": "right", "y": "back", "z": "top"}


class CaptureError(Exception):
    """A capture pre-render failure whose message is surfaced to the agent verbatim."""


class CaptureMesh(NamedTuple):
    vertices: list
    tris: list
    groups: list | None
    cap_mesh: tuple | None


def _run_with_timeout(fn, timeout_s: float, /, *args):
    """Run ``fn(*args)`` on a worker thread; raise the builtin TimeoutError past
    the deadline (concurrent.futures.TimeoutError IS TimeoutError on 3.11+).
    The worker is abandoned, not killed: it keeps running (possibly holding the
    GIL inside native code), so later requests may stall until it finishes."""
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(fn, *args).result(timeout=timeout_s)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


def _srgb(c: float) -> float:
    """Encode a linear-RGB channel (0..1) to sRGB display space.

    ``materials.base_color`` is linear; the viewport color-manages it for
    display but VTK's offscreen render does not, so colors must be encoded
    here before reaching ``SetColor`` or every part renders darker than the
    user sees. Standard sRGB OETF.
    """
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * c ** (1 / 2.4) - 0.055


def validate_capture_args(
    layout: str, resolution, section: dict | None, explode: float
) -> tuple[str | None, int | None]:
    """Validate the cheap, pre-render capture_views args. Returns
    ``(error_or_none, normalized_resolution)`` — resolution is coerced from a
    whole-number float to int when valid; left as-is (invalid) otherwise."""
    if layout not in ("separate", "grid"):
        return f"unknown layout {layout!r}; expected 'separate' or 'grid'", resolution
    if isinstance(resolution, float) and resolution.is_integer():
        resolution = int(resolution)
    if (
        not isinstance(resolution, int)
        or isinstance(resolution, bool)
        or not (256 <= resolution <= 2048)
    ):
        return f"resolution must be an integer in 256..2048, got {resolution!r}", resolution
    if section is not None:
        if explode and explode > 0:
            return "section cannot be combined with explode", resolution
        if (
            not isinstance(section, dict)
            or section.get("axis") not in section_mod.AXES
            or not isinstance(section.get("offset_mm"), (int, float))
            or isinstance(section.get("offset_mm"), bool)
        ):
            return 'section must be {"axis": "x"|"y"|"z", "offset_mm": <number>}', resolution
    return None, resolution


def assemble_capture_mesh(
    model,
    objects,
    *,
    explode: float,
    section: dict | None,
    color: bool,
    timeout_s: float = SECTION_TIMEOUT_S,
) -> CaptureMesh:
    """Build the (vertices, tris, color groups, section cap mesh) for a
    capture, honoring at most one of ``section`` or ``explode`` (the caller
    already rejected combining them). Never mutates ``model``/``objects``:
    section and explode both operate on copies. Raises ``CaptureError`` /
    ``ValueError`` on failure with the exact messages the caller surfaces."""
    cap_mesh = None
    # Render-time explode: for THIS capture only, spread the shown parts
    # radially so a multi-part fit can be reviewed pulled apart (the agent's
    # equivalent of the viewport's Explode slider). exploded() returns
    # translated COPIES for off-center parts but the ORIGINAL object for a
    # concentric / unmovable one, so we must NOT wrap the result in a
    # Compound — that would reparent a shared original out of the caller's
    # model and corrupt it. Instead we merge per-part meshes. Nothing here
    # mutates model / objects, so the saved + exported model stays assembled.
    spread = None
    if explode and explode > 0 and len(objects) > 1:
        spread = solidifai.exploded([o.shape for o in objects], explode)
    # Colored path: one display-sRGB base color per object (same resolver the
    # viewport uses). Falls back to clay when color is off or no object
    # snapshot exists.
    want_groups = bool(color and objects)
    groups: list | None = [] if want_groups else None
    if section is not None:
        # Plane-cut COPIES (the boolean never touches the live shapes), under
        # a hard timeout; compose per-object cut meshes exactly like the
        # explode path (concatenate, never re-Compound).
        shapes = [o.shape for o in objects] if objects else [model]
        try:
            cut_shapes, cap_faces = _run_with_timeout(
                section_mod.cut_with_caps,
                timeout_s,
                shapes,
                section["axis"],
                float(section["offset_mm"]),
            )
        except TimeoutError:
            raise CaptureError(
                f"section cut timed out after {timeout_s:.0f}s "
                "(the abandoned cut may keep the engine busy a while longer); "
                "try a simpler model or a different offset"
            ) from None
        vertices: list = []
        tris: list = []
        for idx, cshape in enumerate(cut_shapes):
            if not cshape.faces():
                continue  # this part lies entirely on the removed side
            pv, pt = cshape.tessellate(TESS_TOLERANCE)
            pv = [tuple(v) for v in pv]
            base = len(vertices)
            vertices.extend(pv)
            tris.extend((a + base, b + base, c + base) for (a, b, c) in pt)
            if groups is not None:
                o = objects[idx]
                lin = _materials.RESOLVER.resolve(
                    o.material, color=o.color
                ).base_color  # linear RGB
                groups.append((pv, pt, tuple(_srgb(c) for c in lin)))
        if not vertices:
            raise CaptureError("section removed the entire model")
        if cap_faces:
            cverts, ctris = feature_geom.tessellate(cap_faces, TESS_TOLERANCE)
            cap_mesh = (cverts, ctris) if cverts else None
    elif spread is not None:
        # Silhouette = concatenation of the spread per-part meshes (no
        # Compound, no reparenting); build the colored groups from the same
        # per-part tessellation in one pass.
        vertices = []
        tris = []
        for o, shape in zip(objects, spread, strict=True):
            pv, pt = shape.tessellate(TESS_TOLERANCE)
            pv = [tuple(v) for v in pv]
            base = len(vertices)
            vertices.extend(pv)
            tris.extend((a + base, b + base, c + base) for (a, b, c) in pt)
            if groups is not None:
                lin = _materials.RESOLVER.resolve(
                    o.material, color=o.color
                ).base_color  # linear RGB
                groups.append((pv, pt, tuple(_srgb(c) for c in lin)))
    else:
        verts, tris = model.tessellate(TESS_TOLERANCE)
        vertices = [tuple(v) for v in verts]
        if groups is not None:
            for o in objects:
                lin = _materials.RESOLVER.resolve(
                    o.material, color=o.color
                ).base_color  # linear RGB
                rgb = tuple(_srgb(c) for c in lin)
                gverts, gtris = o.shape.tessellate(TESS_TOLERANCE)
                groups.append(([tuple(v) for v in gverts], gtris, rgb))
    return CaptureMesh(vertices, tris, groups, cap_mesh)


def resolve_highlight(highlight: list | None, features: list) -> tuple | None:
    """Resolve a list of feature names to a highlight overlay mesh (or None
    when no highlight was requested). Raises ``CaptureError`` naming the
    unknown feature(s) and every valid name, so an unknown name is a clean
    error with no partial render output."""
    if not highlight:
        return None
    by_name = {f.name: f for f in features}
    missing = [h for h in highlight if h not in by_name]
    if missing:
        valid = ", ".join(sorted(by_name)) or "(none)"
        raise CaptureError(f"unknown feature(s) {missing}; valid: {valid}")
    hfaces = [fc for h in highlight for fc in (by_name[h].faces or [])]
    hverts, htris = feature_geom.tessellate(hfaces, TESS_TOLERANCE)
    return (hverts, htris) if hverts else None


def resolve_focus(focus, features: list) -> tuple[tuple | None, str | None]:
    """Resolve ``focus`` (a feature name, or an explicit
    [xmin,ymin,zmin,xmax,ymax,zmax] region) to ``(bounds, label)``, or
    ``(None, None)`` when no focus was requested. Raises ``CaptureError`` for
    an unknown feature name, a feature with no geometry, or a malformed
    explicit region."""
    if focus is None:
        return None, None
    if isinstance(focus, str):
        by_name = {f.name: f for f in features}
        rec = by_name.get(focus)
        if rec is None:
            valid = ", ".join(sorted(by_name)) or "(none)"
            raise CaptureError(f"unknown focus feature {focus!r}; valid: {valid}")
        summary = feature_geom.summarize(rec.faces or [])
        if not summary["bbox"]:
            raise CaptureError(f"focus feature {focus!r} has no geometry to frame")
        (cx, cy, cz), (sx, sy, sz) = summary["center"], summary["bbox"]
        bounds = (
            cx - sx / 2,
            cy - sy / 2,
            cz - sz / 2,
            cx + sx / 2,
            cy + sy / 2,
            cz + sz / 2,
        )
        return bounds, focus
    try:
        vals = [float(v) for v in focus]
    except (TypeError, ValueError):
        vals = []
    if len(vals) != 6 or any(vals[k] > vals[k + 3] for k in range(3)):
        raise CaptureError(
            "focus must be a feature name or [xmin, ymin, zmin, xmax, ymax, zmax] with min <= max"
        )
    return tuple(vals), "region"
