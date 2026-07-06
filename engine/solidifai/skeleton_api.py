"""The collector skeleton.py authors call. Holds named scalars + frames the
children consume. A frame is a build123d Location (a rigid placement)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkeletonResult:
    scalars: dict[str, Any] = field(default_factory=dict)
    frames: dict[str, Any] = field(default_factory=dict)  # name -> Location
    shapes: dict[str, Any] = field(
        default_factory=dict
    )  # name -> build123d shape (profile or solid)

    def scalar(self, name: str, value: Any) -> Any:
        self.scalars[name] = value
        return value

    def frame(self, name: str, location: Any) -> Any:
        self.frames[name] = location
        return location

    def profile(self, name: str, shape: Any) -> Any:
        """Publish a 2D profile (Sketch/Face/Wire/Edge) downstream parts consume.
        Rejects geometry with volume -- use shape() to publish a solid."""
        if not _is_shape(shape):
            raise TypeError(
                f"profile({name!r}) needs a build123d shape, got {type(shape).__name__}"
            )
        if _has_volume(shape):
            raise ValueError(
                f"profile({name!r}) got geometry with volume; publish a 2D profile "
                f"(a Sketch/Face/Wire) or use shape() for a solid"
            )
        self.shapes[name] = shape
        return shape

    def shape(self, name: str, shape: Any) -> Any:
        """Publish any build123d shape (including a solid) for downstream parts."""
        if not _is_shape(shape):
            raise TypeError(f"shape({name!r}) needs a build123d shape, got {type(shape).__name__}")
        self.shapes[name] = shape
        return shape

    def resolve_inputs(self, names: list[str]) -> dict[str, Any]:
        out = {}
        for n in names:
            if n not in self.scalars:
                raise KeyError(f"skeleton has no scalar named {n!r} (declared as a child input)")
            out[n] = self.scalars[n]
        return out

    def resolve_shapes(self, names: list[str]) -> dict[str, Any]:
        out = {}
        for n in names:
            if n not in self.shapes:
                raise KeyError(
                    f"skeleton has no shape named {n!r} (declared as a child shape_input)"
                )
            out[n] = self.shapes[n]
        return out

    def frame_for(self, name: str | None):
        if name is None:
            from build123d import Location

            return Location()  # node origin
        if name not in self.frames:
            raise KeyError(f"skeleton has no frame named {name!r} (declared as a child attach)")
        return self.frames[name]


def _is_shape(obj: Any) -> bool:
    """True when obj is a build123d Shape (the base class of Sketch/Face/Wire/
    Edge/Solid/Part/Compound). Lazy import keeps skeleton_api importable without
    build123d for non-CAD callers."""
    try:
        from build123d import Shape
    except Exception:  # noqa: BLE001
        return hasattr(obj, "wrapped") and hasattr(obj, "bounding_box")
    return isinstance(obj, Shape)


def _has_volume(shape: Any) -> bool:
    """True when the shape has any solids (3D). A 2D profile (Sketch/Face/Wire)
    reports zero solids; a Box/Solid/Part reports one or more."""
    solids = getattr(shape, "solids", None)
    if not callable(solids):
        return False
    try:
        return len(solids()) > 0
    except Exception:  # noqa: BLE001 - a non-topology object is not a solid
        return False


def skeleton() -> SkeletonResult:
    return SkeletonResult()
