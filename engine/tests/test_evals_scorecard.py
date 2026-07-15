"""Composite math, report rendering, baseline round trip."""

import json

import pytest

from evals import scorecard as sc
from evals.vlm_judge import RUBRIC_AXES


def _run(prog, vlm=None):
    vscore = sc.vlm_score(vlm)
    return {
        "workspace": "/tmp/w",
        "agent": None,
        "programmatic": {
            "graders": [{"name": "dfm", "passed": True, "score": 1.0, "detail": "ok", "data": {}}],
            "programmatic_score": prog,
        },
        "vlm": vlm,
        "vlm_score": vscore,
        "composite": sc.composite(prog, vscore),
    }


def test_vlm_score_normalizes_one_to_five():
    assert sc.vlm_score({"scores": {a: 5 for a in RUBRIC_AXES}}) == 1.0
    assert sc.vlm_score({"scores": {a: 1 for a in RUBRIC_AXES}}) == 0.0
    assert sc.vlm_score({"scores": {a: 3 for a in RUBRIC_AXES}}) == 0.5
    assert sc.vlm_score({"error": "no model"}) is None
    assert sc.vlm_score(None) is None


def test_composite_weights_and_no_vlm_fallback():
    assert sc.composite(0.8, 0.5) == 0.68  # 0.6*0.8 + 0.4*0.5
    assert sc.composite(0.8, None) == 0.8


def test_required_vlm_failure_is_inconclusive_not_perfect():
    result = sc.grade_result(programmatic=1.0, vlm={"error": "timeout"}, vlm_required=True)
    assert result["terminal_status"] == "inconclusive"
    assert result["gate_passed"] is False
    assert result["composite"] is None


def test_no_vlm_is_explicit_and_only_valid_when_not_required():
    allowed = sc.grade_result(
        programmatic=1.0,
        vlm={"status": "skipped", "reason": "--no-vlm"},
        vlm_required=False,
    )
    required = sc.grade_result(programmatic=1.0, vlm={"status": "skipped"}, vlm_required=True)
    assert allowed["terminal_status"] == "passed"
    assert allowed["gate_passed"] is True
    assert required["terminal_status"] == "inconclusive"


def test_explicit_no_vlm_skip_is_inconclusive_for_required_tasks():
    result = sc.grade_result(
        programmatic=1.0,
        vlm={"status": "skipped", "reason": "--no-vlm"},
        vlm_required=True,
    )
    assert result == {"terminal_status": "inconclusive", "gate_passed": False, "composite": None}


@pytest.mark.parametrize(
    "vlm",
    [None, {}, {"error": "timeout"}, {"scores": {RUBRIC_AXES[0]: 5}}],
)
def test_requested_vlm_failure_is_inconclusive_for_every_task(vlm):
    result = sc.grade_result(programmatic=1.0, vlm=vlm, vlm_required=False)
    assert result == {"terminal_status": "inconclusive", "gate_passed": False, "composite": None}


def test_only_explicit_no_vlm_skip_can_bypass_the_judge():
    result = sc.grade_result(
        programmatic=1.0,
        vlm={"status": "skipped", "reason": "--no-vlm"},
        vlm_required=False,
    )
    assert result["terminal_status"] == "passed"


def test_agent_and_grader_failures_cannot_be_quality_results():
    for agent in (
        {"exit_code": 3, "timed_out": False},
        {"exit_code": 0, "timed_out": False, "envelope_valid": False},
    ):
        result = sc.grade_result(
            programmatic=1.0, vlm={"status": "skipped"}, vlm_required=False, agent=agent
        )
        assert result["terminal_status"] == "infra_error"
        assert result["composite"] is None
    result = sc.grade_result(
        programmatic={"programmatic_score": 1.0, "graders": [{"detail": "grader crashed: boom"}]},
        vlm={"status": "skipped"},
        vlm_required=False,
    )
    assert result["terminal_status"] == "inconclusive"


def test_incomplete_runs_are_not_quality_aggregates():
    complete = _run(1.0)
    complete.update({"terminal_status": "passed", "gate_passed": True})
    incomplete = _run(1.0)
    incomplete.update({"terminal_status": "infra_error", "gate_passed": False, "composite": None})
    summary = sc.summarize_task([complete, incomplete])
    assert summary["composite_mean"] == 1.0
    assert summary["incomplete_runs"] == 1


def test_scorecard_with_baseline_deltas():
    judge = {"scores": {a: 4 for a in RUBRIC_AXES}, "rubric_version": "1"}
    card = sc.build_scorecard(
        tier="smoke",
        task_results={"washer-spec": [_run(1.0, judge), _run(0.5, judge)]},
        repeats=2,
        rubric_ver="1",
        vlm_enabled=True,
        baseline={"schema": 1, "tasks": {"washer-spec": 0.5}},
    )
    t = card["tasks"]["washer-spec"]
    assert t["composite_min"] < t["composite_mean"] < t["composite_max"]
    assert t["baseline"] == 0.5
    assert t["delta"] == round(t["composite_mean"] - 0.5, 4)
    assert card["rubric_version"] == "1"
    assert card["composite"] == t["composite_mean"]


def test_report_renders_per_grader_detail():
    card = sc.build_scorecard(
        tier="smoke",
        task_results={"hook-wall": [_run(1.0)]},
        repeats=1,
        rubric_ver=None,
        vlm_enabled=False,
        baseline=None,
    )
    report = sc.render_report(card)
    assert "| hook-wall |" in report
    assert "dfm: PASS" in report
    assert "VLM skipped" in report


def test_baseline_round_trip(tmp_path):
    card = sc.build_scorecard(
        tier="full",
        task_results={"hook-wall": [_run(0.75)]},
        repeats=1,
        rubric_ver="1",
        vlm_enabled=True,
        baseline=None,
    )
    base = sc.baseline_from_scorecard(card)
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    loaded = sc.load_baseline(p)
    assert loaded["tasks"]["hook-wall"] == 0.75
    assert loaded["rubric_version"] == "1"
    assert sc.load_baseline(tmp_path / "missing.json") is None


def test_write_run_outputs(tmp_path):
    card = sc.build_scorecard(
        tier="smoke",
        task_results={"hook-wall": [_run(1.0)]},
        repeats=1,
        rubric_ver=None,
        vlm_enabled=False,
        baseline=None,
    )
    sc.write_run_outputs(tmp_path / "run1", card)
    assert json.loads((tmp_path / "run1" / "scorecard.json").read_text(encoding="utf-8"))
    assert (tmp_path / "run1" / "report.md").is_file()


def test_summarize_task_zero_runs():
    assert sc.summarize_task([]) == {
        "composite_mean": None,
        "composite_min": None,
        "composite_max": None,
        "quality_runs": 0,
        "incomplete_runs": 0,
    }
    card = sc.build_scorecard(
        tier="smoke",
        task_results={"hook-wall": []},
        repeats=1,
        rubric_ver=None,
        vlm_enabled=False,
        baseline=None,
    )
    assert card["tasks"]["hook-wall"]["composite_mean"] is None


def test_stale_baseline_suppresses_deltas():
    card = sc.build_scorecard(
        tier="full",
        task_results={"hook-wall": [_run(0.75)]},
        repeats=1,
        rubric_ver="2",
        vlm_enabled=True,
        baseline={"schema": 1, "rubric_version": "1", "tasks": {"hook-wall": 0.5}},
    )
    t = card["tasks"]["hook-wall"]
    assert card["baseline_stale"] is True
    assert t["baseline"] is None
    assert t["delta"] is None
    report = sc.render_report(card)
    assert "baseline stale (rubric v2 vs v1); deltas suppressed" in report

    fresh = sc.build_scorecard(
        tier="full",
        task_results={"hook-wall": [_run(0.75)]},
        repeats=1,
        rubric_ver="1",
        vlm_enabled=True,
        baseline={"schema": 1, "rubric_version": "1", "tasks": {"hook-wall": 0.5}},
    )
    assert fresh["baseline_stale"] is False
    assert fresh["tasks"]["hook-wall"]["delta"] == 0.25


def test_report_escapes_markdown_in_details():
    judge = {
        "scores": {a: 4 for a in RUBRIC_AXES},
        "rationales": {a: "ok | fine" for a in RUBRIC_AXES},
    }
    run = _run(1.0, judge)
    run["programmatic"]["graders"][0]["detail"] = "bad | pipe\nsecond line"
    card = sc.build_scorecard(
        tier="smoke",
        task_results={"hook|wall": [run]},
        repeats=1,
        rubric_ver="1",
        vlm_enabled=True,
        baseline=None,
    )
    report = sc.render_report(card)
    assert "| hook\\|wall |" in report
    assert "bad \\| pipe second line" in report
    assert "ok \\| fine" in report
    assert "bad | pipe" not in report


def test_write_run_outputs_nan_safe(tmp_path):
    run = _run(1.0)
    run["programmatic"]["graders"][0]["data"] = {
        "mass": float("nan"),
        "stress": float("inf"),
        "nested": [float("-inf"), 1.5],
    }
    card = sc.build_scorecard(
        tier="smoke",
        task_results={"hook-wall": [run]},
        repeats=1,
        rubric_ver=None,
        vlm_enabled=False,
        baseline=None,
    )
    sc.write_run_outputs(tmp_path / "run1", card)
    text = (tmp_path / "run1" / "scorecard.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    data = json.loads(text)
    grader_data = data["tasks"]["hook-wall"]["runs"][0]["programmatic"]["graders"][0]["data"]
    assert grader_data["mass"] is None
    assert grader_data["stress"] is None
    assert grader_data["nested"] == [None, 1.5]


def test_error_runs_build_and_render():
    error_run = {
        "workspace": "/tmp/w",
        "error": "engine exploded",
        "composite": 0.0,
        "programmatic": {"programmatic_score": 0.0, "graders": []},
        "vlm": None,
        "vlm_score": None,
    }
    card = sc.build_scorecard(
        tier="custom",
        task_results={"t": [error_run, _run(1.0)]},
        repeats=2,
        rubric_ver=None,
        vlm_enabled=False,
        baseline=None,
    )
    assert card["tasks"]["t"]["composite_mean"] == 0.5
    report = sc.render_report(card)
    assert "run failed: engine exploded" in report
