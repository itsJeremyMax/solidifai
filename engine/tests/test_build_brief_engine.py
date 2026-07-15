"""Engine-side build brief: validate, persist, read back."""

from __future__ import annotations

import json

import pytest

from solidifai_engine import build_brief


def _good():
    return {
        "summary": "A lid + base box",
        "parts": [
            {"name": "base", "role": "holds contents", "why": "the body"},
            {"name": "lid", "role": "closes", "why": "lifts off"},
        ],
        "key_dims": [{"name": "wall", "value": 2.4, "unit": "mm", "drives": "wall"}],
        "interfaces": [{"between": ["lid", "base"], "kind": "press", "clearance": 0.2}],
        "make_real": "PLA FDM, 2.4 mm walls",
        "tier": "pause",
    }


def test_validate_normalizes_a_good_brief():
    norm = build_brief.validate(_good())
    assert norm["tier"] == "pause"
    assert [p["name"] for p in norm["parts"]] == ["base", "lid"]
    assert norm["interfaces"][0]["kind"] == "press"
    assert norm["key_dims"][0]["drives"] == "wall"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(tier="maybe"),  # bad tier
        lambda b: b.update(parts=[]),  # empty parts
        lambda b: b.update(summary=""),  # missing summary
        lambda b: b["interfaces"][0].update(kind="weld"),  # bad interface kind
        lambda b: b["interfaces"][0].update(between=["lid"]),  # between not a pair
        lambda b: b.update(key_dims=123),  # key_dims not a list
        lambda b: b.update(interfaces=123),  # interfaces not a list
        lambda b: b["interfaces"][0].update(between=[None, None]),  # between not strings
        lambda b: b["interfaces"][0].update(between=[1, 2]),  # between not strings
    ],
)
def test_validate_rejects_bad_shapes(mutate):
    b = _good()
    mutate(b)
    with pytest.raises(ValueError):
        build_brief.validate(b)


def test_validate_rejects_non_finite_numbers():
    for bad in (float("nan"), float("inf"), float("-inf"), {"x": 1}):
        b = _good()
        b["key_dims"][0]["value"] = bad
        with pytest.raises(ValueError):
            build_brief.validate(b)
        b = _good()
        b["interfaces"][0]["clearance"] = bad
        with pytest.raises(ValueError):
            build_brief.validate(b)
    # a normal float and None are both accepted
    ok = _good()
    ok["key_dims"][0]["value"] = 3.5
    ok["interfaces"][0]["clearance"] = None
    norm = build_brief.validate(ok)
    assert norm["key_dims"][0]["value"] == 3.5
    assert norm["interfaces"][0]["clearance"] is None


def test_validate_rejects_prose_blobs():
    """Prose fields carry a sentence or two; detail belongs in the structured
    fields, so a runaway blob is rejected with an actionable message."""
    b = _good()
    b["summary"] = "x" * (build_brief.MAX_SUMMARY + 1)
    with pytest.raises(ValueError, match="summary"):
        build_brief.validate(b)
    b = _good()
    b["make_real"] = "x" * (build_brief.MAX_PROSE + 1)
    with pytest.raises(ValueError, match="make_real"):
        build_brief.validate(b)
    b = _good()
    b["parts"][0]["why"] = "x" * (build_brief.MAX_PART_TEXT + 1)
    with pytest.raises(ValueError, match="why"):
        build_brief.validate(b)
    # exactly at the cap still passes
    ok = _good()
    ok["summary"] = "x" * build_brief.MAX_SUMMARY
    ok["make_real"] = "x" * build_brief.MAX_PROSE
    assert build_brief.validate(ok)["summary"] == ok["summary"]


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        ("part.name", lambda b: b["parts"][0].update(name="x" * (build_brief.MAX_PART_NAME + 1))),
        (
            "key_dim.name",
            lambda b: b["key_dims"][0].update(name="x" * (build_brief.MAX_DIM_NAME + 1)),
        ),
        ("key_dim.unit", lambda b: b["key_dims"][0].update(unit="x" * (build_brief.MAX_UNIT + 1))),
        (
            "key_dim.drives",
            lambda b: b["key_dims"][0].update(drives="x" * (build_brief.MAX_DIM_DRIVES + 1)),
        ),
        (
            "interface.between",
            lambda b: b["interfaces"][0].update(
                between=["x" * (build_brief.MAX_PART_NAME + 1), "base"]
            ),
        ),
    ],
)
def test_validate_rejects_oversized_structured_labels(field, mutate):
    b = _good()
    mutate(b)
    with pytest.raises(ValueError, match=field):
        build_brief.validate(b)


def test_validate_normalizes_interface_aliases():
    b = _good()
    b["interfaces"][0]["kind"] = "press-fit"
    assert build_brief.validate(b)["interfaces"][0]["kind"] == "press"
    b["interfaces"][0]["kind"] = "hinge"
    assert build_brief.validate(b)["interfaces"][0]["kind"] == "pivot"


def test_validate_v1_keeps_legacy_category_caps():
    brief = _good()
    brief["parts"] *= build_brief.MAX_PARTS + 1
    with pytest.raises(ValueError, match="too many parts"):
        build_brief.validate_v1(brief)


def test_write_then_load_roundtrips(tmp_path):
    root = str(tmp_path)
    norm = build_brief.write_build_brief(root, _good())
    assert norm["tier"] == "pause"
    on_disk = json.loads((tmp_path / "build_brief.json").read_text(encoding="utf-8"))
    assert on_disk["schema"] == build_brief.SCHEMA
    assert on_disk["summary"] == "A lid + base box"
    loaded = build_brief.load_build_brief(root)
    assert loaded["parts"][1]["name"] == "lid"


def test_load_missing_returns_none(tmp_path):
    assert build_brief.load_build_brief(str(tmp_path)) is None


def test_load_corrupt_returns_none(tmp_path):
    path = tmp_path / "build_brief.json"
    # corrupt / unparseable
    path.write_text("{not valid json", encoding="utf-8")
    assert build_brief.load_build_brief(str(tmp_path)) is None
    # empty file
    path.write_text("", encoding="utf-8")
    assert build_brief.load_build_brief(str(tmp_path)) is None
    # valid JSON but not an object (a list)
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert build_brief.load_build_brief(str(tmp_path)) is None


from solidifai_engine.server import _HANDLERS
from solidifai_engine.session import Session


def _sess(tmp_path):
    model_path = tmp_path / "model.py"
    model_path.write_text("from solidifai import *\n", encoding="utf-8")
    return Session(str(tmp_path / "artifacts"), model_path=str(model_path))


def test_session_propose_build_persists_and_reads_back(tmp_path):
    s = _sess(tmp_path)
    res = s.propose_build(_good())
    assert res["ok"] is True
    assert res["brief"]["tier"] == "pause"
    assert (tmp_path / "build_brief.json").exists()
    got = s.get_build_brief()
    assert got["ok"] is True
    assert got["brief"]["summary"] == "A lid + base box"


def test_session_get_build_brief_preserves_v1_for_legacy_and_migrates_for_v2(tmp_path):
    session = _sess(tmp_path)
    assert session.propose_build(_good())["ok"] is True

    legacy = session.get_build_brief()["brief"]
    capable = session.get_build_brief(target_schema=2)["brief"]

    assert legacy["schema"] == 1
    assert capable["schema"] == 2


def test_session_get_build_brief_none_when_absent(tmp_path):
    s = _sess(tmp_path)
    assert s.get_build_brief()["brief"] is None


def test_handlers_registered():
    assert "propose_build" in _HANDLERS
    assert "get_build_brief" in _HANDLERS


def test_protocol_bumped_for_new_handlers():
    # The build-brief handlers shipped in revision 8; a floor (not an exact pin)
    # so later contract changes can keep bumping without rewriting this test.
    from solidifai_engine.protocol import PROTOCOL_VERSION

    assert PROTOCOL_VERSION >= 8


def _v2(parts=None, interfaces=None, **overrides):
    brief = {
        "schema": 2,
        "revision": 0,
        "summary": "A modular enclosure",
        "tier": "stream",
        "parts": parts or [{"id": "base", "name": "Base", "children": []}],
        "requirements": [],
        "dimensions": [],
        "interfaces": interfaces or [],
        "references": [],
        "assumptions": [],
        "manufacturing": [],
        "obligations": [],
    }
    brief.update(overrides)
    return brief


def test_v1_read_as_v2_does_not_rewrite_disk(tmp_path):
    original = {
        "schema": 1,
        "summary": "box",
        "parts": [{"name": "base"}],
        "key_dims": [],
        "interfaces": [],
        "make_real": "FDM",
        "tier": "stream",
    }
    path = tmp_path / "build_brief.json"
    path.write_text(json.dumps(original), encoding="utf-8")

    migrated = build_brief.load_build_brief(str(tmp_path), target_schema=2)

    assert migrated["schema"] == 2
    assert migrated["parts"][0]["id"] == "base"
    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_v2_accepts_hierarchy_and_free_form_interface_kind():
    brief = _v2(
        parts=[
            {"id": "assembly", "name": "Assembly", "children": ["magnet"]},
            {"id": "magnet", "name": "Magnet", "children": []},
        ],
        interfaces=[{"id": "i1", "kind": "magnetic", "participants": ["assembly", "magnet"]}],
    )

    assert build_brief.validate_v2(brief)["interfaces"][0]["kind"] == "magnetic"


@pytest.mark.parametrize(
    "brief, match",
    [
        (
            _v2(parts=[{"id": "base", "name": "Base"}, {"id": "base", "name": "Lid"}]),
            "duplicate id",
        ),
        (_v2(parts=[{"id": "base", "name": "Base", "children": ["lid"]}]), "unknown part"),
    ],
)
def test_v2_rejects_invalid_references_and_risk_disposition(brief, match):
    with pytest.raises(ValueError, match=match):
        build_brief.validate_v2(brief)


@pytest.mark.parametrize(
    "assumption",
    [
        {
            "id": "style",
            "risk": "low",
            "statement": "Color is a reversible styling choice",
            "disposition": "implicit",
        },
        {
            "id": "fit",
            "risk": "functional",
            "statement": "Fit clearance is delegated to the user",
            "disposition": "delegated",
            "source": "user",
            "rationale": "User delegated fit choices",
        },
        {
            "id": "heat",
            "risk": "safety",
            "statement": "Maximum operating temperature is confirmed",
            "disposition": "confirmed",
            "source": "user",
            "rationale": "User confirmed temperature limit",
        },
        {
            "id": "cert",
            "risk": "compliance",
            "statement": "Certification target is delegated to the user",
            "disposition": "delegated",
            "source": "user",
            "rationale": "User owns certification target",
        },
    ],
)
def test_v2_accepts_risk_matrix_assumption_dispositions(assumption):
    normalized = build_brief.validate_v2(_v2(assumptions=[assumption]))

    assert normalized["assumptions"] == [assumption]


@pytest.mark.parametrize(
    "assumption, match",
    [
        (
            {
                "id": "fit",
                "risk": "functional",
                "statement": "Clearance must fit the mating part",
                "disposition": "implicit",
            },
            "delegated or confirmed",
        ),
        (
            {
                "id": "heat",
                "risk": "safety",
                "statement": "Maximum operating temperature is known",
                "disposition": "confirmed",
            },
            "source",
        ),
        (
            {
                "id": "cert",
                "risk": "compliance",
                "statement": "Certification target is delegated",
                "disposition": "delegated",
                "source": "user",
            },
            "rationale",
        ),
        (
            {
                "id": "unknown",
                "risk": "critical",
                "statement": "Unknown category",
                "disposition": "confirmed",
            },
            "risk",
        ),
    ],
)
def test_v2_rejects_assumptions_outside_risk_matrix(assumption, match):
    with pytest.raises(ValueError, match=match):
        build_brief.validate_v2(_v2(assumptions=[assumption]))


def test_v2_requires_a_non_empty_assumption_statement():
    with pytest.raises(ValueError, match="statement"):
        build_brief.validate_v2(
            _v2(
                assumptions=[
                    {
                        "id": "fit",
                        "risk": "functional",
                        "disposition": "confirmed",
                        "source": "user",
                        "rationale": "User confirmed the clearance",
                    }
                ]
            )
        )


def test_v2_normalizes_established_legacy_assumption_fields():
    normalized = build_brief.validate_v2(
        _v2(
            assumptions=[
                {
                    "id": "use",
                    "kind": "functional",
                    "text": "The user validated the intended use",
                    "disposition": "validated",
                }
            ]
        )
    )

    assert normalized["assumptions"] == [
        {
            "id": "use",
            "risk": "functional",
            "statement": "The user validated the intended use",
            "disposition": "confirmed",
            "source": "legacy-v2",
            "rationale": "Migrated legacy disposition: validated",
        }
    ]


def test_v2_normalizes_legacy_high_assumption_without_dropping_its_disposition():
    normalized = build_brief.validate_v2(
        _v2(assumptions=[{"id": "legacy-load", "risk": "high", "disposition": "validated"}])
    )

    assert normalized["assumptions"] == [
        {
            "id": "legacy-load",
            "risk": "functional",
            "statement": "legacy-load",
            "disposition": "confirmed",
            "source": "legacy-v2",
            "rationale": "Migrated legacy high-risk disposition: validated",
            "legacyDisposition": "validated",
        }
    ]


def test_load_normalizes_persisted_legacy_high_assumption(tmp_path):
    legacy = _v2(assumptions=[{"id": "legacy-load", "risk": "high", "disposition": "validated"}])
    (tmp_path / "build_brief.json").write_text(json.dumps(legacy), encoding="utf-8")

    loaded = build_brief.load_build_brief(str(tmp_path), target_schema=2)

    assert loaded["assumptions"][0]["risk"] == "functional"
    assert loaded["assumptions"][0]["source"] == "legacy-v2"


def test_load_normalizes_persisted_legacy_kind_and_name_assumption(tmp_path):
    legacy = _v2(
        assumptions=[
            {
                "id": "use",
                "kind": "safety",
                "name": "Safe handling",
                "disposition": "validated",
            }
        ]
    )
    (tmp_path / "build_brief.json").write_text(json.dumps(legacy), encoding="utf-8")

    loaded = build_brief.load_build_brief(str(tmp_path), target_schema=2)

    assert loaded["assumptions"][0]["risk"] == "safety"
    assert loaded["assumptions"][0]["statement"] == "Safe handling"


def test_v2_rejects_indirect_part_hierarchy_cycle():
    brief = _v2(
        parts=[
            {"id": "base", "name": "Base", "children": ["lid"]},
            {"id": "lid", "name": "Lid", "children": ["base"]},
        ]
    )

    with pytest.raises(ValueError, match="cycle"):
        build_brief.validate_v2(brief)


def test_v2_rejects_transport_safety_limits():
    too_deep = {"id": "base", "name": "Base", "metadata": {}}
    cursor = too_deep["metadata"]
    for _ in range(build_brief.MAX_NESTING_DEPTH):
        cursor["next"] = {}
        cursor = cursor["next"]
    with pytest.raises(ValueError, match="nesting"):
        build_brief.validate_v2(_v2(parts=[too_deep]))

    payload = _v2(summary="x" * build_brief.MAX_PAYLOAD_BYTES)
    with pytest.raises(ValueError, match="payload"):
        build_brief.validate_v2(payload)


def test_update_migrates_v1_persists_v2_and_increments_revision(tmp_path):
    build_brief.write_build_brief(str(tmp_path), _good())

    updated = build_brief.update_build_brief(
        str(tmp_path),
        "parts",
        [{"id": "lid", "name": "Lid", "children": []}],
        [],
        expected_revision=0,
    )

    assert updated["schema"] == 2
    assert updated["revision"] == 1
    assert {part["id"] for part in updated["parts"]} == {"base", "lid"}
    assert json.loads((tmp_path / "build_brief.json").read_text(encoding="utf-8"))["schema"] == 2
    with pytest.raises(ValueError, match="revision conflict"):
        build_brief.update_build_brief(str(tmp_path), "parts", [], [], expected_revision=0)


def test_v2_mutations_require_expected_revision(tmp_path):
    with pytest.raises(ValueError, match="expectedRevision is required"):
        build_brief.write_build_brief(str(tmp_path), _v2())

    build_brief.write_build_brief(str(tmp_path), _good())
    with pytest.raises(ValueError, match="expectedRevision is required"):
        build_brief.update_build_brief(str(tmp_path), "parts", [], [])


def test_v2_replacement_checks_expected_revision_and_increments_it(tmp_path):
    build_brief.write_build_brief(str(tmp_path), _good())

    replacement = build_brief.write_build_brief(str(tmp_path), _v2(), expected_revision=0)

    assert replacement["revision"] == 1
    with pytest.raises(ValueError, match="revision conflict"):
        build_brief.write_build_brief(str(tmp_path), _v2(), expected_revision=0)


def test_v1_unresolved_interface_migrates_and_allows_first_v2_mutation(tmp_path):
    legacy = _good()
    legacy["interfaces"] = [
        {"between": ["base", "external-latch"], "kind": "fixed", "clearance": None}
    ]
    build_brief.write_build_brief(str(tmp_path), legacy)

    migrated = build_brief.load_build_brief(str(tmp_path), target_schema=2)
    interface = migrated["interfaces"][0]
    assert interface["participants"] == ["base"]
    assert interface["unresolved_participants"] == ["external-latch"]
    assert interface["conformance"] == "unknown"

    updated = build_brief.update_build_brief(
        str(tmp_path),
        "obligations",
        [{"id": "verify-latch", "label": "Verify latch fit"}],
        [],
        expected_revision=0,
    )
    assert updated["revision"] == 1


def test_update_limits_items_and_handlers_are_registered():
    with pytest.raises(ValueError, match="too many update items"):
        build_brief.validate_update("parts", [{}] * (build_brief.MAX_UPDATE_ITEMS + 1), [])
    assert "update_build_brief" in _HANDLERS
