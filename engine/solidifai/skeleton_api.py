"""The collector skeleton.py authors call. Holds named scalars + frames the
children consume. A frame is a build123d Location (a rigid placement)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Declared joint kinds. This is a DECLARED-INTENT model (motion checking), not a
# constraint solver: placement stays frame-driven; a joint records how a child is
# meant to move so check_motion can sweep it and check_interfaces can validate it.
JOINT_KINDS = ("rigid", "revolute", "slider", "cylindrical", "planar", "ball")
# Kinds that need a motion axis (default +Z when omitted). rigid has no DOF; ball
# rotates freely but we still record an axis for the swept check.
_ROTARY_KINDS = ("revolute", "cylindrical", "ball")
_LINEAR_KINDS = ("slider", "cylindrical", "planar")


@dataclass
class SkeletonResult:
    scalars: dict[str, Any] = field(default_factory=dict)
    frames: dict[str, Any] = field(default_factory=dict)  # name -> Location
    shapes: dict[str, Any] = field(
        default_factory=dict
    )  # name -> build123d shape (profile or solid)
    joints: list[dict[str, Any]] = field(default_factory=list)  # declared joints (see joint())

    def scalar(self, name: str, value: Any) -> Any:
        self.scalars[name] = value
        return value

    def frame(self, name: str, location: Any) -> Any:
        self.frames[name] = location
        return location

    def joint(
        self,
        name: str,
        kind: str,
        frame: str,
        axis: Any = None,
        limits: Any = None,
        between: Any = None,
    ) -> dict[str, Any]:
        """Declare a joint: how one child is meant to move relative to another.

        This is declared intent for motion checking, NOT a constraint solver --
        parts are still placed by their attach frame. ``kind`` is one of rigid,
        revolute, slider, cylindrical, planar, ball. ``frame`` names a published
        frame at the joint location. ``axis`` is a local axis vector (default
        +Z) for kinds that move about/along an axis. ``limits`` is ``[lo, hi]``
        (degrees for rotary kinds, mm for linear kinds). ``between`` optionally
        names the two child ids the joint relates ``[moving, ground]``; check_motion
        sweeps the FIRST id. Validated here so a bad kind/shape fails at authoring."""
        if kind not in JOINT_KINDS:
            raise ValueError(
                f"joint({name!r}) kind {kind!r} must be one of {', '.join(JOINT_KINDS)}"
            )
        if not isinstance(frame, str):
            raise TypeError(f"joint({name!r}) frame must be a published frame name (a string)")
        axis_vec = _validate_axis(name, axis)
        limits_pair = _validate_limits(name, limits)
        between_ids = _validate_between(name, between)
        rec = {
            "name": name,
            "kind": kind,
            "frame": frame,
            "axis": axis_vec,
            "limits": limits_pair,
            "between": between_ids,
        }
        self.joints.append(rec)
        return rec

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


def _validate_axis(name: str, axis: Any) -> list[float]:
    """A 3-number axis vector; default +Z. Rejected: wrong length, non-numeric, or
    a zero vector (no direction to sweep)."""
    if axis is None:
        return [0.0, 0.0, 1.0]
    try:
        vec = [float(v) for v in axis]
    except (TypeError, ValueError) as exc:
        raise TypeError(f"joint({name!r}) axis must be three numbers [x, y, z]") from exc
    if len(vec) != 3:
        raise ValueError(f"joint({name!r}) axis must have exactly three components")
    if vec == [0.0, 0.0, 0.0]:
        raise ValueError(f"joint({name!r}) axis must be a non-zero vector")
    return vec


def _validate_limits(name: str, limits: Any) -> list[float] | None:
    """Optional ``[lo, hi]`` travel bounds (degrees for rotary, mm for linear),
    with lo <= hi. None means unbounded (the caller supplies a range)."""
    if limits is None:
        return None
    try:
        lo, hi = (float(v) for v in limits)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"joint({name!r}) limits must be a pair [lo, hi]") from exc
    if lo > hi:
        raise ValueError(f"joint({name!r}) limits lo ({lo}) must be <= hi ({hi})")
    return [lo, hi]


def _validate_between(name: str, between: Any) -> list[str] | None:
    """Optional pair of child ids the joint relates ``[moving, ground]``."""
    if between is None:
        return None
    ids = list(between)
    if len(ids) != 2 or not all(isinstance(b, str) for b in ids):
        raise ValueError(f"joint({name!r}) between must be two child ids [moving, ground]")
    return ids


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
