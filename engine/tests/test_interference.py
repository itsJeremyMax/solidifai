from build123d import Box, Compound, Pos

from solidifai_engine import interference as itf
from solidifai_engine.session import Session


def _session(tmp_path) -> Session:
    return Session(artifacts_dir=str(tmp_path))


def test_overlapping_solids_report_overlap_volume():
    a = Box(10, 10, 10)
    b = Pos(5, 0, 0) * Box(10, 10, 10)  # 5 mm interpenetration in X
    rel = itf.classify_pair(a, b)
    assert rel["relation"] == "overlap"
    assert rel["overlapVolume"] > 100  # ~500 mm^3
    assert "overlapBbox" in rel


def test_face_touching_solids_are_adjacent_not_overlap():
    a = Box(10, 10, 10)
    b = Pos(10, 0, 0) * Box(10, 10, 10)  # share a face, no interpenetration
    rel = itf.classify_pair(a, b)
    assert rel["relation"] == "adjacent"
    assert "overlapVolume" not in rel


def test_separated_solids_are_clear():
    a = Box(10, 10, 10)
    b = Pos(50, 0, 0) * Box(10, 10, 10)
    assert itf.classify_pair(a, b)["relation"] == "clear"


def test_single_solid_internal_is_single():
    rep = itf.classify_internal(Box(10, 10, 10))
    assert rep["solids"] == 1
    assert rep["internal"] == "single"


def test_compound_of_two_overlapping_solids_is_internal_overlap():
    a = Box(10, 10, 10)
    b = Pos(5, 0, 0) * Box(10, 10, 10)
    rep = itf.classify_internal(Compound(children=[a, b]))
    assert rep["solids"] == 2
    assert rep["internal"] == "overlap"
    assert rep["internalOverlaps"] and rep["internalOverlaps"][0]["overlapVolume"] > 100


def test_compound_of_two_separated_solids_is_disjoint_with_components():
    a = Box(10, 10, 10)
    b = Pos(50, 0, 0) * Box(10, 10, 10)  # not touching -> floating lump
    rep = itf.classify_internal(Compound(children=[a, b]))
    assert rep["internal"] == "disjoint"
    assert len(rep["components"]) == 2
    assert all("centerOfMass" in c and "bbox" in c for c in rep["components"])


def test_compound_of_two_touching_solids_is_touching():
    a = Box(10, 10, 10)
    b = Pos(10, 0, 0) * Box(10, 10, 10)  # share a face -> one connected body
    rep = itf.classify_internal(Compound(children=[a, b]))
    assert rep["internal"] == "touching"


def test_check_interferences_reports_overlapping_parts(tmp_path):
    s = _session(tmp_path)
    s.execute_script(
        "from build123d import Box, Pos\n"
        "from solidifai import show\n"
        "show(Box(10,10,10), name='A')\n"
        "show(Pos(5,0,0)*Box(10,10,10), name='B')\n"
    )
    rep = s.check_interferences()
    assert rep["ok"] is True
    pair = next(p for p in rep["pairs"] if {p["a"], p["b"]} == {"A", "B"})
    assert pair["relation"] == "overlap"
    assert pair["overlapVolume"] > 100
    assert rep["summary"]["overlaps"] == 1


def test_check_interferences_clean_assembly_has_no_flags(tmp_path):
    s = _session(tmp_path)
    s.execute_script(
        "from build123d import Box, Pos\n"
        "from solidifai import show\n"
        "show(Box(10,10,10), name='A')\n"
        "show(Pos(20,0,0)*Box(10,10,10), name='B')\n"
    )
    rep = s.check_interferences()
    assert rep["summary"]["overlaps"] == 0
    assert rep["summary"]["disjoint"] == 0
    assert all(p["internal"] == "single" for p in rep["parts"])


def test_check_interferences_flags_floating_component(tmp_path):
    s = _session(tmp_path)
    s.execute_script(
        "from build123d import Box, Pos, Compound\n"
        "from solidifai import show\n"
        "show(Compound(children=[Box(10,10,10), Pos(50,0,0)*Box(10,10,10)]), name='Part')\n"
    )
    rep = s.check_interferences()
    part = next(p for p in rep["parts"] if p["name"] == "Part")
    assert part["internal"] == "disjoint"
    assert rep["summary"]["disjoint"] == 1


def test_check_interferences_empty_model_errors(tmp_path):
    s = _session(tmp_path)
    rep = s.check_interferences()
    assert rep["ok"] is False
    assert "no model" in rep["error"]
