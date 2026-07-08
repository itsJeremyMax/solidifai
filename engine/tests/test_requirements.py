"""Design requirements: evaluation against measured context + persistence."""

import solidifai_engine.requirements as req
from solidifai_engine import requirements as rq


def test_max_mass_pass_and_fail():
    ctx = {"mass": 42.0, "bbox": [10, 10, 10], "manifold": True}
    assert req.evaluate([{"id": "a", "type": "max_mass", "target": 50}], ctx)[0]["pass"] is True
    assert req.evaluate([{"id": "a", "type": "max_mass", "target": 40}], ctx)[0]["pass"] is False


def test_min_mass():
    ctx = {"mass": 42.0}
    assert req.evaluate([{"id": "a", "type": "min_mass", "target": 40}], ctx)[0]["pass"] is True
    assert req.evaluate([{"id": "a", "type": "min_mass", "target": 50}], ctx)[0]["pass"] is False


def test_max_size_fails_one_axis_with_detail():
    ctx = {"mass": 1, "bbox": [58, 39.5, 22.1], "manifold": True}
    r = req.evaluate([{"id": "s", "type": "max_size", "target": [60, 40, 20]}], ctx)[0]
    assert r["pass"] is False
    assert "Z" in r["detail"]


def test_max_size_passes_when_within():
    ctx = {"bbox": [58, 39.5, 19.0]}
    assert (
        req.evaluate([{"id": "s", "type": "max_size", "target": [60, 40, 20]}], ctx)[0]["pass"]
        is True
    )


def test_watertight_and_printable():
    ctx = {"mass": 1, "bbox": [1, 1, 1], "manifold": False, "dfmCritical": 2}
    rs = req.evaluate(
        [
            {"id": "w", "type": "watertight", "target": None},
            {"id": "p", "type": "printable", "target": None},
        ],
        ctx,
    )
    assert rs[0]["pass"] is False
    assert rs[1]["pass"] is False


def test_no_interference():
    assert (
        req.evaluate([{"id": "n", "type": "no_interference", "target": None}], {"overlaps": 0})[0][
            "pass"
        ]
        is True
    )
    assert (
        req.evaluate([{"id": "n", "type": "no_interference", "target": None}], {"overlaps": 3})[0][
            "pass"
        ]
        is False
    )


def test_pass_null_without_measurement():
    r = req.evaluate([{"id": "a", "type": "max_mass", "target": 50}], {})[0]
    assert r["pass"] is None


def test_disabled_requirement_skipped():
    ctx = {"mass": 1}
    out = req.evaluate([{"id": "a", "type": "max_mass", "target": 50, "enabled": False}], ctx)
    assert out == []


def test_needs():
    reqs = [{"type": "printable", "target": None, "enabled": True}]
    assert req.needs(reqs, "printable") is True
    assert req.needs(reqs, "no_interference") is False


def test_persistence_roundtrip(tmp_path):
    reqs = [{"id": "a", "type": "max_mass", "target": 50, "enabled": True}]
    req.write_requirements(str(tmp_path), reqs)
    assert req.load_requirements(str(tmp_path)) == reqs


def test_load_malformed_returns_empty(tmp_path):
    (tmp_path / "requirements.json").write_text("{ not json")
    assert req.load_requirements(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# Task 1: Predicate model + quantity registry
# ---------------------------------------------------------------------------


def test_predicate_le_boundary():
    r = {"id": "a", "quantity": "mass", "op": "<=", "bound": 50}
    assert rq.evaluate([r], {"mass": 50})[0]["pass"] is True
    assert rq.evaluate([r], {"mass": 50.1})[0]["pass"] is False


def test_predicate_ge_and_within():
    ge = {"id": "b", "quantity": "min_wall", "op": ">=", "bound": 1.2}
    assert rq.evaluate([ge], {"min_wall": 1.2})[0]["pass"] is True
    assert rq.evaluate([ge], {"min_wall": 1.0})[0]["pass"] is False
    win = {"id": "c", "quantity": "min_clearance", "op": "within", "bound": [0.2, 0.4]}
    assert rq.evaluate([win], {"min_clearance": 0.3})[0]["pass"] is True
    assert rq.evaluate([win], {"min_clearance": 0.5})[0]["pass"] is False


def test_predicate_size_vector_le_per_axis():
    r = {"id": "d", "quantity": "size", "op": "<=", "bound": [60, 40, 20]}
    assert rq.evaluate([r], {"bbox": [58, 39, 19]})[0]["pass"] is True
    res = rq.evaluate([r], {"bbox": [58, 39, 22]})[0]
    assert res["pass"] is False and "Z" in res["detail"]


def test_predicate_missing_measurement_is_null():
    r = {"id": "e", "quantity": "mass", "op": "<=", "bound": 50}
    assert rq.evaluate([r], {})[0]["pass"] is None


def test_size_within_flat_bound_is_null_not_crash():
    # A `within` on a vector quantity needs a [lo, hi] pair per axis; a flat
    # [lo, hi] bound is the wrong shape and must read as unmeasured, not raise.
    r = {"id": "z", "quantity": "size", "op": "within", "bound": [10, 40]}
    assert rq.evaluate([r], {"bbox": [20, 20, 20]})[0]["pass"] is None


def test_scalar_within_flat_bound_is_null_not_crash():
    # A scalar `within` needs a [lo, hi] pair; a bare scalar bound is the wrong
    # shape and must read as unmeasured, not raise (matches the vector branch).
    r = {"id": "z", "quantity": "min_wall", "op": "within", "bound": 2}
    assert rq.evaluate([r], {"min_wall": 1.2})[0]["pass"] is None


def test_size_within_per_axis_pairs():
    r = {
        "id": "z",
        "quantity": "size",
        "op": "within",
        "bound": [[10, 40], [10, 40], [10, 40]],
    }
    assert rq.evaluate([r], {"bbox": [20, 20, 20]})[0]["pass"] is True
    res = rq.evaluate([r], {"bbox": [20, 50, 20]})[0]
    assert res["pass"] is False and "Y" in res["detail"]


def test_predicate_ok_rejects_bad_bound_shapes():
    # size + within needs per-axis pairs, not a flat pair
    assert rq.predicate_ok({"quantity": "size", "op": "within", "bound": [10, 40]}) is False
    assert (
        rq.predicate_ok(
            {"quantity": "size", "op": "within", "bound": [[10, 40], [10, 40], [10, 40]]}
        )
        is True
    )
    # size + <= needs three scalars
    assert rq.predicate_ok({"quantity": "size", "op": "<=", "bound": [60, 40, 20]}) is True
    assert rq.predicate_ok({"quantity": "size", "op": "<=", "bound": 60}) is False
    # scalar quantity: within needs a pair, others need a scalar
    assert rq.predicate_ok({"quantity": "mass", "op": "<=", "bound": 50}) is True
    assert (
        rq.predicate_ok({"quantity": "min_clearance", "op": "within", "bound": [0.2, 0.4]}) is True
    )
    assert rq.predicate_ok({"quantity": "mass", "op": "within", "bound": 50}) is False


# ---------------------------------------------------------------------------
# Task 2: Legacy migration + restricted assert
# ---------------------------------------------------------------------------


def test_migrate_legacy_types():
    legacy = [
        {"id": "1", "type": "max_mass", "target": 50},
        {"id": "2", "type": "min_mass", "target": 10},
        {"id": "3", "type": "max_size", "target": [60, 40, 20]},
        {"id": "4", "type": "printable"},
        {"id": "5", "type": "no_interference"},
        {"id": "6", "type": "watertight"},
    ]
    out = rq.migrate_legacy(legacy)
    assert out[0] == {"id": "1", "quantity": "mass", "op": "<=", "bound": 50, "enabled": True}
    assert out[1]["quantity"] == "mass" and out[1]["op"] == ">="
    assert out[2]["quantity"] == "size" and out[2]["op"] == "<="
    assert out[3] == {
        "id": "4",
        "quantity": "dfm_critical",
        "op": "<=",
        "bound": 0,
        "enabled": True,
    }
    assert out[4]["quantity"] == "overlaps"
    assert out[5] == {
        "id": "6",
        "quantity": "watertight",
        "op": "==",
        "bound": True,
        "enabled": True,
    }


def test_assert_predicate_restricted():
    ok = {"id": "x", "kind": "assert", "expr": "mass < 50", "label": "light"}
    assert rq.evaluate([ok], {"mass": 42})[0]["pass"] is True
    assert rq.evaluate([ok], {"mass": 60})[0]["pass"] is False
    bad = {"id": "y", "kind": "assert", "expr": "__import__('os').system('x')", "label": "evil"}
    res = rq.evaluate([bad], {"mass": 1})[0]
    assert res["pass"] is None and res["detail"]  # refused, never executed


# ---------------------------------------------------------------------------
# Task 3: Regression delta + state persistence
# ---------------------------------------------------------------------------


def test_regression_delta():
    prev = [{"id": "1", "pass": True}, {"id": "2", "pass": False}, {"id": "9", "pass": True}]
    curr = [{"id": "1", "pass": False}, {"id": "2", "pass": True}, {"id": "3", "pass": True}]
    deltas = rq.diff_results(prev, curr)
    by = {d["id"]: d["delta"] for d in deltas}
    assert by["1"] == "regressed"
    assert by["2"] == "fixed"
    assert by["3"] == "new"
    summary = rq.delta_summary(deltas)
    assert summary["regressed"] == 1 and summary["fixed"] == 1


def test_regression_no_previous_all_unchanged():
    curr = [{"id": "1", "pass": True}]
    assert rq.diff_results(None, curr)[0]["delta"] == "unchanged"
