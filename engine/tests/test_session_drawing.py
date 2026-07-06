"""Session.create_drawing writes the drawing files + spec data."""

import os
from pathlib import Path

from solidifai_engine.session import Session

_MODEL = (
    "from build123d import BuildPart, Box, Cylinder, Mode\n"
    "import solidifai\n"
    "with BuildPart() as bp:\n"
    "    Box(20, 20, 10)\n"
    "    Cylinder(radius=2.5, height=10, mode=Mode.SUBTRACT)\n"
    "solidifai.show(bp.part, name='Plate', material='pla')\n"
)


def _session(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_MODEL, encoding="utf-8")
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert s.run_file(str(root / "model.py"))["ok"]
    return s, root


def test_create_drawing_writes_svg_and_pdf(tmp_path):
    s, root = _session(tmp_path)
    res = s.create_drawing()
    assert res["ok"], res
    exts = sorted(os.path.splitext(f)[1] for f in res["files"])
    assert ".svg" in exts
    assert ".pdf" in exts  # fpdf2 is a dependency
    assert res["scale"]
    for f in res["files"]:
        assert os.path.exists(f) and os.path.getsize(f) > 0


def test_drawing_svg_has_dims_material_and_hole_chart(tmp_path):
    # A single-part model now renders a located hole chart (the dimension upgrade)
    # rather than the aggregate "HOLES:" tally, which is an assembly-page feature.
    s, root = _session(tmp_path)
    res = s.create_drawing()
    svg_path = next(f for f in res["files"] if f.endswith(".svg"))
    svg = Path(svg_path).read_text(encoding="utf-8")
    assert "20.0" in svg  # overall W/D
    assert "10.0" in svg  # overall H
    assert "PLA" in svg  # spec material
    assert "HOLE CHART" in svg and "5.0" in svg  # Ø5 hole located in the chart
    assert "FRONT" in svg and "ISO" in svg  # view labels


def test_no_model_errors(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    res = s.create_drawing()
    assert res["ok"] is False
    assert "no model" in res["error"]


def test_explicit_filename_is_honored(tmp_path):
    s, root = _session(tmp_path)
    res = s.create_drawing(path="sheet1.pdf")
    assert res["ok"], res
    assert any(f.endswith("sheet1.pdf") for f in res["files"])
    assert any(f.endswith("sheet1.svg") for f in res["files"])


_TWO_PARTS = (
    "from build123d import Box, Pos\n"
    "import solidifai\n"
    "solidifai.show(Box(20, 20, 10), name='Plate', material='pla')\n"
    "solidifai.show(Pos(40, 0, 0) * Box(10, 10, 30), name='Post', material='pla')\n"
)


def test_drawing_is_multipage_for_multi_unique_parts(tmp_path):
    # Two distinct part shapes -> assembly overview + 2 detail pages (3 sheets).
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(_TWO_PARTS, encoding="utf-8")
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert s.run_file(str(root / "model.py"))["ok"]
    res = s.create_drawing()
    assert res["ok"], res
    svg = Path(next(f for f in res["files"] if f.endswith(".svg"))).read_text(encoding="utf-8")
    # stacked SVG -> one sheet frame (281mm wide) per page: assembly + 2 parts
    assert svg.count('width="281.000"') >= 3
    assert "Plate" in svg and "Post" in svg  # both part detail sheets present


def test_part_sheet_locates_all_off_center_holes(tmp_path):
    # Four off-center through-holes must each be located in the hole chart (robust
    # axis-based hole classification; the old solid-center heuristic under-counted).
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(
        "from build123d import BuildPart, Box, Cylinder, Mode, Locations\n"
        "import solidifai\n"
        "with BuildPart() as bp:\n"
        "    Box(60, 40, 12)\n"
        "    with Locations((-22, -14), (22, -14), (22, 14), (-22, 14)):\n"
        "        Cylinder(radius=2.0, height=12, mode=Mode.SUBTRACT)\n"
        "solidifai.show(bp.part, name='Bracket', material='aluminum')\n",
        encoding="utf-8",
    )
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert s.run_file(str(root / "model.py"))["ok"]
    res = s.create_drawing()
    svg_path = next(f for f in res["files"] if f.endswith(".svg"))
    svg = Path(svg_path).read_text(encoding="utf-8")
    assert "HOLE CHART" in svg
    assert svg.count("Ø4.0") == 4  # all four Ø4.0 holes located as chart rows
