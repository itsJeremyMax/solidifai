"""Sheet layout, overall dimensions, hole schedule, title/spec panel."""

from build123d import Box, Cylinder, Pos

from solidifai_engine.drawing import sheet
from solidifai_engine.drawing.model import Line, Text

_SPEC = {
    "bbox": (20.0, 10.0, 5.0),
    "material": "PLA",
    "process": "fdm",
    "mass_g": 1.24,
    "volume_cm3": 1.0,
    "part_count": 1,
    "dfm_summary": "No issues",
    "bom": [{"name": "Body", "qty": 1, "mass_g": 1.24}],
    "holes": {3.2: 4, 5.0: 2},
    "name": "widget",
    "units": "mm",
    "generated_at": "2026-06-04",
}


def _texts(d):
    return [t.s for t in d.items if isinstance(t, Text)]


def test_overall_dims_equal_bbox():
    d, meta = sheet.compose(Box(20, 10, 5), _SPEC, {})
    texts = _texts(d)
    assert "20.0" in texts  # width (X)
    assert "5.0" in texts  # height (Z)
    assert "10.0" in texts  # depth (Y)


def test_hole_schedule_note_present():
    d, meta = sheet.compose(Box(20, 10, 5), _SPEC, {})
    note = next(t for t in _texts(d) if t.startswith("HOLES"))
    assert "4x" in note and "3.2" in note
    assert "2x" in note and "5.0" in note


def test_title_block_has_material_and_name():
    d, meta = sheet.compose(Box(20, 10, 5), _SPEC, {})
    texts = _texts(d)
    assert "PLA" in texts
    assert "widget" in texts
    assert meta["scaleLabel"]  # e.g. "2:1" or "1:1"


def test_everything_fits_on_the_sheet():
    d, meta = sheet.compose(Box(20, 10, 5), _SPEC, {})
    for ln in d.items:
        if isinstance(ln, Line):
            for x, y in ((ln.x1, ln.y1), (ln.x2, ln.y2)):
                assert -0.5 <= x <= sheet.SHEET_W + 0.5
                assert -0.5 <= y <= sheet.SHEET_H + 0.5


def test_chosen_scale_is_a_nice_ratio():
    d, meta = sheet.compose(Box(20, 10, 5), _SPEC, {})
    assert meta["scale"] in sheet._NICE


def test_panel_is_branded_with_mono_values():
    d, meta = sheet.compose(Box(20, 10, 5), _SPEC, {})
    texts = [t for t in d.items if isinstance(t, Text)]
    wordmark = next(t for t in texts if t.s == "solidifai")
    assert wordmark.color == sheet.ACCENT and wordmark.bold
    assert any(t.mono for t in texts)  # spec values use the monospace technical face
    assert "Generated with solidifai" in [t.s for t in texts]


_PART_SPEC = {
    "bbox": (40.0, 20.0, 4.0),
    "material": "PLA",
    "process": "FDM",
    "mass_g": 12.0,
    "qty": 4,
    "name": "Foot",
    "units": "mm",
    "generated_at": "2026-06-07",
    "holes": [
        {"center": (-10.0, 0.0, 0.0), "axis": (0.0, 0.0, 1.0), "dia": 5.0},
        {"center": (10.0, 0.0, 0.0), "axis": (0.0, 0.0, 1.0), "dia": 5.0},
    ],
}


def _plate():
    p = Box(40, 20, 4)
    for dx in (-10, 10):
        p -= Pos(dx, 0, 0) * Cylinder(radius=2.5, height=10)
    return p


def test_part_sheet_has_qty_and_hole_chart():
    d, meta = sheet.compose_part({"shape": _plate(), "spec": _PART_SPEC}, _PART_SPEC, {})
    texts = _texts(d)
    assert any("QTY" in t or t == "4" for t in texts)  # quantity shown
    assert any(t.startswith("HOLE") for t in texts)  # hole chart header
    assert any("5.0" in t for t in texts)  # the hole diameter appears in a chart row


def test_part_sheet_dimensions_are_part_bbox():
    d, meta = sheet.compose_part({"shape": _plate(), "spec": _PART_SPEC}, _PART_SPEC, {})
    texts = _texts(d)
    assert "40.0" in texts and "20.0" in texts and "4.0" in texts


def test_front_view_hole_chart_y_stays_within_part_height():
    # A side (Y-axis) hole on a part resting on z=0 charts in the front view, where
    # the vertical axis is the part's height. Its charted Y must be the height above
    # the base (8), never inflated past the part. Regression: a vertical-sign mix
    # between the located point and the drawn views charted this far off the part.
    import re

    from build123d import Align, Box, Cylinder, Pos

    block = Box(40, 20, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))  # z in [0, 30]
    block -= Pos(10, 0, 8) * Cylinder(radius=3, height=40, rotation=(90, 0, 0))  # Y-axis bore
    spec = {
        "bbox": (40.0, 20.0, 30.0),
        "material": "PLA",
        "process": "FDM",
        "mass_g": 1.0,
        "qty": 1,
        "name": "Block",
        "units": "mm",
        "generated_at": "2026-06-07",
        "holes": [{"center": (10.0, 0.0, 8.0), "axis": (0.0, 1.0, 0.0), "dia": 6.0}],
    }
    d, meta = sheet.compose_part({"shape": block, "spec": spec}, spec, {})
    row = next(t for t in _texts(d) if t.lstrip().startswith("A") and "6.0" in t)
    nums = re.findall(r"\d+\.\d+", row.replace("6.0", "", 1))  # drop the diameter token
    chart_y = float(nums[-1])
    assert chart_y == 8.0, f"expected Y=8.0 (height above base), got {chart_y} in {row!r}"


def test_views_do_not_cross_into_the_panel_for_flat_wide_parts():
    # A flat wide plate's iso is wider than its depth; the layout must scale so no
    # view line bleeds across the panel divider into the data block.
    panel_x = sheet.SHEET_W - sheet.MARGIN - sheet.PANEL_W
    d, meta = sheet.compose_part({"shape": _plate(), "spec": _PART_SPEC}, _PART_SPEC, {})
    crossing = [
        ln
        for ln in d.items
        if isinstance(ln, Line)
        and max(ln.x1, ln.x2) > panel_x + 0.5
        and min(ln.x1, ln.x2) < panel_x - 0.5
    ]
    assert not crossing, f"{len(crossing)} view lines cross the panel divider"


def test_assembly_bom_is_grouped_and_uncapped():
    spec = dict(_SPEC)
    spec["bom"] = [{"name": f"P{i}", "qty": 1, "mass_g": 1.0} for i in range(12)]
    spec["part_count"] = 12
    d, meta = sheet.compose(Box(20, 10, 5), spec, {})
    # all 12 unique rows render (no [:7] cap); rows past the old cap are present
    assert any("P7" in t or "P8" in t or "P11" in t for t in _texts(d))


def test_oversized_part_scales_to_fit_the_panel():
    # A part larger than the smallest nice ratio (1:100) once floored the scale at
    # 1:100 and overflowed the drawing area, bleeding across the panel divider.
    spec = dict(_SPEC)
    spec["bbox"] = (20000.0, 15000.0, 200.0)
    spec["holes"] = {}
    d, meta = sheet.compose(Box(20000, 15000, 200), spec, {})
    panel_x = sheet.SHEET_W - sheet.MARGIN - sheet.PANEL_W
    crossing = [
        ln
        for ln in d.items
        if isinstance(ln, Line)
        and max(ln.x1, ln.x2) > panel_x + 0.5
        and min(ln.x1, ln.x2) < panel_x - 0.5
    ]
    assert not crossing, f"{len(crossing)} view lines cross the panel divider"
    for ln in d.items:
        if isinstance(ln, Line):
            for x, _y in ((ln.x1, ln.y1), (ln.x2, ln.y2)):
                assert x <= sheet.SHEET_W + 0.5


def test_hole_tags_stay_alphabetic_past_z():
    # 27+ charted holes once ran the A..Z counter into '[', '\\', ']' via chr();
    # they must roll over to spreadsheet-style AA, AB, ... instead.
    from build123d import Align, Box, Cylinder, Pos

    plate = Box(200, 200, 4, align=(Align.CENTER, Align.CENTER, Align.MIN))
    holes = []
    for i in range(30):
        hx, hy = -90 + (i % 10) * 20, -90 + (i // 10) * 20
        plate -= Pos(hx, hy, 0) * Cylinder(radius=2, height=10)
        holes.append({"center": (float(hx), float(hy), 0.0), "axis": (0.0, 0.0, 1.0), "dia": 4.0})
    spec = dict(_PART_SPEC)
    spec["bbox"] = (200.0, 200.0, 4.0)
    spec["holes"] = holes
    d, meta = sheet.compose_part({"shape": plate, "spec": spec}, spec, {})
    tags = {
        t.s for t in d.items if isinstance(t, Text) and t.color == sheet.ACCENT and len(t.s) <= 2
    }
    assert not (tags & set("[\\]^_`")), f"non-alphabetic tags leaked: {tags}"
    assert "AA" in tags  # rolled over past Z


def test_bom_overflow_note_stays_above_the_title_block():
    spec = dict(_SPEC)
    spec["bom"] = [{"name": f"P{i}", "qty": 1, "mass_g": 1.0} for i in range(25)]
    spec["part_count"] = 25
    d, meta = sheet.compose(Box(20, 10, 5), spec, {})
    ty = sheet.SHEET_H - sheet.MARGIN - 40.0  # the title-block rule
    note = next(t for t in d.items if isinstance(t, Text) and t.s.endswith("more"))
    assert note.y < ty, f"'+N more' at y={note.y} overlaps the title block rule at {ty}"


def test_oblique_holes_get_an_informational_note_not_a_chart_row():
    import math

    from build123d import Align, Box, Cylinder, Pos

    block = Box(40, 40, 40, align=(Align.CENTER, Align.CENTER, Align.MIN))
    block -= Pos(0, 0, 20) * Cylinder(radius=3, height=60, rotation=(45, 0, 0))
    ax = (0.0, math.sin(math.radians(45)), math.cos(math.radians(45)))
    spec = dict(_PART_SPEC)
    spec["bbox"] = (40.0, 40.0, 40.0)
    spec["holes"] = [{"center": (0.0, 0.0, 20.0), "axis": ax, "dia": 6.0}]
    d, meta = sheet.compose_part({"shape": block, "spec": spec}, spec, {})
    texts = _texts(d)
    assert any("oblique" in t for t in texts), "expected an oblique-hole note"
    assert not any(t.startswith("HOLE CHART") for t in texts)  # no ambiguous chart
