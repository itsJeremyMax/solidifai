import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidifai_engine import session as session_module
from solidifai_engine.session import Session

MODEL = """
from build123d import Box, BuildPart, Hole, Locations, Pos
from solidifai import feature, show

PARAMS = {"width": {"value": 20, "min": 1, "max": 100, "step": 1, "unit": "mm"}}

def build(width):
    with BuildPart() as base:
        Box(width, 20, 10)
        with feature("bore", kind="hole", driven_by="width"), Locations((0, 0)):
            Hole(radius=2)
    show(base.part, name="base")
    show(Pos(30, 0, 0) * Box(10, 10, 10), name="cap")
"""


def _brief(**changes):
    brief = {
        "schema": 2,
        "summary": "Measured two-part enclosure",
        "tier": "stream",
        "parts": [
            {"id": "base", "name": "Base", "children": []},
            {"id": "cap", "name": "Cap", "children": []},
        ],
        "features": [{"id": "bore", "kind": "hole"}],
        "requirements": [],
        "dimensions": [
            {"id": "width", "drives": "width", "value": 20, "tolerance": 0.01},
            {
                "id": "gap",
                "measure": {"a": "base", "b": "cap", "mode": "min"},
                "value": 15,
                "tolerance": 0.01,
            },
        ],
        "interfaces": [
            {
                "id": "base-cap",
                "kind": "fixed",
                "participants": ["base", "cap"],
                "check": "no_interference",
            }
        ],
        "references": [],
        "assumptions": [{"id": "use", "kind": "functional", "disposition": "validated"}],
        "manufacturing": [{"id": "fdm", "process": "fdm"}],
        "obligations": [{"id": "model", "kind": "persistence"}],
    }
    brief.update(changes)
    return brief


def _session(tmp_path: Path, brief: dict) -> Session:
    root = tmp_path / "widget"
    root.mkdir(parents=True)
    session = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert session.execute_script(MODEL)["ok"] is True
    proposed = session.propose_build(brief, expected_revision=0)
    assert proposed["ok"] is True, proposed
    return session


def _finding(session: Session, finding_id: str) -> dict:
    return next(item for item in session.get_conformance()["findings"] if item["id"] == finding_id)


def test_snapshot_evidence_makes_complete_v2_brief_ready(tmp_path):
    session = _session(tmp_path, _brief())

    report = session.get_conformance()

    assert report["readiness"] == {"level": "ready", "findingIds": []}, report
    assert {item["status"] for item in report["findings"]} == {"pass"}


def test_snapshot_part_dimension_and_interface_evidence_can_fail_independently(tmp_path):
    missing_part = _session(
        tmp_path / "part",
        _brief(parts=[{"id": "missing", "name": "Missing", "children": []}], interfaces=[]),
    )
    wrong_dimension = _session(
        tmp_path / "dimension",
        _brief(dimensions=[{"id": "width", "drives": "width", "value": 21, "tolerance": 0.01}]),
    )
    unmeasurable_dimension = _session(
        tmp_path / "dimension-unknown",
        _brief(dimensions=[{"id": "unmeasurable"}]),
    )
    overlapping = _session(
        tmp_path / "interface",
        _brief(
            interfaces=[
                {
                    "id": "base-cap",
                    "kind": "fixed",
                    "participants": ["base", "cap"],
                    "check": "no_interference",
                }
            ]
        ),
    )
    overlapping.execute_script(MODEL.replace("Pos(30, 0, 0)", "Pos(5, 0, 0)"))
    unspecified_interface = _session(
        tmp_path / "interface-unknown",
        _brief(interfaces=[{"id": "base-cap", "kind": "fixed", "participants": ["base", "cap"]}]),
    )

    assert _finding(missing_part, "part:missing")["status"] == "fail"
    assert _finding(wrong_dimension, "dimension:width")["status"] == "fail"
    assert _finding(unmeasurable_dimension, "dimension:unmeasurable")["status"] == "unknown"
    assert _finding(overlapping, "interface:base-cap")["status"] == "fail"
    assert _finding(unspecified_interface, "interface:base-cap")["status"] == "unknown"


def test_snapshot_feature_assumption_and_manufacturing_evidence_reports_absence_or_unknown(
    tmp_path,
):
    missing_feature = _session(
        tmp_path / "feature", _brief(features=[{"id": "slot", "kind": "slot"}])
    )
    unresolved_assumption = _session(
        tmp_path / "assumption",
        _brief(assumptions=[{"id": "use", "kind": "functional"}]),
    )
    unsupported_process = _session(
        tmp_path / "manufacturing",
        _brief(manufacturing=[{"id": "laser", "process": "laser"}]),
    )
    critical_limit = _session(
        tmp_path / "manufacturing-fail",
        _brief(manufacturing=[{"id": "fdm", "process": "fdm", "maxCritical": -1}]),
    )

    assert _finding(missing_feature, "feature:slot")["status"] == "fail"
    assert _finding(unresolved_assumption, "assumption:use")["status"] == "unknown"
    assert _finding(unsupported_process, "manufacturing:laser")["status"] == "unknown"
    assert _finding(critical_limit, "manufacturing:fdm")["status"] == "fail"


def test_persistence_hash_matches_committed_source_and_stale_edit_blocks_strict_export(tmp_path):
    session = _session(tmp_path, _brief())

    assert _finding(session, "persistence:model")["status"] == "pass"
    assert session.export("stl", "matching.stl", strict_export=True)["ok"] is True

    Path(session.model_path).write_text(MODEL + "\n# edited outside the engine\n", encoding="utf-8")

    assert _finding(session, "persistence:model")["status"] == "fail"
    assert session.export("stl", "stale.stl", strict_export=True) == {
        "ok": False,
        "error": "export blocked by readiness",
        "findingIds": ["persistence:model"],
    }


def test_persistence_evidence_handles_unsaved_missing_and_unreadable_source(tmp_path, monkeypatch):
    session = _session(tmp_path, _brief())
    model_path = Path(session.model_path)

    assert session._persistence_evidence() is True
    model_path.unlink()
    assert session._persistence_evidence() is False

    model_path.write_text(MODEL, encoding="utf-8")
    monkeypatch.setattr(
        session_module.os,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()),
    )
    assert session._persistence_evidence() is None

    unsaved = Session(str(tmp_path / "bare-artifacts"))
    assert unsaved._persistence_evidence() is None


def test_persistence_evidence_rejects_source_that_changes_while_hashed(tmp_path, monkeypatch):
    session = _session(tmp_path, _brief())
    real_fstat = session_module.os.fstat
    calls = 0

    def changed_fstat(descriptor):
        nonlocal calls
        calls += 1
        stat = real_fstat(descriptor)
        if calls == 2:
            return SimpleNamespace(
                st_dev=stat.st_dev,
                st_ino=stat.st_ino,
                st_size=stat.st_size + 1,
                st_mtime_ns=stat.st_mtime_ns,
            )
        return stat

    monkeypatch.setattr(session_module.os, "fstat", changed_fstat)

    assert session._persistence_evidence() is None


def test_persisted_v2_brief_without_a_build_reports_blocking_unknowns(tmp_path):
    root = tmp_path / "unbuilt"
    root.mkdir()
    session = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert session.propose_build(_brief(), expected_revision=0)["ok"] is True

    report = session.get_conformance()

    assert report["readiness"]["level"] == "blocked"
    assert _finding(session, "part:base")["status"] == "unknown"
    assert _finding(session, "persistence:model")["status"] == "unknown"


def test_conformance_and_strict_export_normalize_persisted_legacy_v2_assumptions(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    session = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert session.execute_script(MODEL)["ok"] is True
    (root / "build_brief.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "revision": 0,
                "summary": "Legacy assumption",
                "tier": "stream",
                "parts": [],
                "features": [],
                "requirements": [],
                "dimensions": [],
                "interfaces": [],
                "references": [],
                "assumptions": [{"id": "use", "kind": "functional", "disposition": "validated"}],
                "manufacturing": [],
                "obligations": [],
            }
        ),
        encoding="utf-8",
    )

    brief = session.get_build_brief(target_schema=2)["brief"]

    assert brief["assumptions"][0]["risk"] == "functional"
    assert brief["assumptions"][0]["statement"] == "use"
    assert session.get_readiness() == {"level": "ready", "findingIds": []}
    assert session.export("stl", "legacy.stl", strict_export=True)["ok"] is True


@pytest.mark.parametrize(
    ("legacy_disposition", "normalized_disposition", "ready"),
    [
        ("validated", "confirmed", True),
        ("confirmed", "confirmed", True),
        ("delegated", "delegated", True),
        ("unknown", "unknown", False),
        ("unverified", "unknown", False),
        ("rejected", "unknown", False),
        ("", "unknown", False),
        ("arbitrary", "unknown", False),
    ],
)
def test_persisted_legacy_high_dispositions_are_allowlisted_for_readiness_and_export(
    tmp_path, legacy_disposition, normalized_disposition, ready
):
    root = tmp_path / "legacy-high"
    root.mkdir()
    session = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "model.py"))
    assert session.execute_script(MODEL)["ok"] is True
    (root / "build_brief.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "revision": 0,
                "summary": "Legacy high-risk assumption",
                "tier": "stream",
                "parts": [],
                "features": [],
                "requirements": [],
                "dimensions": [],
                "interfaces": [],
                "references": [],
                "assumptions": [
                    {"id": "legacy-load", "risk": "high", "disposition": legacy_disposition}
                ],
                "manufacturing": [],
                "obligations": [],
            }
        ),
        encoding="utf-8",
    )

    assumption = session.get_build_brief(target_schema=2)["brief"]["assumptions"][0]
    export = session.export("stl", "legacy-high.stl", strict_export=True)

    assert assumption["legacyDisposition"] == legacy_disposition
    assert assumption["risk"] == "functional"
    assert assumption["disposition"] == normalized_disposition
    if ready:
        assert session.get_readiness() == {"level": "ready", "findingIds": []}
        assert export["ok"] is True
    else:
        assert session.get_readiness() == {
            "level": "blocked",
            "findingIds": ["assumption:legacy-load"],
        }
        assert export == {
            "ok": False,
            "error": "export blocked by readiness",
            "findingIds": ["assumption:legacy-load"],
        }
