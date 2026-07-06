"""Session-level analyze_dfm: envelope, process inference, summary."""

import os
import tempfile

from solidifai_engine.session import Session


def _session_with(code: str) -> Session:
    d = tempfile.mkdtemp()
    s = Session(os.path.join(d, "artifacts"))
    res = s.execute_script(code)
    assert res["ok"], res
    return s


def test_no_model_returns_error():
    d = tempfile.mkdtemp()
    s = Session(os.path.join(d, "artifacts"))
    rep = s.analyze_dfm()
    assert rep["ok"] is False
    assert "no model" in rep["error"]


def test_thin_pla_part_reports_critical_and_infers_fdm():
    s = _session_with(
        "from build123d import Box\n"
        "import solidifai\n"
        "solidifai.show(Box(20, 20, 0.6), name='Plate', material='pla')\n"
    )
    rep = s.analyze_dfm()
    assert rep["ok"] is True
    part = rep["parts"][0]
    assert part["partId"] == "plate"  # slug node id (matches model.json)
    assert part["partName"] == "Plate"  # human-readable display name
    assert part["process"] == "fdm"
    assert part["evaluated"] is True
    assert any(v["rule"] == "wall_thickness" for v in part["violations"])
    assert rep["summary"]["critical"] >= 1
    assert rep["buildId"] == s.build_id


def test_metal_part_is_not_evaluated_in_v1():
    s = _session_with(
        "from build123d import Box\n"
        "import solidifai\n"
        "solidifai.show(Box(20, 20, 0.6), name='Bracket', material='aluminum')\n"
    )
    rep = s.analyze_dfm()
    part = rep["parts"][0]
    assert part["process"] == "cnc"
    assert part["evaluated"] is False
    assert part["note"]
    assert rep["summary"]["critical"] == 0


def test_explicit_process_override():
    s = _session_with(
        "from build123d import Box\n"
        "import solidifai\n"
        "solidifai.show(Box(20, 20, 0.6), name='Plate', material='aluminum')\n"
    )
    rep = s.analyze_dfm(process="fdm")
    assert rep["parts"][0]["process"] == "fdm"
    assert rep["parts"][0]["evaluated"] is True


_FUNNEL_SCRIPT = (
    "from build123d import (Axis, BuildLine, BuildPart, BuildSketch, Plane,\n"
    "                       Polyline, make_face, revolve)\n"
    "import solidifai\n"
    "inner = [(6.0, 0.0), (6.0, 20.0), (30.0, 50.0)]\n"
    "outer = [(34.0, 50.0), (10.0, 20.0), (10.0, 0.0)]\n"
    "with BuildPart() as bp:\n"
    "    with BuildSketch(Plane.XZ):\n"
    "        with BuildLine():\n"
    "            Polyline(*(inner + outer + [inner[0]]))\n"
    "        make_face()\n"
    "    revolve(axis=Axis.Z)\n"
    "solidifai.show(bp.part, name='Funnel', material='pla')\n"
)


def test_revolved_constant_wall_funnel_has_no_false_critical():
    # Acceptance: a revolved 4 mm-wall funnel must report no critical / no warning
    # wall finding, and surface its real ~3.1 mm perpendicular wall as the minimum.
    s = _session_with(_FUNNEL_SCRIPT)
    rep = s.analyze_dfm()
    assert rep["ok"] is True
    assert rep["summary"]["critical"] == 0
    assert rep["summary"]["warning"] == 0
    assert 2.7 < rep["summary"]["minWallMm"] < 3.7
    part = rep["parts"][0]
    assert not any(v["rule"] == "wall_thickness" for v in part["violations"])
    assert 2.7 < part["metrics"]["minWallMm"] < 3.7
