"""Golden-task loading + spec schema validation for the eval harness."""

import json

import pytest

from evals.run import (
    DEFAULT_TIMEOUT_S,
    KNOWN_GRADERS,
    SMOKE_TASKS,
    Task,
    discover_tasks,
    load_task,
    tier_tasks,
    validate_spec,
)

VALID_SPEC = {
    "schema": 1,
    "graders": ["watertight", "dfm"],
    "requirements": [
        {"id": "wt", "quantity": "watertight", "op": "==", "bound": True},
        {"id": "pr", "quantity": "dfm_critical", "op": "<=", "bound": 0},
    ],
}


def _write_task(tasks_dir, name, brief="Make a thing.", spec=VALID_SPEC):
    d = tasks_dir / name
    d.mkdir(parents=True)
    (d / "brief.md").write_text(brief, encoding="utf-8")
    (d / "spec.json").write_text(json.dumps(spec), encoding="utf-8")


def test_validate_spec_accepts_a_valid_spec():
    assert validate_spec(VALID_SPEC) == []


def test_validate_spec_rejects_garbage():
    assert validate_spec({}) != []
    msgs = "; ".join(validate_spec({"schema": 1, "graders": ["nope"]}))
    assert "unknown grader 'nope'" in msgs
    bad_req = {
        "schema": 1,
        "graders": ["watertight"],
        "requirements": [{"id": "x", "quantity": "bogus", "op": "<=", "bound": 1}],
    }
    assert validate_spec(bad_req)


def test_validate_spec_rejects_requirements_missing_or_malformed_bound():
    missing_bound = {
        "schema": 1,
        "graders": ["watertight"],
        "requirements": [{"id": "wt", "quantity": "watertight", "op": "=="}],
    }
    assert "invalid requirement 'wt'" in "; ".join(validate_spec(missing_bound))
    within_scalar = {
        "schema": 1,
        "graders": ["watertight"],
        "requirements": [{"id": "m", "quantity": "mass", "op": "within", "bound": 5}],
    }
    assert "invalid requirement 'm'" in "; ".join(validate_spec(within_scalar))
    within_ok = {
        "schema": 1,
        "graders": ["watertight"],
        "requirements": [{"id": "m", "quantity": "mass", "op": "within", "bound": [1, 5]}],
    }
    assert validate_spec(within_ok) == []


def test_validate_spec_requires_grader_configs():
    assert validate_spec({"schema": 1, "graders": ["motion"]})  # needs motion config
    assert validate_spec({"schema": 1, "graders": ["containment"]})  # needs volumes
    ok = {
        "schema": 1,
        "graders": ["motion", "containment"],
        "motion": {"kind": "revolute", "part": {"name_contains": "leaf"}},
        "containment": {"volumes": [{"name": "v", "size_mm": [10, 10, 10]}]},
    }
    assert validate_spec(ok) == []


def test_validate_spec_checks_expected_dims_and_timeout():
    bad = {
        "schema": 1,
        "graders": ["dim_match"],
        "expected_dims": [{"kind": "bogus", "expected": 1, "tol": 0.1}],
        "timeout_s": -5,
    }
    msgs = "; ".join(validate_spec(bad))
    assert "expected_dims" in msgs
    assert "timeout_s" in msgs


def test_discover_and_load_tasks_from_a_dir(tmp_path):
    _write_task(tmp_path, "alpha")
    _write_task(tmp_path, "beta", spec={**VALID_SPEC, "timeout_s": 120})
    assert discover_tasks(tmp_path) == ["alpha", "beta"]
    t = load_task("beta", tasks_dir=tmp_path)
    assert isinstance(t, Task)
    assert t.timeout_s == 120
    assert load_task("alpha", tasks_dir=tmp_path).timeout_s == DEFAULT_TIMEOUT_S


def test_load_task_rejects_empty_brief_and_bad_spec(tmp_path):
    _write_task(tmp_path, "empty", brief="   ")
    with pytest.raises(ValueError):
        load_task("empty", tasks_dir=tmp_path)
    _write_task(tmp_path, "bad", spec={"schema": 2, "graders": ["dfm"]})
    with pytest.raises(ValueError):
        load_task("bad", tasks_dir=tmp_path)


def test_load_task_unknown_name_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="directory not found"):
        load_task("no-such-task", tasks_dir=tmp_path)


def test_tier_tasks_rejects_unknown_tier(tmp_path):
    with pytest.raises(ValueError):
        tier_tasks("bogus", tasks_dir=tmp_path)


def test_smoke_tasks_exist_in_repo():
    found = discover_tasks()
    for name in SMOKE_TASKS:
        assert name in found, f"missing smoke task {name!r}"


def test_repo_tasks_load_and_validate():
    for name in discover_tasks():
        t = load_task(name)
        assert t.brief, name
        assert len(t.brief) < 1200, f"{name}: brief should read like a real user prompt"
        assert t.spec["graders"], name


def test_washer_spec_grades_dimensions():
    t = load_task("washer-spec")
    kinds = {e["kind"] for e in t.spec["expected_dims"]}
    assert "hole" in kinds and "bbox_sorted" in kinds


def test_pi_case_has_containment_volume_and_timeout_override():
    t = load_task("pi-case")
    vols = t.spec["containment"]["volumes"]
    assert vols[0]["size_mm"] == [85, 56, 18]
    assert t.timeout_s == 1800


def test_full_tier_is_twelve_tasks():
    assert len(discover_tasks()) == 12


def test_gear_pair_checks_center_distance_and_engagement():
    t = load_task("gear-pair")
    cd = [e for e in t.spec["expected_dims"] if e["kind"] == "center_distance"]
    assert cd and cd[0]["expected"] == 50.0
    assert t.spec["motion"]["expect"] == "collides_within"


def test_hinge_motion_expects_clear_swing():
    t = load_task("hinge")
    assert t.spec["motion"]["expect"] == "clear_to"
    assert t.spec["motion"]["threshold_deg"] <= t.spec["motion"]["stop"]


def test_battery_box_contains_four_cells():
    t = load_task("battery-box")
    vols = t.spec["containment"]["volumes"]
    assert len(vols) == 4
    assert all(v["size_mm"] == [19, 19, 66] for v in vols)


def test_box_lid_fit_uses_min_clearance_requirement():
    t = load_task("box-lid-fit")
    fits = [r for r in t.spec["requirements"] if r.get("quantity") == "min_clearance"]
    assert fits and fits[0]["op"] == "within"


def test_tier_vocabulary(tmp_path):
    for name in ("washer-spec", "phone-stand", "pi-case", "extra"):
        _write_task(tmp_path, name)
    assert tier_tasks("smoke", tasks_dir=tmp_path) == SMOKE_TASKS
    assert tier_tasks("full", tasks_dir=tmp_path) == sorted(
        ["washer-spec", "phone-stand", "pi-case", "extra"]
    )
    assert SMOKE_TASKS == ["washer-spec", "phone-stand", "pi-case"]
    assert (
        frozenset(
            {
                "requirements",
                "dfm",
                "watertight",
                "interference",
                "stress",
                "dim_match",
                "containment",
                "stability",
                "motion",
            }
        )
        == KNOWN_GRADERS
    )
