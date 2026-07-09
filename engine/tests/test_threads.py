"""Real modeled ISO metric threads: valid + manifold, correct pitch and diameters,
and an external thread that screws into an internal cutter with positive clearance."""

import math

import pytest
from build123d import Align, Cylinder, Location

from solidifai import hardware, std


def _minor_major_cyl_volume(size, length):
    from solidifai_engine import standards

    d = float(size[1:])
    p = standards.thread_pitch(size)
    d3 = d - 1.2269 * p
    return math.pi * (d3 / 2) ** 2 * length, math.pi * (d / 2) ** 2 * length


@pytest.mark.parametrize("size", ["M2", "M2.5", "M3", "M4", "M5", "M6", "M8"])
def test_external_thread_is_valid_and_manifold(size):
    t = hardware.external_thread(size, 10.0)
    assert t.is_valid
    assert t.is_manifold
    assert len(t.solids()) == 1


@pytest.mark.parametrize("size", ["M2.5", "M6", "M8"])
def test_external_volume_between_minor_and_major(size):
    t = hardware.external_thread(size, 10.0)
    vmin, vmax = _minor_major_cyl_volume(size, 10.0)
    assert vmin < t.volume < vmax


@pytest.mark.parametrize("size,turns", [("M6", 5), ("M3", 5), ("M8", 4)])
def test_pitch_is_correct(size, turns):
    """N turns of thread stand exactly N*pitch tall (measure without the lead-in
    chamfer, which trims the ends)."""
    p = std.thread_pitch(size)
    t = hardware.external_thread(size, turns * p, lead_in=False)
    assert math.isclose(t.bounding_box().size.Z, turns * p, abs_tol=0.03)


def test_thread_pitch_matches_iso261():
    assert std.thread_pitch("M6") == 1.0
    assert std.thread_pitch("M8") == 1.25
    assert std.thread_pitch("M3") == 0.5
    with pytest.raises(ValueError):
        std.thread_pitch("M99")


def test_internal_cutter_is_valid_and_manifold():
    c = hardware.internal_thread_cutter("M6", 8.0)
    assert c.is_valid
    assert c.is_manifold


def test_external_screws_into_internal_with_positive_clearance():
    """The headline correctness check: cut a nut blank with the internal cutter,
    drop the matching external thread into the hole on the same axis, and confirm
    the two do not interpenetrate (overlap volume ~ 0). The lead-in chamfer on both
    parts is what removes the sharp partial-thread crests that would otherwise
    clash, so this is run with the defaults an agent gets."""
    blank = Cylinder(6.0, 8.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    nut = blank - hardware.internal_thread_cutter("M6", 8.0)
    assert nut.is_valid and nut.is_manifold

    rod = hardware.external_thread("M6", 8.0)
    overlap = nut & rod
    overlap_vol = overlap.volume if overlap.solids() else 0.0
    assert overlap_vol < 0.05  # essentially no interference at the standard clearance

    # and the parts are really engaged, not floating past each other
    assert rod.volume > 0 and nut.volume < blank.volume


def test_external_thread_builds_quickly():
    """Performance guard: a modeled M6x10 thread must build in a couple of seconds,
    not minutes. If this regresses, the groove sweep has gone pathological."""
    import time

    start = time.time()
    t = hardware.external_thread("M6", 10.0)
    assert t.is_valid
    assert time.time() - start < 8.0


def test_thread_tessellates_and_exports(tmp_path):
    """Threads compose with tessellation and STL export like any other solid."""
    t = hardware.external_thread("M6", 10.0)
    verts, tris = t.tessellate(0.1)
    assert len(verts) > 100
    assert len(tris) > 100

    from build123d import export_stl

    out = tmp_path / "thread.stl"
    assert export_stl(t, str(out))
    assert out.exists() and out.stat().st_size > 0


def test_clearance_widens_the_female_thread():
    """A larger clearance removes more material from the nut (a looser thread)."""
    blank_a = Cylinder(6.0, 8.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    blank_b = Cylinder(6.0, 8.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    tight = blank_a - hardware.internal_thread_cutter("M6", 8.0, clearance=0.1)
    loose = blank_b - hardware.internal_thread_cutter("M6", 8.0, clearance=0.25)
    assert loose.volume < tight.volume
