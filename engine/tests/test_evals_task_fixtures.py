"""Deterministic geometry fixtures for the schema-2 task corpus."""

import json
import shutil
from pathlib import Path

from evals.graders import grade_workspace, open_grading_session
from evals.run import TASKS_DIR, discover_tasks, load_task, main

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "evals" / "fixtures"
TASK_9_FIXTURES = (
    "battery-box",
    "bracket-load",
    "box-lid-fit",
    "desk-organizer",
    "gear-pair",
    "handle-grip",
    "hinge",
    "hook-wall",
    "match-object",
    "pi-case",
    "phone-stand",
    "washer-spec",
)

FULL_SPEC_NEGATIVE_FIXTURES: dict[str, dict[str, dict[str, set[str]]]] = {
    "bracket-load": {
        "one-hole": {"semantic": {"wall-mount-holes"}, "dim_match": {"hole", "center_distance"}},
        "flat-plate": {"semantic": {"two-leg-load-geometry"}},
        "sharp-corner": {"stress": set()},
    },
    "desk-organizer": {
        "missing-phone-slot": {"semantic": {"three-usable-regions"}},
    },
    "hook-wall": {
        "one-hole": {"semantic": {"two-wall-holes"}},
        "flat-plate": {"semantic": {"hook-load-geometry"}},
    },
    "washer-spec": {
        "solid-disc": {"semantic": {"m8-bore"}, "dim_match": {"hole"}},
        "oversize-outer-diameter": {"dim_match": {"bbox_sorted:mid", "bbox_sorted:max"}},
        "too-thick": {"dim_match": {"bbox_sorted:min"}},
    },
}


def _grade(workspace: Path, spec: dict) -> dict:
    session = open_grading_session(str(workspace))
    try:
        return grade_workspace(session, spec)
    finally:
        session.close()


def _source_tree(workspace: Path) -> dict[str, bytes]:
    return {
        path.relative_to(workspace).as_posix(): path.read_bytes()
        for path in workspace.rglob("*")
        if path.is_file()
    }


def _semantic_checks(workspace: Path, spec: dict, tmp_path: Path) -> dict[str, dict]:
    copied = tmp_path / f"workspace-{workspace.parent.name}-{workspace.name}"
    before = _source_tree(workspace)
    shutil.copytree(workspace, copied)
    graded = _grade(
        copied,
        {
            "schema": 2,
            "graders": ["semantic"],
            "semantic_requirements": spec["semantic_requirements"],
        },
    )
    assert _source_tree(workspace) == before, "fixture source workspace was polluted by grading"
    semantic = graded["graders"][0]
    assert semantic["name"] == "semantic"
    assert semantic["data"], semantic["detail"]
    return {check["id"]: check for check in semantic["data"]["checks"]}


def _failed_grader_ids(graded: dict) -> dict[str, set[str]]:
    failed: dict[str, set[str]] = {}
    for grader in graded["graders"]:
        if grader["passed"] is True:
            continue
        if grader["name"] == "semantic" and grader.get("data"):
            failed["semantic"] = {
                check["id"] for check in grader["data"]["checks"] if check["pass"] is False
            }
            continue
        if grader["name"] == "dim_match" and grader.get("data"):
            labels = set()
            for check in grader["data"]["checks"]:
                if check["pass"]:
                    continue
                label = check["kind"]
                if check["kind"] == "bbox_sorted":
                    label = f"{label}:{check['axis']}"
                labels.add(label)
            failed["dim_match"] = labels
            continue
        if grader["name"] == "requirements" and grader.get("data"):
            failed["requirements"] = {
                row["id"] for row in grader["data"]["requirements"] if row.get("pass") is False
            }
            continue
        failed[grader["name"]] = set()
    return failed


def test_fixture_manifest_covers_the_twelve_task_corpus():
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert sorted(manifest) == discover_tasks(TASKS_DIR)
    assert len(manifest) == 12
    for task_name, negatives in manifest.items():
        assert (FIXTURES_DIR / task_name / "positive" / "model.py").is_file()
        assert negatives, task_name
        for fixture_name, requirement_id in negatives.items():
            assert (FIXTURES_DIR / task_name / fixture_name / "model.py").is_file()
            assert isinstance(requirement_id, str) and requirement_id


def test_positive_fixture_passes_every_programmatic_semantic_requirement(tmp_path):
    for task_name in discover_tasks(TASKS_DIR):
        task = load_task(task_name)
        if task.spec.get("fixture_matrix_migration"):
            continue
        checks = _semantic_checks(FIXTURES_DIR / task_name / "positive", task.spec, tmp_path)
        assert checks and all(check["pass"] for check in checks.values()), (task_name, checks)


def test_task_9_positive_fixtures_pass_full_configured_specs_from_tmp_copies(tmp_path):
    for task_name in TASK_9_FIXTURES:
        task = load_task(task_name)
        workspace = FIXTURES_DIR / task_name / "positive"
        copied = tmp_path / f"full-spec-{task_name}"
        shutil.copytree(workspace, copied)
        graded = _grade(copied, task.spec)
        failed = [grader for grader in graded["graders"] if grader["passed"] is not True]
        assert not failed, (task_name, failed)


def test_negative_fixture_fails_exactly_its_named_requirement_without_vlm(tmp_path):
    manifest = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    for task_name, negatives in manifest.items():
        spec = load_task(task_name).spec
        if spec.get("fixture_matrix_migration"):
            continue
        for fixture_name, failed_id in negatives.items():
            checks = _semantic_checks(FIXTURES_DIR / task_name / fixture_name, spec, tmp_path)
            failed = {check_id for check_id, check in checks.items() if not check["pass"]}
            assert failed == {failed_id}, (task_name, fixture_name, failed, checks)


def test_fixture_matrix_migrations_are_explicitly_marked():
    pending = {
        task_name
        for task_name in discover_tasks(TASKS_DIR)
        if load_task(task_name).spec.get("fixture_matrix_migration")
    }
    assert pending == set()


def test_full_spec_negative_fixtures_fail_their_named_requirements_from_tmp_copies(tmp_path):
    for task_name, fixtures in FULL_SPEC_NEGATIVE_FIXTURES.items():
        task = load_task(task_name)
        for fixture_name, expected in fixtures.items():
            copied = tmp_path / f"negative-{task_name}-{fixture_name}"
            shutil.copytree(FIXTURES_DIR / task_name / fixture_name, copied)
            graded = _grade(copied, task.spec)
            assert _failed_grader_ids(graded) == expected, (
                task_name,
                fixture_name,
                graded["graders"],
            )


def test_washer_positive_fixture_is_the_grade_only_known_good_workspace(tmp_path):
    workspace = FIXTURES_DIR / "washer-spec" / "positive"
    copied = tmp_path / "workspace"
    shutil.copytree(workspace, copied)
    assert (
        main(
            [
                "--tasks",
                "washer-spec",
                "--grade-only",
                str(copied),
                "--no-vlm",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
