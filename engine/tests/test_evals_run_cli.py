"""CLI contract + a real --grade-only end-to-end (no claude, no vlm)."""

import json
import re

import pytest

from evals.run import KNOWN_GRADERS, load_task, main
from solidifai_engine.session import Session

WASHER = """
from build123d import Cylinder
from solidifai import show

washer = Cylinder(8, 1.6) - Cylinder(4.2, 4)
show(washer, name="washer")
"""


def test_known_graders_matches_the_registry():
    from evals.graders import GRADERS

    assert set(GRADERS) == set(KNOWN_GRADERS)


def test_grade_only_requires_exactly_one_task(tmp_path):
    with pytest.raises(SystemExit):
        main(["--grade-only", str(tmp_path), "--tasks", "washer-spec,phone-stand"])
    with pytest.raises(SystemExit):
        main(["--grade-only", str(tmp_path)])  # tier implies 3 tasks


def test_grade_only_scores_a_real_workspace_without_claude(tmp_path, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "model.py").write_text(WASHER, encoding="utf-8")

    rc = main(
        [
            "--grade-only",
            str(ws),
            "--tasks",
            "washer-spec",
            "--no-vlm",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert rc == 0
    run_dir = next((tmp_path / "runs").iterdir())
    card = json.loads((run_dir / "scorecard.json").read_text(encoding="utf-8"))
    task = card["tasks"]["washer-spec"]
    assert task["composite_mean"] >= 0.9  # the fixture IS the golden washer
    assert (run_dir / "report.md").is_file()
    by = {g["name"]: g for g in task["runs"][0]["programmatic"]["graders"]}
    assert set(by) == set(load_task("washer-spec").spec["graders"])
    assert card["tier"] == "grade-only"
    assert card["vlm"] is False


def test_run_ids_are_collision_resistant():
    from evals.run import _run_id

    ids = {_run_id() for _ in range(8)}  # same-second calls must not collide
    assert len(ids) == 8
    assert all(re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", i) for i in ids)


def test_one_failing_task_does_not_abort_the_run(tmp_path, monkeypatch, capsys):
    import evals.agent_runner as agent_runner
    import evals.run as run_mod

    monkeypatch.setattr(agent_runner, "ensure_claude", lambda: "claude")

    def fake_run_task_once(task, ws_dir, out_dir, *, no_vlm):
        if task.name == "washer-spec":
            raise RuntimeError("boom")
        return {
            "workspace": str(ws_dir),
            "agent": None,
            "programmatic": {"programmatic_score": 1.0, "graders": []},
            "vlm": None,
            "vlm_score": None,
            "composite": 1.0,
        }

    monkeypatch.setattr(run_mod, "run_task_once", fake_run_task_once)

    rc = main(
        [
            "--tasks",
            "washer-spec,phone-stand",
            "--no-vlm",
            "--runs-dir",
            str(tmp_path / "runs"),
            "--workspaces-root",
            str(tmp_path / "ws"),
        ]
    )
    assert rc == 1
    run_dir = next((tmp_path / "runs").iterdir())
    card = json.loads((run_dir / "scorecard.json").read_text(encoding="utf-8"))
    failed = card["tasks"]["washer-spec"]["runs"][0]
    assert failed["error"] == "boom"
    assert failed["terminal_status"] == "infra_error"
    assert failed["composite"] is None
    assert card["tasks"]["phone-stand"]["composite_mean"] == 1.0
    assert "run failed: boom" in (run_dir / "report.md").read_text(encoding="utf-8")


def test_agent_failure_cannot_pass_with_partial_geometry(tmp_path, monkeypatch):
    import evals.agent_runner as agent_runner
    import evals.provision as provision
    import evals.run as run_mod

    task = load_task("washer-spec")
    monkeypatch.setattr(provision, "provision_workspace", lambda *args: None)

    class Engine:
        def __init__(self, *args):
            pass

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr(agent_runner, "EngineProcess", Engine)
    monkeypatch.setattr(
        agent_runner, "run_agent", lambda *args, **kwargs: {"exit_code": -1, "timed_out": True}
    )
    monkeypatch.setattr(
        run_mod,
        "grade_workspace_dir",
        lambda *args, **kwargs: {"programmatic": {"programmatic_score": 1.0, "graders": []}},
    )
    result = run_mod.run_task_once(task, tmp_path / "ws", tmp_path / "out", no_vlm=False)
    assert result["terminal_status"] == "infra_error"
    assert result["gate_passed"] is False


def test_grade_only_retains_open_or_grade_failure_as_infra_error(tmp_path, monkeypatch):
    import evals.run as run_mod

    def boom(*args, **kwargs):
        raise RuntimeError("bad workspace")

    monkeypatch.setattr(run_mod, "grade_workspace_dir", boom)
    rc = main(
        [
            "--grade-only",
            str(tmp_path / "missing"),
            "--tasks",
            "washer-spec",
            "--no-vlm",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert rc == 1
    card = json.loads(next((tmp_path / "runs").iterdir()).joinpath("scorecard.json").read_text())
    run = card["tasks"]["washer-spec"]["runs"][0]
    assert run["terminal_status"] == "infra_error"
    assert run["error"] == "bad workspace"


def test_no_vlm_cli_is_nongate_for_required_vlm_tasks(tmp_path, monkeypatch):
    import evals.run as run_mod
    from evals import scorecard as sc

    real_task = load_task("washer-spec")
    required_task = type(real_task)(
        name=real_task.name,
        brief=real_task.brief,
        spec={**real_task.spec, "vlm_required": True},
        timeout_s=real_task.timeout_s,
    )

    monkeypatch.setattr(run_mod, "load_task", lambda name: required_task)
    monkeypatch.setattr(
        run_mod,
        "grade_workspace_dir",
        lambda *args, **kwargs: {
            "workspace": str(tmp_path / "ws"),
            "agent": None,
            "programmatic": {"programmatic_score": 1.0, "graders": []},
            "vlm": {"status": "skipped", "reason": "--no-vlm"},
            "vlm_score": None,
            **sc.grade_result(
                programmatic=1.0,
                vlm={"status": "skipped", "reason": "--no-vlm"},
                vlm_required=True,
            ),
        },
    )

    rc = main(
        [
            "--grade-only",
            str(tmp_path / "ws"),
            "--tasks",
            "washer-spec",
            "--no-vlm",
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert rc == 1
    card = json.loads(next((tmp_path / "runs").iterdir()).joinpath("scorecard.json").read_text())
    run = card["tasks"]["washer-spec"]["runs"][0]
    assert run["terminal_status"] == "inconclusive"
    assert run["gate_passed"] is False
