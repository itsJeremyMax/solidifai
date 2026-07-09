"""Standard ISO metric hardware: dimensions to spec, manifold parts, right bores."""

import math

import pytest
from build123d import Box

from solidifai import hardware


def test_dims_m3():
    d = hardware.dims("M3")
    assert math.isclose(d["head_dia"], 5.5, abs_tol=0.01)
    assert math.isclose(d["head_height"], 3.0, abs_tol=0.01)
    assert math.isclose(d["clearance_medium"], 3.4, abs_tol=0.01)
    assert math.isclose(d["nut_width"], 5.5, abs_tol=0.01)


def test_socket_head_screw_envelope():
    s = hardware.socket_head_cap_screw("M3", 12)
    bb = s.bounding_box()
    assert s.is_manifold
    assert math.isclose(bb.size.X, 5.5, abs_tol=0.2)  # head dia dominates
    assert math.isclose(bb.size.Z, 12 + 3.0, abs_tol=0.2)  # length + head height


def test_clearance_hole_diameter():
    plate = Box(20, 20, 5)
    bored = plate - hardware.clearance_hole("M3", depth=5)
    drop = plate.volume - bored.volume
    assert math.isclose(drop, math.pi * (3.4 / 2) ** 2 * 5, rel_tol=0.05)


def test_hex_nut_across_flats():
    n = hardware.hex_nut("M3")
    bb = n.bounding_box()
    assert n.is_manifold
    assert math.isclose(min(bb.size.X, bb.size.Y), 5.5, abs_tol=0.2)


def test_washer_outer_diameter():
    w = hardware.washer("M3")
    bb = w.bounding_box()
    assert w.is_manifold
    assert math.isclose(bb.size.X, 7.0, abs_tol=0.2)


def test_unknown_size_raises():
    with pytest.raises(ValueError):
        hardware.dims("M99")


def test_table_is_single_homed_on_standards():
    from solidifai_engine import standards

    for size in hardware.sizes():
        d = hardware.dims(size)
        assert d["head_dia"] == standards.screw(size, head="cap")["head_dia"]
        assert d["clearance_medium"] == standards.ISO273_CLEARANCE[size]["medium"]
        assert d["nut_thickness"] == standards.nut(size)["thickness"]


def test_nut_thickness_corrected_to_iso4032():
    assert hardware.dims("M5")["nut_thickness"] == 4.7
    assert hardware.dims("M6")["nut_thickness"] == 5.2
    assert hardware.dims("M8")["nut_thickness"] == 6.8


def test_clearance_hole_close_and_coarse_are_iso273():
    # Same removed-volume technique as test_clearance_hole_diameter above.
    for fit, dia in (("close", 3.2), ("coarse", 3.6)):
        plate = Box(20, 20, 5) - hardware.clearance_hole("M3", depth=5, fit=fit)
        removed = 20 * 20 * 5 - plate.volume
        assert math.isclose(removed, math.pi * (dia / 2) ** 2 * 5, rel_tol=0.05), fit


def test_counterbore_cuts_a_stepped_head_pocket():
    """Subtracting counterbore() from a top-referenced plate must leave a wide
    head recess above the clearance bore, not a plain hole (recess-direction
    regression)."""
    from build123d import Align

    plate = Box(30, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MAX))  # top at Z=0
    removed = plate.volume - (plate - hardware.counterbore("M6", depth=8)).volume
    t = hardware.dims("M6")
    plain_bore = math.pi * (t["clearance_medium"] / 2) ** 2 * 8
    # the stepped pocket removes clearly more than a plain bore of the same depth
    assert removed > plain_bore * 1.3


def test_counterbore_bore_follows_the_profile_fit():
    """The counterbore bore must resolve the manufacturing profile's fit like
    clearance_hole does, not hardcode the medium series. A tighter profile shrinks
    the bore diameter; the default normal fit keeps the historical medium bore."""
    from build123d import Align, Cylinder

    from solidifai_engine import manufacturing_profile

    top = (Align.CENTER, Align.CENTER, Align.MAX)

    def removed_under_fit(fit_profile):
        orig = manufacturing_profile.builtin_defaults
        manufacturing_profile.builtin_defaults = lambda: {"design": {"fit": fit_profile}}
        try:
            plate = Box(30, 30, 10, align=top)  # top face at Z=0
            return plate.volume - (plate - hardware.counterbore("M6", depth=8)).volume
        finally:
            manufacturing_profile.builtin_defaults = orig

    # A tight profile (close series) removes strictly less than the normal (medium).
    assert removed_under_fit("tight") < removed_under_fit("normal")

    # Default normal fit is byte-for-byte the old medium-bore counterbore: build the
    # reference cutter the same way counterbore does and compare removed volumes.
    t = hardware.dims("M6")
    ref_bore = Cylinder(t["clearance_medium"] / 2, 8, align=top)
    ref_recess = Cylinder(t["head_dia"] / 2 + 0.2, t["head_height"] + 0.2, align=top)
    ref = ref_bore + ref_recess
    plate_a = Box(30, 30, 10, align=top)
    plate_b = Box(30, 30, 10, align=top)
    removed_default = plate_a.volume - (plate_a - hardware.counterbore("M6", depth=8)).volume
    removed_ref = plate_b.volume - (plate_b - ref).volume
    assert math.isclose(removed_default, removed_ref, rel_tol=1e-6)


def test_counterbore_rejects_depth_shallower_than_head():
    """A counterbore shallower than the head recess would overshoot the bore, so
    it must raise rather than silently cut past the requested depth."""
    with pytest.raises(ValueError, match="shallower than"):
        hardware.counterbore("M3", depth=2)  # M3 head recess needs 3.2
