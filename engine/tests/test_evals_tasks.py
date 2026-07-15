"""Golden-task loading + spec schema validation for the eval harness."""

import json
from copy import deepcopy

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


def test_validate_spec_requires_typed_semantics_for_new_non_calibration_specs():
    spec = {"schema": 2, "graders": ["semantic"]}
    assert "semantic_requirements" in "; ".join(validate_spec(spec))


def test_validate_spec_rejects_malformed_semantic_requirements():
    spec = {
        "schema": 2,
        "graders": ["semantic"],
        "semantic_requirements": [
            {"id": "parts", "kind": "part_count", "count": float("inf")},
            {"id": "parts", "kind": "part_name", "name": "base", "extra": True},
        ],
    }
    msgs = "; ".join(validate_spec(spec))
    assert "semantic requirement 'parts'" in msgs
    assert "duplicate semantic requirement id 'parts'" in msgs


def test_validate_spec_accepts_all_supported_semantic_kinds():
    spec = {
        "schema": 2,
        "graders": ["semantic"],
        "semantic_requirements": [
            {"id": "parts", "kind": "part_count", "count": 2},
            {"id": "base", "kind": "part_name", "name": "base"},
            {"id": "boss", "kind": "feature", "name": "boss"},
            {
                "id": "holes",
                "kind": "hole_pattern",
                "count": 4,
                "diameter_mm": 3,
                "tolerance_mm": 0.1,
            },
            {"id": "cavity", "kind": "cavity", "size_mm": [10, 10, 10], "tolerance_mm": 0.1},
            {
                "id": "regions",
                "kind": "cavity_pattern",
                "size_mm": [[10, 10, 10], [12, 8, 6]],
                "centers_mm": [[-8, 0, 0], [8, 0, 0]],
                "tolerance_mm": 0.1,
            },
            {"id": "joint", "kind": "interface", "parts": ["base", "lid"]},
            {
                "id": "swing",
                "kind": "motion",
                "part": "lid",
                "range_deg": [0, 90],
            },
            {
                "id": "bracket",
                "kind": "l_bracket",
                "name": "bracket",
                "mount_axis": "x",
                "span_axis": "y",
                "rise_axis": "z",
                "min_mount_thickness_mm": 5,
                "min_span_mm": 40,
                "min_rise_mm": 45,
                "min_projection_mm": 20,
                "tolerance_mm": 0.5,
            },
        ],
    }
    assert validate_spec(spec) == []


@pytest.mark.parametrize(
    ("requirement", "message"),
    [
        ({"id": "x", "kind": "part_count", "count": 2, "min": 1, "max": 3}, "count"),
        ({"id": "x", "kind": "part_count", "min": 3, "max": 2}, "min"),
        ({"id": "x", "kind": "part_count", "count": True}, "integer"),
        ({"id": "x", "kind": "part_name", "name": "base", "count": True}, "count"),
        ({"id": "x", "kind": "part_faces", "name": "base", "min": True}, "min"),
        ({"id": "x", "kind": "feature", "name": "boss", "metric": "area"}, "metric"),
        ({"id": "x", "kind": "feature", "name": "boss", "range": [1, 2]}, "metric"),
        (
            {
                "id": "x",
                "kind": "hole_pattern",
                "count": True,
                "diameter_mm": 3,
                "tolerance_mm": 0.1,
            },
            "count",
        ),
        (
            {"id": "x", "kind": "cavity", "size_mm": [1, 1, 1], "tolerance_mm": float("inf")},
            "tolerance",
        ),
        (
            {
                "id": "x",
                "kind": "cavity_pattern",
                "size_mm": [[10, 10, 10]],
                "centers_mm": [[0, 0, 0], [10, 0, 0]],
                "tolerance_mm": 0.1,
            },
            "size_mm",
        ),
        ({"id": "x", "kind": "interface", "parts": ["a", "b"], "tolerance_mm": False}, "tolerance"),
        (
            {"id": "x", "kind": "motion", "part": "lid", "axis": [0, 0, 1], "range_deg": [0, 90]},
            "invalid kind or keys",
        ),
        (
            {
                "id": "x",
                "kind": "l_bracket",
                "name": "bracket",
                "mount_axis": "x",
                "span_axis": "x",
                "rise_axis": "z",
                "min_mount_thickness_mm": 5,
                "min_span_mm": 40,
                "min_rise_mm": 45,
                "min_projection_mm": 20,
                "tolerance_mm": 0.5,
            },
            "distinct axes",
        ),
    ],
)
def test_validate_spec_rejects_ambiguous_or_unused_semantic_fields(requirement, message):
    spec = {"schema": 2, "graders": ["semantic"], "semantic_requirements": [deepcopy(requirement)]}
    assert message in "; ".join(validate_spec(spec))


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
                "semantic",
            }
        )
        == KNOWN_GRADERS
    )
