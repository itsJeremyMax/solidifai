import math

from build123d import Box, BuildPart, Hole, Pos

import solidifai_engine.props as props_mod
from solidifai_engine.props import mass_grams, properties


def _box_with_hole():
    with BuildPart() as bp:
        Box(20, 20, 20)
        Hole(radius=2.5)
    return bp.part


def test_properties_returns_geometry_only():
    shape = _box_with_hole()
    props = properties(shape)

    size = props["bbox"]["size"]
    assert len(size) == 3
    for got, want in zip(size, (20.0, 20.0, 20.0), strict=True):
        assert abs(got - want) < 1e-4

    assert "min" in props["bbox"]
    assert "max" in props["bbox"]
    assert 7000 < props["volume"] < 8000
    assert props["manifold"] is True
    assert props["valid"] is True
    assert len(props["centerOfMass"]) == 3

    # mass is no longer part of properties(); it is assembled per-object in render.
    assert "mass" not in props


def test_mass_grams_formula():
    # 8000 mm^3 of PLA (1.24 g/cm^3) = 8000 * 1.24 / 1000 = 9.92 g
    assert mass_grams(8000.0, 1.24) == 9.92
    assert mass_grams(0.0, 7.85) == 0.0


# --- mass_properties: exact inertia, validated against closed form -----------


def test_mass_properties_box_matches_closed_form():
    # 20 x 10 x 6 mm box, PLA-ish density 1.24 g/cm^3, centered at origin.
    w, d, h, rho = 20.0, 10.0, 6.0, 1.24
    mp = props_mod.mass_properties(Box(w, d, h), rho)

    vol = w * d * h
    assert mp["volume"] == round(vol, 4)
    assert math.isclose(mp["mass"], vol * rho / 1000.0, rel_tol=1e-6)
    assert math.isclose(mp["surfaceArea"], 2 * (w * d + w * h + d * h), rel_tol=1e-4)
    assert all(abs(c) < 1e-6 for c in mp["centerOfMass"])  # centered

    m = vol * rho / 1000.0
    ixx = m / 12.0 * (d * d + h * h)
    iyy = m / 12.0 * (w * w + h * h)
    izz = m / 12.0 * (w * w + d * d)
    pm = sorted(mp["inertia"]["principalMoments"])
    for got, exp in zip(pm, sorted([ixx, iyy, izz]), strict=True):
        assert math.isclose(got, exp, rel_tol=1e-3), (got, exp)


def test_mass_properties_tensor_is_about_com_not_origin():
    # A tensor about the ORIGIN would be huge for an offset box; about the CoM it
    # must equal the centered-box tensor.
    w, d, h, rho = 20.0, 10.0, 6.0, 1.0
    centered = props_mod.mass_properties(Box(w, d, h), rho)
    offset = props_mod.mass_properties(Pos(100, 50, 30) * Box(w, d, h), rho)
    assert offset["centerOfMass"] == [100.0, 50.0, 30.0]
    for a, b in zip(
        sorted(offset["inertia"]["principalMoments"]),
        sorted(centered["inertia"]["principalMoments"]),
        strict=True,
    ):
        assert math.isclose(a, b, rel_tol=1e-3)


def test_aggregate_two_boxes_parallel_axis():
    # Two equal boxes offset on X: total mass sums, CoM at the midpoint (origin).
    rho = 2.0
    a = props_mod.mass_properties(Pos(-10, 0, 0) * Box(4, 4, 4), rho)
    b = props_mod.mass_properties(Pos(10, 0, 0) * Box(4, 4, 4), rho)
    tot = props_mod.aggregate([a, b])
    assert math.isclose(tot["mass"], a["mass"] + b["mass"], rel_tol=1e-9)
    assert all(abs(c) < 1e-6 for c in tot["centerOfMass"])
    assert math.isclose(tot["volume"], a["volume"] + b["volume"], rel_tol=1e-9)
    # Combined Izz: each box about its own CoM plus m*dx^2 (parallel axis).
    m = a["mass"]
    izz_each = m / 12.0 * (4.0**2 + 4.0**2)
    izz_expected = 2 * (izz_each + m * 10.0**2)
    assert math.isclose(max(tot["inertia"]["principalMoments"]), izz_expected, rel_tol=1e-3)
