"""safe_chamfer / safe_fillet: self-clamping bevels that apply the largest
valid size instead of failing the whole build on a too-large radius.

The regression these guard against: a bevel radius that exceeds ~half the local
wall width makes OpenCascade reject the operation, which build123d surfaces as a
ValueError. On a thin-walled part (the user's 3 mm open-channel bracket) almost
any "bevel the edges" radius fails, and the agent thrashes. safe_* clamp down to
the biggest size that works so the model just builds.
"""

import pytest
from build123d import Align, Axis, Box, BuildPart, Locations, chamfer, fillet

from solidifai import safe_chamfer, safe_fillet


def _thin_wall_channel():
    """Open U-channel with 3 mm walls, the geometry that broke bevels."""
    W, D, H, t = 90.0, 81.0, 23.0, 3.0
    with BuildPart() as bp:
        Box(W, D, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((-W / 2 + t / 2, 0, 0), (W / 2 - t / 2, 0, 0)):
            Box(t, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return bp.part


def test_plain_bevel_really_fails_on_thin_wall():
    """Precondition: the naive radius genuinely fails, so the helper has a job."""
    part = _thin_wall_channel()
    top = part.edges().group_by(Axis.Z)[-1]
    with pytest.raises(ValueError):
        fillet(top, 2.0)
    with pytest.raises(ValueError):
        chamfer(top, 2.0)


def test_safe_fillet_clamps_instead_of_raising():
    part = _thin_wall_channel()
    top = part.edges().group_by(Axis.Z)[-1]
    out = safe_fillet(top, 2.0)  # too large; must not raise
    assert out.is_valid
    assert 0 < out.volume < part.volume  # material was rounded off, part survived


def test_safe_chamfer_clamps_instead_of_raising():
    part = _thin_wall_channel()
    top = part.edges().group_by(Axis.Z)[-1]
    out = safe_chamfer(top, 2.0)
    assert out.is_valid
    assert 0 < out.volume < part.volume


def test_valid_radius_is_applied_exactly():
    """A radius that already fits must be used as-is (no needless shrink)."""
    part = Box(40, 40, 40)
    edges = part.edges().group_by(Axis.Z)[-1]
    exact = fillet(edges, 3.0)
    out = safe_fillet(part.edges().group_by(Axis.Z)[-1], 3.0)
    assert out.volume == pytest.approx(exact.volume, rel=1e-6)


def test_safe_fillet_updates_builder_context():
    """Inside BuildPart, safe_fillet must replace the context part like fillet does."""
    W, D, H, t = 90.0, 81.0, 23.0, 3.0
    with BuildPart() as bp:
        Box(W, D, t, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations((-W / 2 + t / 2, 0, 0), (W / 2 - t / 2, 0, 0)):
            Box(t, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
        before = bp.part.volume
        safe_fillet(bp.edges().group_by(Axis.Z)[-1], 2.0)
    assert bp.part.is_valid
    assert bp.part.volume < before  # context solid actually changed


def test_operates_on_the_edges_own_part_under_a_foreign_context():
    """Regression: a live BuildPart context must not hijack the target. safe_fillet
    must fillet the part the edges belong to, not silently no-op the context part."""
    channel = _thin_wall_channel()
    top = channel.edges().group_by(Axis.Z)[-1]
    with BuildPart():  # unrelated live context
        Box(40, 40, 40)
        out = safe_fillet(top, 1.0)  # edges belong to `channel`, not the cube
    assert out.is_valid
    # the channel got filleted (volume dropped from its own baseline)...
    assert out.volume < channel.volume
    # ...and it is NOT the untouched 40mm cube (vol 64000)
    assert out.volume < 40_000


def test_degrades_to_no_op_when_even_min_fails():
    """If nothing down to min works, return the part unchanged rather than raise."""
    part = Box(40, 40, 40)
    edges = part.edges().group_by(Axis.Z)[-1]
    # min_radius larger than the box can take on all 4 top edges at once
    out = safe_fillet(edges, 30.0, min_radius=25.0)
    assert out.is_valid
    assert out.volume == pytest.approx(part.volume, rel=1e-9)
