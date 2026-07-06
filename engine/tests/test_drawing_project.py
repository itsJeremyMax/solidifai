"""HLR projection of a known box into 2D view polylines."""

from build123d import Box, Compound

from solidifai_engine.drawing import project


def _span(polylines):
    bb = project.polylines_bbox(polylines)
    assert bb is not None
    return (bb[2] - bb[0], bb[3] - bb[1])


def test_front_view_spans_width_and_height():
    out = project.project_view(Box(20, 10, 5), "front")
    du, dv = _span(out["visible"])
    assert abs(du - 20) < 0.5
    assert abs(dv - 5) < 0.5


def test_top_view_spans_width_and_depth():
    out = project.project_view(Box(20, 10, 5), "top")
    du, dv = _span(out["visible"])
    assert abs(du - 20) < 0.5
    assert abs(dv - 10) < 0.5


def test_right_view_spans_depth_and_height():
    out = project.project_view(Box(20, 10, 5), "right")
    du, dv = _span(out["visible"])
    assert abs(du - 10) < 0.5
    assert abs(dv - 5) < 0.5


def test_iso_view_has_edges():
    out = project.project_view(Box(20, 10, 5), "iso")
    assert len(out["visible"]) > 1


def test_empty_compound_yields_nothing_without_raising():
    out = project.project_view(Compound(children=[]), "front")
    assert out["visible"] == []
    assert out["hidden"] == []


def test_unknown_view_raises():
    import pytest

    with pytest.raises(ValueError):
        project.project_view(Box(1, 1, 1), "back")


def test_project_point_matches_drawn_geometry():
    # A box corner at (10,5,2.5) must project to the same (u,v) the edges use.
    box = Box(20, 10, 5)  # centered at origin -> corner at (10, 5, 2.5)
    out = project.project_view(box, "front")
    bb = project.polylines_bbox(out["visible"])  # (min_u, min_v, max_u, max_v)
    u, v = project.project_point("front", (10.0, 5.0, 2.5))
    # front: u = x (right), v = z (up). Corner must sit at a bbox extreme.
    assert abs(u - bb[2]) < 1e-6  # max_u corresponds to x = +10
    assert abs(abs(v) - max(abs(bb[1]), abs(bb[3]))) < 1e-6


def test_view_axes_are_orthonormal():
    import math

    for view in ("front", "top", "right", "iso"):
        x, up, z = project.view_axes(view)
        for a in (x, up, z):
            assert abs(math.sqrt(sum(c * c for c in a)) - 1.0) < 1e-9
        assert abs(sum(a * b for a, b in zip(x, up, strict=True))) < 1e-9  # x . up == 0


def test_project_point_shares_the_drawn_frame_for_offcenter_parts():
    # A located point must report v in the SAME range the drawn HLR edges occupy,
    # so marks land on the geometry. Regression: project_point used the opposite
    # vertical sign from project_view, so off-center parts (resting on z=0 rather
    # than centered) charted hole heights far outside the part.
    from build123d import Box, Pos

    part = Pos(0, 0, 15) * Box(40, 20, 30)  # z in [0, 30], not symmetric about origin
    bb = project.polylines_bbox(project.project_view(part, "front")["visible"])
    _, v_bottom = project.project_point("front", (0, 0, 0))
    _, v_top = project.project_point("front", (0, 0, 30))
    assert abs(min(v_bottom, v_top) - bb[1]) < 1e-6
    assert abs(max(v_bottom, v_top) - bb[3]) < 1e-6
