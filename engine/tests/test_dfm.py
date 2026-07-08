"""Unit tests for the DFM rules engine (pure geometry, no engine/socket)."""

from build123d import (
    Axis,
    Box,
    BuildLine,
    BuildPart,
    BuildSketch,
    Cylinder,
    Mode,
    Plane,
    Polyline,
    Pos,
    Rot,
    extrude,
    make_face,
    revolve,
)

import solidifai_engine.dfm as dfm


def _rules(rep, rule):
    return [v for v in rep["violations"] if v["rule"] == rule]


def test_fdm_defaults_present():
    cfg = dfm.FDM_DEFAULTS
    assert cfg["min_wall_mm"] == 0.8
    assert cfg["min_wall_load_bearing_mm"] == 1.2
    assert cfg["max_overhang_deg"] == 45.0
    assert cfg["max_bridge_warn_mm"] == 5.0
    assert cfg["max_bridge_crit_mm"] == 10.0
    assert cfg["min_hole_diameter_mm"] == 2.0


def test_analyze_part_unknown_process_not_evaluated():
    rep = dfm.analyze_part(Box(10, 10, 10), process="cnc")
    assert rep["evaluated"] is False
    assert rep["process"] == "cnc"
    assert rep["violations"] == []


def test_analyze_part_process_is_case_insensitive():
    # 'FDM'/'Fdm' (reachable via the analyze_dfm process override) must evaluate
    # exactly like 'fdm', not silently skip every check.
    for process in ("FDM", "Fdm", " fdm "):
        rep = dfm.analyze_part(Box(20, 20, 0.5), process=process)
        assert rep["evaluated"] is True, process
        assert any(v["rule"] == "wall_thickness" for v in rep["violations"]), process
    # a genuinely unevaluated process stays unevaluated regardless of case.
    assert dfm.analyze_part(Box(10, 10, 10), process="CNC")["evaluated"] is False


def test_analyze_part_thick_fdm_block_has_no_violations():
    rep = dfm.analyze_part(Box(10, 10, 10), process="fdm")
    assert rep["evaluated"] is True
    assert rep["violations"] == []


def test_vertical_walls_are_not_overhangs():
    rep = dfm.analyze_part(Box(10, 10, 10), process="fdm")
    assert _rules(rep, "overhang") == []
    assert _rules(rep, "bridge") == []


def test_angled_downward_face_flags_overhang():
    # A box tilted 30 deg about Y: its former bottom face now sits at ~30 deg
    # from horizontal -- shallower than the 45 deg support-free limit.
    tilted = Rot(0, 30, 0) * Box(10, 10, 10)
    rep = dfm.analyze_part(tilted, process="fdm")
    over = _rules(rep, "overhang")
    assert len(over) >= 1
    assert over[0]["severity"] == "warning"
    assert over[0]["measured"]["value"] < 45.0


def test_horizontal_tunnel_ceiling_flags_bridge_critical():
    # A 12 mm-wide horizontal tunnel through a block: its ceiling is a flat,
    # elevated, unsupported span (12 mm narrow dimension > the 10 mm crit limit).
    with BuildPart() as bp:
        Box(20, 20, 20)
        Box(12, 30, 5, mode=Mode.SUBTRACT)  # tunnel through Y, 12 wide x 5 tall
    rep = dfm.analyze_part(bp.part, process="fdm")
    bridges = _rules(rep, "bridge")
    assert len(bridges) >= 1
    assert bridges[0]["measured"]["value"] >= 10.0
    assert bridges[0]["severity"] == "critical"


def test_bottom_face_on_plate_is_excluded():
    # The flat bottom face of a plain box rests on z=min and must NOT be a
    # bridge or overhang (it prints sitting on the bed).
    rep = dfm.analyze_part(Box(20, 20, 2), process="fdm")
    assert _rules(rep, "bridge") == []
    assert _rules(rep, "overhang") == []


def _part_with_hole(diameter):
    with BuildPart() as bp:
        Box(20, 20, 10)
        Cylinder(radius=diameter / 2, height=10, mode=Mode.SUBTRACT)
    return bp.part


def test_small_hole_flags_advisory():
    rep = dfm.analyze_part(_part_with_hole(1.5), process="fdm")
    holes = _rules(rep, "small_hole")
    assert len(holes) == 1
    assert holes[0]["severity"] == "advisory"
    assert holes[0]["source"] == "tool_default"
    assert holes[0]["measured"]["value"] == 1.5


def test_large_hole_is_fine():
    rep = dfm.analyze_part(_part_with_hole(5.0), process="fdm")
    assert _rules(rep, "small_hole") == []


def _l_bracket_with_inner_fillet(radius: float):
    """An L-bracket with a small concave fillet on its inner corner. The fillet
    is a partial cylinder (UV span ~pi/2), NOT a hole, so it must not be flagged
    as a small hole even though its radius sits below the hole minimum."""
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline((0, 0), (10, 0), (10, 2), (2, 2), (2, 10), (0, 10), (0, 0))
            make_face()
        extrude(amount=10)
    part = bp.part
    inner = min(
        part.edges().filter_by(Axis.Y), key=lambda e: abs(e.center().X - 2) + abs(e.center().Z - 2)
    )
    return part.fillet(radius=radius, edge_list=[inner])


def test_inner_fillet_is_not_a_small_hole():
    # Regression: a 0.5 mm concave fillet is a partial cylinder, not a hole. It
    # must not be misread as a too-small hole (the opposite of the fix stress
    # analysis recommends).
    rep = dfm.analyze_part(_l_bracket_with_inner_fillet(0.5), process="fdm")
    assert _rules(rep, "small_hole") == []


def _part_with_slotted_hole(slot_width):
    # A 1.5 mm through-hole bisected by a thin slot, so the single cylinder splits
    # into two arc-faces on the same axis (each arc spanning less than the full 2*pi).
    with BuildPart() as bp:
        Box(20, 20, 10)
        Cylinder(radius=0.75, height=10, mode=Mode.SUBTRACT)
        Box(40, slot_width, 10, mode=Mode.SUBTRACT)
    return bp.part


def test_split_below_min_hole_flags_once():
    # R1: a below-minimum hole bisected into two arcs (each ~2.32 rad) must still
    # be flagged -- and exactly once, not dropped as two sub-full partial cylinders.
    rep = dfm.analyze_part(_part_with_slotted_hole(0.6), process="fdm")
    holes = _rules(rep, "small_hole")
    assert len(holes) == 1
    assert holes[0]["measured"]["value"] == 1.5


def test_wider_split_hole_is_not_double_counted():
    # B7: when each half-cylinder spans past the old per-arc guard (~2.6 rad), the
    # hole must be reported once, not twice at the two arc-face centroids.
    rep = dfm.analyze_part(_part_with_slotted_hole(0.4), process="fdm")
    holes = _rules(rep, "small_hole")
    assert len(holes) == 1
    assert holes[0]["measured"]["value"] == 1.5


# -- wall thickness (sampled ray cast) --------------------------------------


def test_thin_plate_flags_wall_critical():
    rep = dfm.analyze_part(Box(20, 20, 0.6), process="fdm")
    walls = _rules(rep, "wall_thickness")
    assert len(walls) >= 1
    assert walls[0]["severity"] == "critical"
    assert walls[0]["sampled"] is True
    assert walls[0]["measured"]["value"] < 0.8


def test_one_mm_plate_reports_no_critical_wall():
    rep = dfm.analyze_part(Box(20, 20, 1.0), process="fdm")
    crit = [v for v in _rules(rep, "wall_thickness") if v["severity"] == "critical"]
    assert crit == []


def test_thick_block_has_no_wall_violation():
    rep = dfm.analyze_part(Box(10, 10, 10), process="fdm")
    assert _rules(rep, "wall_thickness") == []


def test_min_wall_measurement_is_close_to_truth():
    # A 0.6 mm plate: the sampled thinnest wall should be ~0.6 mm, proving the
    # ray cast measures real thickness rather than noise.
    rep = dfm.analyze_part(Box(30, 30, 0.6), process="fdm")
    walls = _rules(rep, "wall_thickness")
    assert walls and abs(walls[0]["measured"]["value"] - 0.6) < 0.25


# -- wall thickness on revolved / curved walls (false-positive regression) ---


def _revolved_funnel(wall: float = 4.0):
    """A funnel of revolution: a straight spout tube that opens into a conical
    bowl, with a constant ``wall`` mm radial wall. The cross-section is a closed
    polygon in the XZ plane (X = radius, Z = height) revolved about Z.

    By construction the wall is a uniform 4 mm radial offset, so the *true
    perpendicular* minimum wall in the slanted cone is ~4*cos(slope) ~ 3.1 mm --
    well above the 0.8 mm FDM minimum. A coarse mesh of the curved cone faces is
    exactly what used to produce a wandering ~0.00 mm false critical."""
    inner = [(6.0, 0.0), (6.0, 20.0), (30.0, 50.0)]
    outer = [(30.0 + wall, 50.0), (6.0 + wall, 20.0), (6.0 + wall, 0.0)]
    pts = inner + outer + [inner[0]]
    with BuildPart() as bp:
        with BuildSketch(Plane.XZ):
            with BuildLine():
                Polyline(*pts)
            make_face()
        revolve(axis=Axis.Z)
    return bp.part


def _thin_cylinder_shell(wall: float = 0.4, r_out: float = 10.0, height: float = 20.0):
    """An open tube with a genuine ``wall`` mm curved wall -- a real thin wall on
    the same kind of curved faces as the funnel, so it proves the fix does not
    over-suppress true thin walls."""
    with BuildPart() as bp:
        Cylinder(radius=r_out, height=height)
        Cylinder(radius=r_out - wall, height=height, mode=Mode.SUBTRACT)
    return bp.part


def test_revolved_constant_wall_cone_has_no_wall_violation():
    # Regression: the 4 mm-wall funnel is thick everywhere; a flat tessellation
    # facet on the curved cone must not be read as a ~0 mm wall.
    rep = dfm.analyze_part(_revolved_funnel(4.0), process="fdm")
    assert _rules(rep, "wall_thickness") == []


def test_revolved_cone_reports_zero_critical_zero_warning():
    rep = dfm.analyze_part(_revolved_funnel(4.0), process="fdm")
    sev = {v["severity"] for v in rep["violations"]}
    assert "critical" not in sev
    assert "warning" not in sev


def test_revolved_cone_reports_measured_min_wall_near_truth():
    # The measured minimum wall must always be present as a number, and it must
    # be the real ~3.1 mm perpendicular wall, not a 0.00 mm outlier.
    rep = dfm.analyze_part(_revolved_funnel(4.0), process="fdm")
    mw = rep["metrics"]["minWallMm"]
    assert mw is not None
    assert 2.7 < mw < 3.7, mw


def test_min_wall_mm_on_revolved_cone_is_robust():
    assert 2.7 < dfm.min_wall_mm(_revolved_funnel(4.0)) < 3.7


def test_genuine_thin_curved_shell_still_flags_critical():
    # A real 0.4 mm curved wall must STILL flag critical -- only artifacts are
    # suppressed, never real thin walls.
    rep = dfm.analyze_part(_thin_cylinder_shell(0.4), process="fdm")
    crit = [v for v in _rules(rep, "wall_thickness") if v["severity"] == "critical"]
    assert crit, "a genuine 0.4 mm wall must flag critical"
    assert crit[0]["measured"]["value"] < 0.8
    assert not crit[0].get("possibleArtifact"), "a corroborated thin wall is not an artifact"


def test_genuine_thin_shell_measurement_is_stable_across_rebuilds():
    a = dfm.min_wall_mm(_thin_cylinder_shell(0.4))
    b = dfm.min_wall_mm(_thin_cylinder_shell(0.4))
    assert a is not None and b is not None
    assert abs(a - b) < 0.1, (a, b)
    assert abs(a - 0.4) < 0.2, a


# -- persistence / area threshold (synthetic samples, deterministic) ---------


def _sample(t, x, y, z, area=2.0, face_type="GeomType.CONE", curved=True):
    return {"t": t, "point": [x, y, z], "area": area, "face_type": face_type, "curved": curved}


def test_single_isolated_thin_sample_is_not_critical():
    # One lone sub-threshold sliver surrounded by thick samples must never raise
    # a critical -- it is tagged an advisory possible artifact instead.
    samples = [_sample(0.05, 0, 0, 0, area=0.5)] + [
        _sample(5.0, i * 4.0, 0, 0) for i in range(1, 6)
    ]
    walls = dfm._violations_from_samples(samples, dfm.FDM_DEFAULTS)
    assert all(v["severity"] != "critical" for v in walls)
    assert any(v.get("possibleArtifact") for v in walls)


def test_contiguous_thin_region_flags_critical():
    # A patch of agreeing thin samples spanning real area is a genuine thin wall.
    samples = [_sample(0.5, x * 0.8, y * 0.8, 0, area=2.0) for x in range(5) for y in range(5)]
    walls = dfm._violations_from_samples(samples, dfm.FDM_DEFAULTS)
    crit = [v for v in walls if v["severity"] == "critical"]
    assert crit
    assert not crit[0].get("possibleArtifact")
