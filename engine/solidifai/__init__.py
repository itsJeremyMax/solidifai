"""User-facing helper package for solidifai scripts.

User scripts call ``from solidifai import show`` to register objects that the
engine then tessellates, measures and renders. The registry lives on an active
build scope (a contextvar): with no scope active, calls hit a default root scope
that behaves like the old module-level list. ``build_scope()`` runs a build in an
isolated scope so per-node builds (assemblies) stay side-effect free. Scripts may
also ``from solidifai import feature`` to declare named, targetable features
inside ``build()``.
"""

from __future__ import annotations

import contextvars
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from . import hardware, std
from .bevel import safe_chamfer, safe_fillet
from .imports import import_cad, set_workspace_root
from .skeleton_api import SkeletonResult, skeleton

__all__ = [
    "show",
    "reset_registry",
    "_registry",
    "ShownObject",
    "feature",
    "FeatureRecord",
    "_feature_registry",
    "build_scope",
    "exploded",
    "import_cad",
    "set_workspace_root",
    "hardware",
    "std",
    "safe_chamfer",
    "safe_fillet",
    "skeleton",
    "SkeletonResult",
    "_record_asset",
]


@dataclass
class ShownObject:
    name: str
    shape: Any
    color: tuple | None
    material: str | None = None
    # "part" = your designed geometry (exported, DFM'd); "reference" = an imported
    # fixture you fit around (ghosted, never exported, not DFM'd).
    role: str = "part"
    # Set by the import manager on references it added from the imports manifest,
    # so a later refresh sweeps only those (not script-shown references). Excluded
    # from eq/repr to keep object comparisons unchanged.
    _from_manifest: bool = field(default=False, compare=False, repr=False)


@dataclass
class _Scope:
    objects: list[ShownObject] = field(default_factory=list)
    features: list[FeatureRecord] = field(default_factory=list)
    assets: list[str] = field(default_factory=list)


# The root scope preserves today's module-global behavior for every call site
# that runs without an explicit build_scope() (existing single-model builds, tests).
_ROOT_SCOPE = _Scope()
_ACTIVE_SCOPE: contextvars.ContextVar[_Scope] = contextvars.ContextVar(
    "solidifai_active_scope", default=_ROOT_SCOPE
)


def _current_scope() -> _Scope:
    return _ACTIVE_SCOPE.get()


@contextmanager
def build_scope():
    """Run a build in an isolated registry. show()/feature() inside the block
    write only to this scope; the root scope and any outer scope are untouched.
    This is what makes a node build a pure, side-effect-free function."""
    scope = _Scope()
    token = _ACTIVE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _ACTIVE_SCOPE.reset(token)


def _record_asset(path: str) -> None:
    """Record an asset path read during the active build, so the cache can
    invalidate a cached part when its referenced asset changes."""
    _current_scope().assets.append(path)


def reset_registry() -> None:
    scope = _current_scope()
    scope.objects.clear()
    scope.features.clear()
    scope.assets.clear()


def _registry() -> list[ShownObject]:
    return _current_scope().objects


@dataclass
class FeatureRecord:
    """A named, targetable feature declared inside build() via ``feature()``.

    Metadata fields (``name``, ``kind``, ``driven_by``, ``source_line``) are
    always populated. Geometry fields (``metrics``/``center``/``bbox``) and
    inference fields start at ``None``; the engine fills them in after
    tessellation.
    """

    name: str
    kind: str | None = None
    driven_by: list = field(default_factory=list)
    source_line: int | None = None
    # In assembly mode, the owning child path ("pin" or "hinge/pin"); None for a
    # single-model feature. The addressable name is namespaced ("<part>/<name>").
    part: str | None = None
    # Raw build123d faces this block created (set-diff capture); never serialized,
    # interpreted engine-side. Empty when there is no active builder.
    faces: list = field(default_factory=list)
    # Engine-side tessellation cache (lazy; not serialized). Naturally per-build
    # because records are re-created on each successful build.
    _tess_cache: Any = None
    # Set by the engine after tessellation (None until the build completes):
    metrics: dict | None = None
    center: list | None = None
    bbox: list | None = None
    # Automatic inference fields — unset for explicitly declared features:
    inferred: bool = False
    confidence: float | None = None


def _feature_registry() -> list[FeatureRecord]:
    return _current_scope().features


class feature:
    """Declare a named, targetable feature for the geometry built inside it.

    Used inside ``build()`` (or any script) wrapping the operation(s) that
    produce a feature, so tools can map it back to the source and its driving
    parameter::

        with feature("central_bore", driven_by="bore_dia"):
            with Locations((0, 0)):
                Hole(radius=bore_dia / 2)

    Records ``name``, ``kind``, ``driven_by`` and the source line without
    touching build123d or altering geometry. A block that raises is NOT
    recorded and the exception propagates (the build fails as usual).
    """

    def __init__(
        self,
        name: str,
        *,
        driven_by: str | list | None = None,
        kind: str | None = None,
    ):
        self.name = name
        self.kind = kind
        if driven_by is None:
            self.driven_by: list = []
        elif isinstance(driven_by, str):
            self.driven_by = [driven_by]
        else:
            self.driven_by = list(driven_by)
        self.source_line: int | None = None

    def __enter__(self) -> feature:
        self.source_line = sys._getframe(1).f_lineno
        # Lazy build123d import: keep `import solidifai` light, and degrade
        # gracefully when there is no active builder (feature used loosely).
        # build123d's Builder is untyped, so these hold Any-or-None.
        self._builder: Any = None
        self._faces_before: set | None = None
        self._solid_before: Any = None
        try:
            from build123d import Builder

            ctx: Any = Builder._get_context()
            if ctx is not None:
                self._builder = ctx
                self._faces_before = set(ctx.faces())
                self._solid_before = ctx.part
        except Exception:  # noqa: BLE001 - capture is best-effort, never fatal
            self._builder = None
            self._faces_before = None
            self._solid_before = None
        return self

    def _set_diff_faces(self) -> list:
        """Fallback face capture: faces present after the block but not before.

        Best-effort; returns ``[]`` rather than ever raising.
        """
        if self._builder is None or self._faces_before is None:
            return []
        try:
            return list(set(self._builder.faces()) - self._faces_before)
        except Exception:  # noqa: BLE001 - never fail the build on capture
            return []

    @staticmethod
    def _same_surface(fa, fb) -> bool:
        """True when two faces lie on the same underlying surface.

        Used to tell a genuinely-new feature surface (a hole wall, a fillet
        round) apart from a face that merely inherited a pre-existing surface
        (the plate face a hole punched through, which is a *new* topological face
        on the same plane). Handles the two surfaces blends/holes create — planes
        and cylinders; any other pair is treated as distinct (best-effort)."""
        try:
            ta, tb = str(fa.geom_type), str(fb.geom_type)
            if ta != tb:
                return False
            if "PLANE" in ta:
                na, nb = fa.normal_at(), fb.normal_at()
                if abs(na.dot(nb)) < 0.999:  # not parallel
                    return False
                pa, pb = fa.position_at(0.5, 0.5), fb.position_at(0.5, 0.5)
                return abs((pa - pb).dot(nb)) < 1e-6  # same offset
            if "CYLINDER" in ta:
                aa, ab = fa.axis_of_rotation, fb.axis_of_rotation
                if aa is None or ab is None or abs(fa.radius - fb.radius) > 1e-6:
                    return False
                if abs(aa.direction.dot(ab.direction)) < 0.999:  # axes not parallel
                    return False
                d = aa.position - ab.position
                perp = d - ab.direction * d.dot(ab.direction)
                return perp.length < 1e-6  # axes collinear
            return False
        except Exception:  # noqa: BLE001 - coincidence test is best-effort
            return False

    def _novel_after_faces(self) -> list:
        """After-block faces whose surface did not exist before the block.

        These are the actual new feature surfaces (a hole wall, a fillet's
        rounded surface) with re-faced pre-existing surfaces (the plate a hole
        went through) filtered out. This makes a blend's rounded surface
        directly targetable by feature_at even when the removed-material sliver
        lies off the true surface. Best-effort; returns ``[]`` on any problem."""
        if self._builder is None or self._faces_before is None:
            return []
        try:
            before = self._faces_before
            new_faces = set(self._builder.faces()) - before
            return [f for f in new_faces if not any(self._same_surface(f, b) for b in before)]
        except Exception:  # noqa: BLE001 - never fail the build on capture
            return []

    @staticmethod
    def _union_faces(a, b) -> list:
        """Concatenate two face lists, dropping identity duplicates, order stable."""
        seen: set = set()
        out: list = []
        for f in list(a) + list(b):
            if id(f) not in seen:
                seen.add(id(f))
                out.append(f)
        return out

    def _capture_faces(self) -> list:
        """Capture the faces this feature block created.

        Prefers a boolean delta against the pre-block solid so a subtractive op
        (e.g. ``Hole``) yields just the removed plug (wall + caps) and an
        additive op yields just the added body — instead of the set-diff, which
        also picks up the whole punched plate faces. The delta is unioned with
        the block's genuinely-new after-faces (``_novel_after_faces``) so a
        blend's rounded surface is captured even though the removed sliver sits
        up to a radius off it; the novel set excludes re-faced flats, so a hole's
        plug still summarizes to the hole (not the whole plate). Falls back to
        the set-diff, then ``[]``; never raises.
        """
        try:
            novel = self._novel_after_faces()
            if self._solid_before is not None:
                after = self._builder.part
                # Subtractive: the material removed (the plug — wall + caps).
                try:
                    removed = self._solid_before - after
                    if removed is not None and removed.volume > 1e-6:
                        return self._union_faces(removed.faces(), novel)
                except Exception:  # noqa: BLE001 - try the additive branch next
                    pass
                # Additive: the material added (the new body).
                try:
                    added = after - self._solid_before
                    if added is not None and added.volume > 1e-6:
                        return self._union_faces(added.faces(), novel)
                except Exception:  # noqa: BLE001 - fall back below
                    pass
            # No before-solid, or neither delta had volume: prefer the novel
            # surfaces, else the set-diff.
            return novel or self._set_diff_faces()
        except Exception:  # noqa: BLE001 - never fail the build on capture
            return self._set_diff_faces()

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        if exc_type is None:
            faces = self._capture_faces()
            _current_scope().features.append(
                FeatureRecord(
                    name=self.name,
                    kind=self.kind,
                    driven_by=list(self.driven_by),
                    source_line=self.source_line,
                    faces=faces,
                )
            )
        return False


def show(
    shape: Any,
    name: str | None = None,
    color: tuple | None = None,
    material: str | None = None,
    role: str = "part",
) -> ShownObject:
    """Register ``shape`` for rendering.

    ``material`` names an entry in the material library (default ``"pla"`` at
    render time); ``color`` overrides that material's base color. If ``name`` is
    not given, objects are auto-named ``object_1``, ``object_2``, and so on.
    ``role`` is ``"part"`` for designed geometry (exported, DFM-checked) or
    ``"reference"`` for an imported fixture you fit around (ghosted, not exported).
    """
    scope = _current_scope()
    if name is None:
        name = f"object_{len(scope.objects) + 1}"
    obj = ShownObject(name=name, shape=shape, color=color, material=material, role=role)
    scope.objects.append(obj)
    return obj


def exploded(shapes: list[Any], factor: float, *, spread: float = 0.6) -> list[Any]:
    """Translate parts radially outward from the assembly centroid for an
    exploded view.

    This is the engine-internal spread behind ``capture_views(explode=...)``:
    the agent asks for an exploded capture and the engine routes the shown parts
    through here for that render only, never mutating the saved model. Scripts
    do **not** call this directly and must not add an ``explode`` parameter —
    exploded view is a render-time / viewport concern, not model geometry.

    ``shapes`` is a list of build123d parts (the assembly); ``factor`` is the
    spread amount 0..100 (a percentage). At ``factor=100`` the outward offset
    distance equals ``spread`` times the assembly's bounding-box diagonal.
    Values above 100 are accepted and scale proportionally beyond the
    spread×diagonal maximum. Returns a NEW list of translated shapes in the same
    order; the inputs are never mutated.

    Returned unchanged: ``factor <= 0``; an empty or single-element list; and
    any part whose center coincides with the assembly center (concentric — a
    documented limitation, move such parts explicitly instead).
    """
    parts = list(shapes)
    if factor <= 0 or len(parts) <= 1:
        return parts

    boxes = [s.bounding_box() for s in parts]
    min_x = min(b.min.X for b in boxes)
    min_y = min(b.min.Y for b in boxes)
    min_z = min(b.min.Z for b in boxes)
    max_x = max(b.max.X for b in boxes)
    max_y = max(b.max.Y for b in boxes)
    max_z = max(b.max.Z for b in boxes)
    cx, cy, cz = (min_x + max_x) / 2, (min_y + max_y) / 2, (min_z + max_z) / 2
    diagonal = ((max_x - min_x) ** 2 + (max_y - min_y) ** 2 + (max_z - min_z) ** 2) ** 0.5
    offset = (factor / 100.0) * spread * diagonal
    eps = 1e-6 * max(diagonal, 1.0)

    out = []
    for shape, box in zip(parts, boxes, strict=True):
        c = box.center()
        dx, dy, dz = c.X - cx, c.Y - cy, c.Z - cz
        length = (dx * dx + dy * dy + dz * dz) ** 0.5
        if length < eps:
            out.append(shape)  # concentric with the assembly center: leave in place
        else:
            k = offset / length
            out.append(shape.translate((dx * k, dy * k, dz * k)))
    return out
