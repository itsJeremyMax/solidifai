"""First-order validation: tolerance stack math and geometric stress hot-spots."""

import math

from build123d import (
    Axis,
    Box,
    BuildPart,
    Locations,
    Mode,
    fillet,
)

import solidifai_engine.validation as val

# --- tolerance stack ---------------------------------------------------------


def test_tolerance_worst_case_and_rss():
    chain = [
        {"label": "a", "nominal": 10.0, "plus": 0.02, "minus": -0.02, "direction": 1},
        {"label": "b", "nominal": 5.0, "plus": 0.01, "minus": -0.01, "direction": 1},
    ]
    r = val.tolerance_stack(chain)
    assert r["ok"] is True
    assert math.isclose(r["nominal"], 15.0)
    assert math.isclose(r["worstCase"]["max"], 15.03)
    assert math.isclose(r["worstCase"]["min"], 14.97)
    # RSS half-tol = sqrt(0.02^2 + 0.01^2), reported to 4 dp.
    assert math.isclose(r["rss"]["max"] - 15.0, math.hypot(0.02, 0.01), abs_tol=1e-3)


def test_tolerance_iso_fit_clearance():
    # Hole H7 over shaft g6 at Ø10 is a known clearance fit (ISO 286).
    chain = [
        {"label": "hole", "nominal": 10.0, "fit": "H7", "direction": 1},
        {"label": "shaft", "nominal": 10.0, "fit": "g6", "direction": -1},
    ]
    r = val.tolerance_stack(chain)
    assert r["ok"] is True
    assert r["fit"]["type"] == "clearance"
    assert r["fit"]["minGap"] > 0
    # Known ISO 286 values: hole 10.000..10.015, shaft 9.986..9.995.
    assert math.isclose(r["fit"]["minGap"], 0.005, abs_tol=1e-6)
    assert math.isclose(r["fit"]["maxGap"], 0.029, abs_tol=1e-6)


def test_tolerance_interference_fit():
    # Hole H7 over shaft p6 at Ø10 is an interference fit.
    chain = [
        {"label": "hole", "nominal": 10.0, "fit": "H7", "direction": 1},
        {"label": "shaft", "nominal": 10.0, "fit": "p6", "direction": -1},
    ]
    r = val.tolerance_stack(chain)
    assert r["fit"]["type"] == "interference"


def test_tolerance_bad_link_errors():
    assert val.tolerance_stack([{"label": "x", "nominal": 1.0, "fit": "Z99"}])["ok"] is False


# --- stress hot-spots --------------------------------------------------------


def _l_bracket(fillet_radius: float = 0.0):
    """An L-shaped part: a square plate with one corner quadrant removed leaves a
    single sharp re-entrant vertical edge at the inner corner (3, 3)."""
    with BuildPart() as p:
        Box(30, 30, 20)
        with Locations((11, 11, 0)):
            Box(16, 16, 20, mode=Mode.SUBTRACT)
        if fillet_radius:
            inner = (
                p.edges()
                .filter_by(Axis.Z)
                .filter_by(
                    lambda e: (
                        abs(e.position_at(0.5).X - 3) < 0.5 and abs(e.position_at(0.5).Y - 3) < 0.5
                    )
                )
            )
            fillet(inner, radius=fillet_radius)
    return p.part


def test_stress_clean_block_has_none():
    assert val.stress_hotspots(Box(20, 20, 20)) == []


def test_stress_flags_sharp_inner_corner():
    rep = val.stress_hotspots(_l_bracket(fillet_radius=0.0))
    sharp = [h for h in rep if h["rule"] == "sharp_internal_corner"]
    assert len(sharp) == 1
    assert sharp[0]["measured"]["value"] == 0.0  # no fillet radius
    assert sharp[0]["severity"] == "warning"


def test_stress_filleted_corner_has_none():
    rep = val.stress_hotspots(_l_bracket(fillet_radius=3.0))
    assert [h for h in rep if h["rule"] == "sharp_internal_corner"] == []
