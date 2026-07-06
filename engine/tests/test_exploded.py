import pytest
from build123d import Box, Pos

from solidifai import exploded


def _center(shape):
    c = shape.bounding_box().center()
    return (c.X, c.Y, c.Z)


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def test_factor_zero_is_identity():
    a = Box(20, 20, 10)  # center (0, 0, 0)
    b = Pos(0, 0, 20) * Box(20, 20, 10)  # center (0, 0, 20)
    out = exploded([a, b], 0)
    assert _center(out[0]) == pytest.approx(_center(a))
    assert _center(out[1]) == pytest.approx(_center(b))


def test_single_part_unchanged_at_any_factor():
    a = Box(20, 20, 10)
    out = exploded([a], 100)
    assert len(out) == 1
    assert _center(out[0]) == pytest.approx(_center(a))


def test_empty_list_returns_empty():
    assert exploded([], 50) == []


def test_separation_increases_with_factor():
    a = Box(20, 20, 10)
    b = Pos(0, 0, 20) * Box(20, 20, 10)
    gap0 = _dist(*[_center(s) for s in exploded([a, b], 0)])
    gap50 = _dist(*[_center(s) for s in exploded([a, b], 50)])
    gap100 = _dist(*[_center(s) for s in exploded([a, b], 100)])
    assert gap0 < gap50 < gap100


def test_order_preserved():
    a = Box(20, 20, 10)  # lower
    b = Pos(0, 0, 20) * Box(20, 20, 10)  # upper
    out = exploded([a, b], 100)
    # out[0] is the lower part, out[1] the upper part, after spreading.
    assert _center(out[0])[2] < _center(out[1])[2]


def test_parts_move_away_from_assembly_center():
    a = Box(20, 20, 10)  # center z = 0
    b = Pos(0, 0, 20) * Box(20, 20, 10)  # center z = 20
    ins = [a, b]
    outs = exploded(ins, 100)
    center_z = 10.0  # combined bbox spans z -5..25 -> center z = 10
    for s_in, s_out in zip(ins, outs, strict=True):
        disp_z = _center(s_out)[2] - _center(s_in)[2]
        dir_z = _center(s_in)[2] - center_z
        assert disp_z * dir_z > 0  # displacement strictly opposes center displacement


def test_concentric_parts_not_moved():
    # Two boxes sharing the assembly center: zero offset, no error (documented limit).
    inner = Box(10, 10, 10)
    outer = Box(20, 20, 20)
    out = exploded([inner, outer], 100)
    assert _center(out[0]) == pytest.approx((0, 0, 0))
    assert _center(out[1]) == pytest.approx((0, 0, 0))


def test_inputs_not_mutated():
    a = Box(20, 20, 10)
    b = Pos(0, 0, 20) * Box(20, 20, 10)
    before = [_center(a), _center(b)]
    exploded([a, b], 100)
    assert _center(a) == pytest.approx(before[0])
    assert _center(b) == pytest.approx(before[1])


def test_3d_diagonal_spread():
    a = Pos(20, 20, 10) * Box(10, 10, 10)
    b = Pos(-20, -20, -10) * Box(10, 10, 10)
    out = exploded([a, b], 100)
    ca, cb = _center(out[0]), _center(out[1])
    assert ca[0] > _center(a)[0] and ca[1] > _center(a)[1] and ca[2] > _center(a)[2]
    assert cb[0] < _center(b)[0] and cb[1] < _center(b)[1] and cb[2] < _center(b)[2]
