from solidifai_engine.conformance import aggregate_readiness, evaluate


def _brief(**overrides):
    brief = {
        "schema": 2,
        "parts": [{"id": "base", "name": "Base", "children": []}],
        "requirements": [],
        "dimensions": [],
        "interfaces": [],
        "references": [],
        "assumptions": [],
        "manufacturing": [],
        "obligations": [],
    }
    brief.update(overrides)
    return brief


def _finding(report, id):
    return next(item for item in report["findings"] if item["id"] == id)


def test_missing_required_reference_blocks_readiness():
    report = evaluate(
        _brief(references=[{"id": "board", "required": True}]), {"reference_status": {}}
    )
    assert _finding(report, "reference:board")["status"] == "unknown"
    assert _finding(report, "reference:board")["severity"] == "blocking"
    assert report["readiness"]["level"] == "blocked"


def test_optional_reference_failure_warns_without_blocking_readiness():
    report = evaluate(
        _brief(parts=[], references=[{"id": "board", "required": False}]),
        {"reference_status": {"board": {"status": "failed", "required": False}}},
    )

    assert _finding(report, "reference:board")["severity"] == "warning"
    assert report["readiness"]["level"] == "needs_attention"


def test_manifest_required_reference_failure_blocks_without_brief_obligation():
    report = evaluate(
        _brief(),
        {"reference_status": {"board": {"status": "failed", "required": True}}},
    )

    assert _finding(report, "reference:board")["severity"] == "blocking"
    assert report["readiness"]["level"] == "blocked"


def test_required_manifest_reference_merges_with_brief_without_duplicate_finding():
    report = evaluate(
        _brief(references=[{"id": "board", "required": False}]),
        {"reference_status": {"board": {"status": "failed", "required": True}}},
    )

    findings = [finding for finding in report["findings"] if finding["id"] == "reference:board"]
    assert len(findings) == 1
    assert findings[0]["severity"] == "blocking"


def test_empty_countable_requirements_are_unknown_not_ready():
    report = evaluate(
        _brief(requirements=[{"id": "functional", "required": True}]),
        {"requirements_report": {"results": []}},
    )
    assert _finding(report, "requirements:functional")["status"] == "unknown"


def test_readiness_uses_all_four_statuses():
    assert aggregate_readiness([{"status": "pass", "severity": "blocking"}])["level"] == "ready"
    assert (
        aggregate_readiness([{"status": "not_applicable", "severity": "blocking"}])["level"]
        == "ready"
    )
    assert (
        aggregate_readiness([{"status": "fail", "severity": "warning"}])["level"]
        == "needs_attention"
    )
    assert (
        aggregate_readiness([{"status": "unknown", "severity": "blocking"}])["level"] == "blocked"
    )


def test_evaluates_all_build_obligation_dimensions_with_stable_ids():
    brief = _brief(
        parts=[{"id": "base", "name": "Base", "children": []}],
        requirements=[{"id": "functional"}],
        dimensions=[{"id": "wall", "tolerance": 0.1}],
        interfaces=[{"id": "lid-fit", "participants": ["base", "lid"]}],
        references=[{"id": "board", "required": True}],
        assumptions=[{"id": "load", "kind": "safety"}],
        manufacturing=[{"id": "fdm", "required": True}],
        obligations=[{"id": "save", "kind": "persistence", "required": True}],
    )

    report = evaluate(
        brief,
        {
            "part_status": {"base": True},
            "requirements_report": {"results": [{"id": "functional", "pass": True}]},
            "dimension_status": {"wall": False},
            "interface_status": {"lid-fit": None},
            "reference_status": {"board": True},
            "assumption_status": {"load": None},
            "manufacturing_status": {"fdm": False},
            "persistence_status": {"save": True},
        },
    )

    assert _finding(report, "part:base")["status"] == "pass"
    assert _finding(report, "requirements:functional")["status"] == "pass"
    assert _finding(report, "dimension:wall")["status"] == "fail"
    assert _finding(report, "interface:lid-fit")["status"] == "unknown"
    assert _finding(report, "reference:board")["status"] == "pass"
    assert _finding(report, "assumption:load")["status"] == "unknown"
    assert _finding(report, "manufacturing:fdm")["status"] == "fail"
    assert _finding(report, "persistence:save")["status"] == "pass"
    assert report["readiness"] == {
        "level": "blocked",
        "findingIds": [
            "dimension:wall",
            "interface:lid-fit",
            "assumption:load",
            "manufacturing:fdm",
        ],
    }


def test_not_applicable_obligation_does_not_require_evidence():
    report = evaluate(
        _brief(manufacturing=[{"id": "cnc", "applicable": False}]),
        {"part_status": {"base": True}, "manufacturing_status": {}},
    )

    assert _finding(report, "manufacturing:cnc")["status"] == "not_applicable"
    assert report["readiness"]["level"] == "ready"


def test_missing_evidence_is_unknown_for_every_addressable_obligation():
    report = evaluate(
        _brief(
            parts=[{"id": "base", "name": "Base", "children": []}],
            features=[{"id": "boss"}],
            dimensions=[{"id": "wall", "drives": "wall_mm"}],
            interfaces=[{"id": "join", "participants": ["base", "lid"]}],
            references=[{"id": "drawing", "required": True}],
            requirements=[{"id": "functional"}],
            assumptions=[{"id": "usage", "kind": "functional"}],
            manufacturing=[{"id": "fdm"}],
            obligations=[{"id": "durable", "kind": "persistence"}],
        ),
        {},
    )

    assert [finding["id"] for finding in report["findings"]] == [
        "part:base",
        "feature:boss",
        "dimension:wall",
        "parameter-binding:wall",
        "interface:join",
        "reference:drawing",
        "requirements:functional",
        "assumption:usage",
        "manufacturing:fdm",
        "persistence:durable",
    ]
    assert {finding["status"] for finding in report["findings"]} == {"unknown"}
    assert report["readiness"]["level"] == "blocked"


def test_confirmed_matrix_assumption_is_addressable_by_its_stable_id():
    report = evaluate(
        _brief(
            assumptions=[
                {
                    "id": "heat-limit",
                    "risk": "safety",
                    "disposition": "confirmed",
                    "source": "user",
                    "rationale": "User confirmed the operating temperature",
                }
            ]
        ),
        {"assumption_status": {"heat-limit": True}},
    )

    assert _finding(report, "assumption:heat-limit")["status"] == "pass"
