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


def test_validate_normalizes_interface_aliases():
    b = _good()
    b["interfaces"][0]["kind"] = "press-fit"
    assert build_brief.validate(b)["interfaces"][0]["kind"] == "press"
    b["interfaces"][0]["kind"] = "hinge"
    assert build_brief.validate(b)["interfaces"][0]["kind"] == "pivot"


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
