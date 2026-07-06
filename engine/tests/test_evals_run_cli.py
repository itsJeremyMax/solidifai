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
    s = Session(str(tmp_path / "art"), model_path=str(ws / "model.py"))
    assert s.execute_script(WASHER)["ok"]

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
    assert rc == 0
    run_dir = next((tmp_path / "runs").iterdir())
    card = json.loads((run_dir / "scorecard.json").read_text(encoding="utf-8"))
    failed = card["tasks"]["washer-spec"]["runs"][0]
    assert failed["error"] == "boom"
    assert failed["composite"] == 0.0
    assert card["tasks"]["phone-stand"]["composite_mean"] == 1.0
    assert "run failed: boom" in (run_dir / "report.md").read_text(encoding="utf-8")
