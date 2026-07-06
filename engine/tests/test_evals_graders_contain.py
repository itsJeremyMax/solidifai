"""Containment (the hollow-cyberdeck class of bug) and CoM-stability graders."""

from evals.graders import grade_containment, grade_stability, open_grading_session
from solidifai_engine.session import Session

HOLLOW_CASE_WITH_REF = """
from build123d import Box
from solidifai import show

shell = Box(96, 66, 26) - Box(90, 60, 20)
show(shell, name="case")
show(Box(85, 56, 18), name="ref: pi5 board", role="reference")
"""

SOLID_BLOCK_WITH_REF = """
from build123d import Box
from solidifai import show

show(Box(96, 66, 26), name="case")
show(Box(85, 56, 18), name="ref: pi5 board", role="reference")
"""

HOLLOW_CASE_NO_REF = """
from build123d import Box
from solidifai import show

shell = Box(96, 66, 26) - Box(90, 60, 20)
show(shell, name="case")
"""

STABLE = """
from build123d import Box, Pos
from solidifai import show

show(Box(60, 60, 5) + Pos(0, 0, 12.5) * Box(10, 10, 20), name="tower")
"""

# Base 6 mm thick so the overhanging mass (bottom at z=2) sits ABOVE the 1 mm
# bottom-contact slab (zmin=-3): the footprint is the small base alone.
TIPPY = """
from build123d import Box, Pos
from solidifai import show

show(Box(20, 20, 6) + Pos(20, 0, 17) * Box(30, 30, 30), name="lean")
"""

CONTAIN_SPEC = {
    "graders": ["containment"],
    "containment": {"volumes": [{"name": "pi5", "size_mm": [85, 56, 18]}]},
}


def make_workspace(base, code):
    ws = base / "ws"
    ws.mkdir()
    s = Session(str(base / "art"), model_path=str(ws / "model.py"))
    res = s.execute_script(code)
    assert res.get("ok"), res
    return str(ws)


def _run(grader, ws, spec):
    gs = open_grading_session(ws)
    try:
        return grader(gs, spec)
    finally:
        gs.close()


def test_hollow_case_with_reference_contains(tmp_path):
    ws = make_workspace(tmp_path, HOLLOW_CASE_WITH_REF)
    res = _run(grade_containment, ws, CONTAIN_SPEC)
    assert res.passed is True and res.score == 1.0
    assert res.data["checks"][0]["via"] == "reference"


def test_solid_block_fails_containment(tmp_path):
    # The hollow-cyberdeck failure class: enclosure modeled solid.
    ws = make_workspace(tmp_path, SOLID_BLOCK_WITH_REF)
    res = _run(grade_containment, ws, CONTAIN_SPEC)
    assert res.passed is False and res.score == 0.0


def test_missing_reference_uses_capped_fallback(tmp_path):
    ws = make_workspace(tmp_path, HOLLOW_CASE_NO_REF)
    res = _run(grade_containment, ws, CONTAIN_SPEC)
    assert res.passed is True
    assert res.score == 0.5  # fallback pass is capped
    assert "fallback" in res.detail


def test_stable_part_passes(tmp_path):
    ws = make_workspace(tmp_path, STABLE)
    res = _run(grade_stability, ws, {"stability": {"footprint_margin": 0.9}})
    assert res.passed is True


def test_tippy_part_fails(tmp_path):
    ws = make_workspace(tmp_path, TIPPY)
    res = _run(grade_stability, ws, {"stability": {"footprint_margin": 0.9}})
    assert res.passed is False
    assert "CoM" in res.detail


REF_ONLY = """
from build123d import Box
from solidifai import show

show(Box(85, 56, 18), name="ref: pi5 board", role="reference")
"""


def test_degenerate_size_mm_fails_cleanly(tmp_path):
    # A zero/negative axis must record a failed check, never crash Box().
    ws = make_workspace(tmp_path, HOLLOW_CASE_WITH_REF)
    spec = {
        "graders": ["containment"],
        "containment": {"volumes": [{"name": "bad", "size_mm": [0, 56, 18]}]},
    }
    res = _run(grade_containment, ws, spec)
    assert res.passed is False and res.score == 0.0
    assert res.data["checks"][0]["detail"] == "degenerate size_mm"


def test_empty_workspace_no_geometry(tmp_path):
    # Direct call (no grade_workspace has_model guard) on a designed-parts-less
    # workspace must degrade cleanly, not ValueError out of _union_bbox.
    ws = make_workspace(tmp_path, REF_ONLY)
    res = _run(grade_containment, ws, CONTAIN_SPEC)
    assert res.passed is False and res.score == 0.0
    assert "no geometry" in res.detail
