"""VLM judge: rubric versioning, strict JSON parsing, stubbed end-to-end."""

import json

import pytest

from evals import vlm_judge
from evals.agent_runner import ClaudeResult
from evals.graders import open_grading_session
from solidifai_engine.session import Session

GOOD_JSON = json.dumps({a: {"score": 4, "why": "fine"} for a in vlm_judge.RUBRIC_AXES})

WASHER = """
from build123d import Cylinder
from solidifai import show

washer = Cylinder(8, 1.6) - Cylinder(4.2, 4)
show(washer, name="washer")
"""


def _runner_returning(stdout, exit_code=0, timed_out=False):
    def run(cmd, cwd, timeout_s, env):
        return ClaudeResult(exit_code, stdout, "", 0.5, timed_out)

    return run


def make_workspace(base, code):
    ws = base / "ws"
    ws.mkdir()
    s = Session(str(base / "art"), model_path=str(ws / "model.py"))
    res = s.execute_script(code)
    assert res.get("ok"), res
    return str(ws)


def test_rubric_is_versioned_and_covers_all_axes():
    assert vlm_judge.rubric_version() == "1"
    text = vlm_judge.RUBRIC_PATH.read_text(encoding="utf-8")
    for axis in vlm_judge.RUBRIC_AXES:
        assert f"## {axis}" in text
    # The anchored-score requirement from the design spec.
    assert "correct massing but unbroken edges and slab faces" in text


def test_parse_judge_output_extracts_embedded_json():
    envelope = json.dumps({"result": "Here are the scores:\n" + GOOD_JSON + "\nDone."})
    parsed = vlm_judge.parse_judge_output(envelope)
    assert parsed["scores"] == {a: 4 for a in vlm_judge.RUBRIC_AXES}
    assert parsed["rationales"]["realism"] == "fine"


def test_parse_rejects_missing_axis_and_out_of_range():
    missing = json.dumps({"result": json.dumps({"proportion": {"score": 4, "why": ""}})})
    with pytest.raises(ValueError):
        vlm_judge.parse_judge_output(missing)
    bad = {a: {"score": 9, "why": ""} for a in vlm_judge.RUBRIC_AXES}
    with pytest.raises(ValueError):
        vlm_judge.parse_judge_output(json.dumps({"result": json.dumps(bad)}))


def test_judge_end_to_end_with_stubbed_claude(tmp_path):
    ws = make_workspace(tmp_path, WASHER)
    gs = open_grading_session(ws)
    try:
        res = vlm_judge.judge(
            gs,
            "make a washer",
            {"views": ["iso", "top"]},
            tmp_path / "judge",
            runner=_runner_returning(json.dumps({"result": GOOD_JSON})),
        )
    finally:
        gs.close()
    assert res["scores"]["realism"] == 4
    assert res["rubric_version"] == "1"
    assert (tmp_path / "judge" / "views.png").is_file()


def test_judge_reports_unparseable_output(tmp_path):
    ws = make_workspace(tmp_path, WASHER)
    gs = open_grading_session(ws)
    try:
        res = vlm_judge.judge(
            gs,
            "make a washer",
            {},
            tmp_path / "judge",
            runner=_runner_returning(json.dumps({"result": "no json here"})),
        )
    finally:
        gs.close()
    assert res["error"].startswith("unparseable")


def test_parse_rejects_is_error_envelope():
    # claude can exit 0 with is_error:true (refusal/API error); that must not
    # be misreported as "no JSON object in judge output".
    envelope = json.dumps({"is_error": True, "result": "API error: overloaded"})
    with pytest.raises(ValueError, match="is_error"):
        vlm_judge.parse_judge_output(envelope)


def test_judge_handles_ok_but_empty_views(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path, WASHER)
    gs = open_grading_session(ws)
    try:
        monkeypatch.setattr(gs.session, "capture_views", lambda **kw: {"ok": True, "views": []})
        res = vlm_judge.judge(gs, "make a washer", {}, tmp_path / "judge")
    finally:
        gs.close()
    assert res["error"] == "view capture failed"


def test_judge_skips_empty_workspace(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    gs = open_grading_session(str(ws))
    try:
        res = vlm_judge.judge(gs, "anything", {}, tmp_path / "judge")
    finally:
        gs.close()
    assert res["error"] == "no model to judge"
