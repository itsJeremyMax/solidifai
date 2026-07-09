"""Self-clamping bevels: ``safe_fillet`` / ``safe_chamfer``.

A fillet or chamfer whose size exceeds ~half the local wall width makes the
kernel reject the whole operation (build123d raises ``ValueError``). On a
thin-walled part almost any "bevel the edges" size fails, so a naive retry loop
thrashes. These helpers instead apply the *largest* size the geometry accepts,
up to the size you asked for, and never raise on a too-large size:

    from solidifai import show, safe_fillet
    with BuildPart() as p:
        Box(90, 81, 3)
        ...
        safe_fillet(p.edges().group_by(Axis.Z)[-1], 2.0)  # clamps to what fits
    show(p.part, name="bracket")

Drop-in for build123d's ``fillet`` / ``chamfer``: same first two arguments,
same builder-context behavior (the context part is replaced), same return value
(the new ``Part``). If even ``min_radius`` / ``min_length`` will not take, the
part is returned unchanged rather than failing the build.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

_SEARCH_ITERS = 14  # binary-search steps; ~0.06 mm resolution over a 1 mm span

_LOG = logging.getLogger(__name__)


def _bevel_errors() -> tuple[type[BaseException], ...]:
    """The exceptions a rejected bevel raises: build123d's ValueError plus the
    raw kernel failure, in case a code path surfaces it directly."""
    errs: list[type[BaseException]] = [ValueError, RuntimeError]
    try:
        from OCP.Standard import Standard_Failure

        errs.append(Standard_Failure)
    except Exception:  # noqa: BLE001 - OCP always present with build123d; be safe anyway
        pass
    return tuple(errs)


def _edge_list(objects: Any) -> list:
    """Materialize ``objects`` (a single edge, a ShapeList, or any iterable) to
    a list, so it can be reused across search trials and the final apply."""
    if objects is None:
        return []
    try:
        return list(objects)
    except TypeError:
        return [objects]


def _noop_on_empty(objects: Any, op: str) -> Any:
    """No-op result for an empty edge selection (a ``filter_by`` that matched
    nothing) -- common enough that failing the build would violate this module's
    never-raise contract, and build123d itself raises a raw IndexError here. Warn,
    then return the active builder context part when one is live (so ``bp.part``
    stays unchanged and valid), else the caller's ``objects`` unchanged."""
    from build123d import Builder

    _LOG.warning("safe_%s: empty edge selection, skipping bevel (no-op)", op)
    ctx: Any = Builder._get_context(None)
    return ctx._obj if ctx is not None else objects


def _resolve_target(edges: list) -> Any:
    """The solid the ``edges`` actually belong to.

    Use the edges' own ``topo_parent`` (set in both builder and algebra mode), not
    the active builder context: probing must run against the solid that owns these
    edges, or a foreign-edge mismatch would be mis-read as "radius too large" and
    silently clamped to a no-op on the wrong part. Falls back to the active context
    only when an edge has no parent recorded. A ``BasePartObject`` (a bare ``Box``)
    is re-wrapped as a plain ``Part`` exactly as build123d's own op does, so its
    ``fillet``/``chamfer`` does not try to reconstruct the primitive from a shape.

    Edges spanning more than one solid have no single target: beveling only the
    first (as ``edges[0]`` implies) silently drops the rest, so raise instead."""
    from build123d import BasePartObject, Builder, Part

    parents = {id(e.topo_parent): e.topo_parent for e in edges if e.topo_parent is not None}
    if len(parents) > 1:
        raise ValueError(
            "edges belong to multiple solids; call safe_fillet/safe_chamfer once per solid"
        )
    target = edges[0].topo_parent
    if target is None:
        ctx: Any = Builder._get_context(None)
        target = ctx._obj if ctx is not None else None
    if isinstance(target, BasePartObject):
        target = Part(target.wrapped)
    return target


def _largest_ok(trial: Callable[[float], Any], requested: float, minimum: float) -> float | None:
    """Return the largest value in ``[minimum, requested]`` for which ``trial``
    does not raise, or ``None`` if even ``minimum`` fails. ``trial`` must be pure
    (no side effects) so probing does not mutate the model."""
    errs = _bevel_errors()

    def ok(v: float) -> bool:
        try:
            trial(v)
            return True
        except errs:
            return False

    if requested <= minimum:
        return requested if ok(requested) else None
    if ok(requested):  # fast path: the asked-for size already fits
        return requested
    if not ok(minimum):  # nothing works, not even the floor
        return None
    lo, hi, best = minimum, requested, minimum
    for _ in range(_SEARCH_ITERS):
        mid = (lo + hi) / 2.0
        if ok(mid):
            best, lo = mid, mid
        else:
            hi = mid
    return best


def _apply(via_context: Callable[[], Any], via_target: Callable[[], Any]) -> Any:
    """Apply the bevel. Prefer the public op (``via_context``), which updates the
    active BuildPart context so ``bp.part`` reflects the bevel. If that raises --
    the active context does not own these edges (a foreign-context call) -- apply
    the bevel purely against the edges' own solid and return it, leaving the
    context untouched. Both routes use a size already proven to succeed."""
    try:
        return via_context()
    except _bevel_errors():
        return via_target()


def safe_fillet(objects: Any, radius: float, *, min_radius: float = 0.1) -> Any:
    """Fillet ``objects`` with the largest radius that fits, up to ``radius``.

    Never raises on a too-large ``radius``; clamps down to what the geometry
    accepts (never below ``min_radius``). If not even ``min_radius`` fits, the
    part is returned unchanged.
    """
    from build123d import fillet

    edges = _edge_list(objects)
    if not edges:
        return _noop_on_empty(objects, "fillet")
    target = _resolve_target(edges)
    if target is None:
        return objects  # edges own no solid and no active part: nothing to bevel
    best = _largest_ok(lambda r: target.fillet(r, edges), radius, min_radius)
    if best is None:
        return target  # degrade to a no-op rather than fail the build
    return _apply(lambda: fillet(edges, best), lambda: target.fillet(best, edges))


def safe_chamfer(
    objects: Any,
    length: float,
    length2: float | None = None,
    *,
    min_length: float = 0.1,
) -> Any:
    """Chamfer ``objects`` with the largest length that fits, up to ``length``.

    Never raises on a too-large ``length``; clamps down to what the geometry
    accepts (never below ``min_length``). ``length2`` (asymmetric chamfer) is
    scaled with the clamp so the ratio you asked for is preserved. If not even
    ``min_length`` fits, the part is returned unchanged.
    """
    from build123d import chamfer

    edges = _edge_list(objects)
    if not edges:
        return _noop_on_empty(objects, "chamfer")
    target = _resolve_target(edges)
    if target is None:
        return objects  # edges own no solid and no active part: nothing to bevel
    ratio = (length2 / length) if (length2 is not None and length) else None

    def trial(v: float) -> Any:
        return target.chamfer(v, (v * ratio) if ratio is not None else None, edges)

    best = _largest_ok(trial, length, min_length)
    if best is None:
        return target
    l2 = (best * ratio) if ratio is not None else None
    return _apply(lambda: chamfer(edges, best, l2), lambda: target.chamfer(best, l2, edges))
