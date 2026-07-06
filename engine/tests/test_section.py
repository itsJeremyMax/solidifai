"""Pure-geometry tests for the section plane-cut: no VTK, no offscreen GL."""

import pytest
from build123d import Box, Pos

from solidifai_engine import section


def _hollow_box():
    # 40x40x20 closed hollow box with 3 mm walls (cavity 34x34x14), centered.
    return Box(40, 40, 20) - Box(34, 34, 14)


def test_cut_removes_positive_half_and_keeps_original():
    shape = _hollow_box()
    v0 = shape.volume
    cut_shapes, caps = section.cut_with_caps([shape], "z", 0.0)
    assert len(cut_shapes) == 1
    # Bottom half kept: 40*40*10 - 34*34*7 = 7908 mm^3 (the part is z-symmetric).
    assert cut_shapes[0].volume == pytest.approx(7908.0, rel=0.01)
    # NON-DESTRUCTIVE: the input shape is untouched.
    assert shape.volume == pytest.approx(v0, rel=1e-9)


def test_cap_faces_lie_on_plane_with_expected_area():
    cut_shapes, caps = section.cut_with_caps([_hollow_box()], "z", 0.0)
    assert caps, "the cut through the cavity must expose cap faces"
    # The exposed ring: 40*40 - 34*34 = 444 mm^2 total.
    assert sum(f.area for f in caps) == pytest.approx(444.0, rel=0.01)
    for f in caps:
        assert abs(f.center().Z - 0.0) < 1e-3


def test_cut_through_solid_region_has_full_cap():
    # Cut below the cavity floor (cavity spans z -7..7): solid 40x40 slab cap.
    cut_shapes, caps = section.cut_with_caps([_hollow_box()], "z", -8.0)
    assert sum(f.area for f in caps) == pytest.approx(1600.0, rel=0.01)


def test_axis_validated():
    with pytest.raises(ValueError) as exc:
        section.cut_with_caps([_hollow_box()], "w", 0.0)
    assert "w" in str(exc.value) and "x" in str(exc.value)


def test_offset_outside_model_is_an_error():
    with pytest.raises(ValueError) as exc:
        section.cut_with_caps([_hollow_box()], "z", 25.0)
    msg = str(exc.value)
    assert "25" in msg and "z" in msg  # names the axis + the model's span


def test_multi_shape_cut_keeps_alignment():
    a = Box(10, 10, 10)  # straddles z=0 -> gets cut
    b = Pos(30, 0, -20) * Box(10, 10, 10)  # entirely below -> kept whole
    cut_shapes, caps = section.cut_with_caps([a, b], "z", 0.0)
    assert len(cut_shapes) == 2
    assert cut_shapes[0].volume == pytest.approx(500.0, rel=0.01)
    assert cut_shapes[1].volume == pytest.approx(1000.0, rel=0.01)
