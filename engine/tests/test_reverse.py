"""Reverse engineering: measure a shape into dimensions + detected features."""

import math

from build123d import Box, BuildPart, Hole, Locations

import solidifai_engine.reverse as reverse


def _plate_with_holes():
    with BuildPart() as p:
        Box(60, 40, 6)
        with Locations((-20, -10), (20, 10)):
            Hole(radius=1.7)  # ~3.4 mm diameter through-holes
    return p.part


def test_analyze_box_with_two_holes():
    rep = reverse.analyze_shape(_plate_with_holes())
    assert rep["planarFaces"] >= 6
    # Two round features, de-duped (not 4 from OCC half-faces). The hole/boss
    # label is a low-trust heuristic (carries a confidence); the value is that
    # the two ~3.4 mm round features are surfaced with their dimensions.
    rounds = [f for f in rep["features"] if f["kind"] in ("hole", "boss", "cylindrical")]
    assert len(rounds) == 2
    assert all(math.isclose(f["diameter"], 3.4, abs_tol=0.1) for f in rounds)
    assert all("confidence" in f for f in rounds)
    assert rep["bbox"]["size"][0] == 60.0


def test_analyze_plain_box():
    rep = reverse.analyze_shape(Box(20, 20, 20))
    assert rep["features"] == []
    assert rep["primitiveGuess"] in ("box", "plate")
    assert rep["planarFaces"] == 6


def test_analyze_thin_plate_guess():
    rep = reverse.analyze_shape(Box(40, 40, 3))
    assert rep["primitiveGuess"] == "plate"


def test_analyze_plain_cylinder_guess():
    # A solid cylinder has one cylindrical face and two planar caps; it must be
    # recognized as a cylinder, not lumped into "compound".
    from build123d import Cylinder  # noqa: PLC0415 - local import for test reuse

    rep = reverse.analyze_shape(Cylinder(radius=10, height=30))
    assert rep["primitiveGuess"] == "cylinder"
