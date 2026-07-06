"""Core graders against fixture models built in-test through the engine."""

import os

import pytest

from evals import graders
from evals.graders import grade_workspace, open_grading_session
from solidifai_engine.session import Session

GOOD_WASHER = """
from build123d import Cylinder
from solidifai import show

washer = Cylinder(8, 1.6) - Cylinder(4.2, 4)
show(washer, name="washer")
"""

# Deliberately bad: a critically thin wall (0.4 mm < FDM 0.8 minimum), an
# interpenetrating pair, and a part with disconnected floating geometry.
BAD_MODEL = """
from build123d import Box, Compound, Pos
from solidifai import show

show(Box(20, 20, 0.4), name="thin_plate")
show(Pos(5, 0, 0) * Box(10, 10, 0.4), name="overlapper")
show(Compound(children=[Box(5, 5, 5), Pos(40, 0, 0) * Box(5, 5, 5)]), name="broken_lump")
"""

SPEC = {
    "schema": 1,
    "graders": ["requirements", "dfm", "watertight", "interference"],
    "requirements": [
        {"id": "watertight", "quantity": "watertight", "op": "==", "bound": True},
        {"id": "printable", "quantity": "dfm_critical", "op": "<=", "bound": 0},
        {"id": "no-overlap", "quantity": "overlaps", "op": "<=", "bound": 0},
    ],
}


def make_workspace(base, code):
    ws = base / "ws"
    ws.mkdir()
    s = Session(str(base / "art"), model_path=str(ws / "model.py"))
    res = s.execute_script(code)
    assert res.get("ok"), res
    return str(ws)


@pytest.fixture(scope="module")
def good_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("good"), GOOD_WASHER)


@pytest.fixture(scope="module")
def bad_ws(tmp_path_factory):
    return make_workspace(tmp_path_factory.mktemp("bad"), BAD_MODEL)


def _grade(ws, spec=SPEC):
    gs = open_grading_session(ws)
    try:
        return grade_workspace(gs, spec)
    finally:
        gs.close()


def test_good_model_passes_core_graders(good_ws):
    out = _grade(good_ws)
    by = {g["name"]: g for g in out["graders"]}
    assert by["watertight"]["passed"] is True
    assert by["dfm"]["passed"] is True
    assert by["interference"]["passed"] is True
    assert by["requirements"]["passed"] is True
    assert out["programmatic_score"] == 1.0


def test_bad_model_fails_the_right_graders(bad_ws):
    out = _grade(bad_ws)
    by = {g["name"]: g for g in out["graders"]}
    assert by["dfm"]["passed"] is False  # 0.4 mm wall is critical
    assert by["interference"]["passed"] is False  # overlap + floating lump
    assert by["requirements"]["passed"] is False
    assert 0.0 < out["programmatic_score"] < 1.0


def test_empty_workspace_scores_zero(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    out = _grade(str(ws))
    assert out["programmatic_score"] == 0.0
    assert all(g["detail"] == "no model produced" for g in out["graders"])


def test_watertight_grader_fails_on_nonmanifold_report(good_ws, monkeypatch):
    gs = open_grading_session(good_ws)
    try:
        monkeypatch.setattr(gs.session, "get_model_info", lambda: {"manifold": False})
        res = graders.grade_watertight(gs, SPEC)
    finally:
        gs.close()
    assert res.passed is False and res.score == 0.0


def test_stress_grader_flags_sharp_reentrant_corner(tmp_path):
    bracket = """
from build123d import Box, Pos
from solidifai import show
show(Box(40, 20, 4) + Pos(-18, 0, 12) * Box(4, 20, 20), name="l_bracket")
"""
    ws = make_workspace(tmp_path, bracket)
    gs = open_grading_session(ws)
    try:
        res = graders.grade_stress(gs, {"graders": ["stress"]})
    finally:
        gs.close()
    assert res.passed is False  # unfilleted internal corner concentrates stress
    assert "warning" in res.detail


def test_unknown_grader_is_reported_not_crashed(good_ws):
    out = _grade(good_ws, {"schema": 1, "graders": ["watertight", "made_up"]})
    by = {g["name"]: g for g in out["graders"]}
    assert by["made_up"]["passed"] is None
    assert "unknown grader" in by["made_up"]["detail"]


def test_zero_requirements_is_vacuous_not_a_failure(good_ws):
    out = _grade(good_ws, {"schema": 1, "graders": ["requirements"], "requirements": []})
    by = {g["name"]: g for g in out["graders"]}
    assert by["requirements"]["passed"] is None
    assert by["requirements"]["score"] == 1.0
    assert by["requirements"]["detail"] == "no requirements"


def test_constructor_failure_cleans_up_temp_artifacts_dir(tmp_path, monkeypatch):
    import tempfile

    made = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        made.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)

    import solidifai_engine.session as session_mod

    def boom(*args, **kwargs):
        raise RuntimeError("engine startup failed")

    monkeypatch.setattr(session_mod, "Session", boom)

    with pytest.raises(RuntimeError, match="engine startup failed"):
        open_grading_session(str(tmp_path))
    assert made, "expected GradingSession to create an artifacts tmpdir"
    assert not any(os.path.exists(p) for p in made), "artifacts tmpdir leaked"
