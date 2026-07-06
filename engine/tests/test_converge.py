"""Tests for converge.py (Tasks 5 & 6).

Part A: pure helpers (candidate_grid, pick_feasible).
Part B: Session.converge_to_spec — non-destructive build + measure + select.
"""

import pytest

from solidifai_engine import converge
from solidifai_engine.session import Session

# ---------------------------------------------------------------------------
# Part A — pure helpers
# ---------------------------------------------------------------------------


def test_candidate_grid_respects_budget():
    params = {
        "wall": {"min": 1.0, "max": 3.0, "step": 0.5},
        "ribs": {"min": 0, "max": 4, "step": 1},
    }
    grid = converge.candidate_grid(params, max_evals=12)
    assert all(1.0 <= c["wall"] <= 3.0 for c in grid)
    assert len(grid) <= 12


def test_candidate_grid_skips_no_range_params():
    # A param with no min/max should be skipped (not in any candidate dict).
    params = {
        "wall": {"min": 1.0, "max": 3.0},
        "fixed": {"value": 5},  # no min/max
    }
    grid = converge.candidate_grid(params, max_evals=8)
    assert len(grid) > 0
    assert all("fixed" not in c for c in grid)


def test_candidate_grid_single_param():
    params = {"wall": {"min": 1.0, "max": 3.0, "step": 0.5}}
    grid = converge.candidate_grid(params, max_evals=24)
    assert len(grid) <= 24
    assert all(1.0 <= c["wall"] <= 3.0 for c in grid)


def test_candidate_grid_empty_when_no_range():
    params = {"fixed": {"value": 5}}
    assert converge.candidate_grid(params) == []


def test_pick_feasible_minimizes_objective():
    preds = [{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.2}]
    cands = [
        {"params": {"wall": 1.0}, "ok": True, "mass": 5, "min_wall": 1.0},
        {"params": {"wall": 1.5}, "ok": True, "mass": 7, "min_wall": 1.5},
        {"params": {"wall": 2.0}, "ok": True, "mass": 9, "min_wall": 2.0},
    ]
    best, feasible, closest = converge.pick_feasible(cands, preds, objective="min_mass")
    assert best["params"]["wall"] == 1.5  # lightest that meets min_wall >= 1.2
    assert feasible == 2


def test_pick_feasible_maximizes_mass():
    preds = [{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.2}]
    cands = [
        {"params": {"wall": 1.5}, "ok": True, "mass": 7, "min_wall": 1.5},
        {"params": {"wall": 2.0}, "ok": True, "mass": 9, "min_wall": 2.0},
    ]
    best, feasible, _ = converge.pick_feasible(cands, preds, objective="max_mass")
    assert best["params"]["wall"] == 2.0


def test_pick_feasible_none_returns_closest_miss():
    preds = [{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 5.0}]
    cands = [{"params": {"wall": 1.0}, "ok": True, "mass": 5, "min_wall": 1.0}]
    best, feasible, closest = converge.pick_feasible(cands, preds, objective="min_mass")
    assert best is None and feasible == 0 and closest is not None


def test_pick_feasible_empty_candidates():
    preds = [{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.2}]
    best, feasible, closest = converge.pick_feasible([], preds)
    assert best is None and feasible == 0 and closest is None


def test_pick_feasible_failed_candidates_ignored():
    # ok=False variants must not be selected.
    preds = [{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.2}]
    cands = [
        {"params": {"wall": 2.0}, "ok": False, "mass": 5, "min_wall": 2.0},
    ]
    best, feasible, closest = converge.pick_feasible(cands, preds)
    assert best is None and feasible == 0 and closest is None


# ---------------------------------------------------------------------------
# Part B — Session.converge_to_spec
# ---------------------------------------------------------------------------

# A parametric script where wall drives the actual wall thickness.
# The Box has wall thickness = wall (it's a hollow box with shell wall).
# Using a simpler approach: a solid box of side `wall` — min_wall_mm of a solid
# cube equals the side length, making it trivially predictable for tests.
WALL_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "wall": {"value": 1.0, "min": 0.8, "max": 5.0, "step": 0.1, "unit": "mm"},
}

def build(wall):
    with BuildPart() as p:
        Box(wall * 10, wall * 10, wall)
    show(p.part, name="Plate")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


@pytest.fixture
def wall_session(tmp_path):
    sess = Session(str(tmp_path))
    res = sess.execute_script(WALL_SCRIPT)
    assert res["ok"], f"wall_script build failed: {res}"
    return sess


def test_converge_to_spec_finds_feasible_wall(wall_session):
    s = wall_session
    # Require min_wall >= 1.5 mm; default wall=1.0 so it fails at current value.
    # The grid covers [0.8, 5.0], so values >= 1.5 satisfy it.
    s.set_requirements([{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.5}])
    rep = s.converge_to_spec()
    assert rep["ok"] is True
    assert rep["found"] is True
    assert rep["params"]["wall"] >= 1.5
    # Non-destructive: buildId is unchanged.
    assert s.build_id == rep["buildIdBefore"]


def test_converge_to_spec_non_destructive_build_id(wall_session):
    s = wall_session
    build_id_before = s.build_id
    s.set_requirements([{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.5}])
    rep = s.converge_to_spec()
    assert s.build_id == build_id_before
    assert rep["buildIdBefore"] == build_id_before


def test_converge_to_spec_no_feasible_returns_closest_miss(wall_session):
    s = wall_session
    # Require an impossibly large min_wall (beyond param max).
    s.set_requirements([{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 999.0}])
    rep = s.converge_to_spec()
    assert rep["ok"] is True
    assert rep["found"] is False
    assert rep["closestMiss"] is not None


def test_converge_to_spec_result_keys(wall_session):
    s = wall_session
    s.set_requirements([{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.5}])
    rep = s.converge_to_spec()
    for key in (
        "ok",
        "found",
        "buildIdBefore",
        "evaluated",
        "objective",
        "params",
        "before",
        "after",
        "closestMiss",
        "notAddressable",
    ):
        assert key in rep, f"missing key {key!r}"


def test_converge_to_spec_non_param_goal_in_not_addressable(tmp_path):
    # A mass requirement on a model where mass is constant across all param variants
    # (wall only varies height, so mass varies — but if we set a mass bound that
    # requires a value outside the param range it's still "addressable" because mass
    # varies). Instead test a truly static quantity: use a watertight requirement on
    # a solid model; manifold is True for all valid builds → constant → not addressable.
    sess = Session(str(tmp_path))
    res = sess.execute_script(WALL_SCRIPT)
    assert res["ok"]
    # Set a watertight requirement — the model is always watertight; the measured
    # value is True for every candidate. Since it never varies across params it should
    # land in notAddressable.
    sess.set_requirements([{"id": "wt", "quantity": "watertight", "op": "==", "bound": True}])
    rep = sess.converge_to_spec()
    assert rep["ok"] is True
    # notAddressable should mention the watertight requirement.
    ids_na = [r["id"] for r in rep["notAddressable"]]
    assert "wt" in ids_na


def test_converge_to_spec_apply_updates_params(wall_session):
    s = wall_session
    s.set_requirements([{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 2.0}])
    rep = s.converge_to_spec(apply=True)
    if rep["found"]:
        # apply=True should have called set_params, which bumps build_id.
        assert s.build_id > rep["buildIdBefore"]
        assert s._param_values["wall"] >= 2.0


def test_converge_to_spec_no_parametric_model(tmp_path):
    from tests.test_session import GOOD_SCRIPT  # noqa: PLC0415 - local import for test reuse

    sess = Session(str(tmp_path))
    sess.execute_script(GOOD_SCRIPT)
    rep = sess.converge_to_spec()
    assert rep["ok"] is False
    assert "error" in rep


def test_converge_to_spec_evaluated_count(wall_session):
    s = wall_session
    s.set_requirements([{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.5}])
    rep = s.converge_to_spec(max_evals=6)
    assert rep["evaluated"] <= 6
