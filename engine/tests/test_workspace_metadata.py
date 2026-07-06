import json

from solidifai_engine import workspace_metadata as wm
from solidifai_engine.server import _HANDLERS
from solidifai_engine.session import Session


def test_load_missing_returns_defaults(tmp_path):
    m = wm.load_metadata(str(tmp_path))
    assert m["name"] == ""
    assert m["description"] == ""
    assert m["descriptionSource"] == "sol"
    assert m["tags"] == []
    assert m["tagsSource"] == "sol"
    assert m["proposedName"] is None
    assert m["proposedNameDismissed"] is None


def test_write_then_load_round_trips_and_is_schema_tagged(tmp_path):
    m = wm.defaults()
    m["name"] = "Gearbox"
    m["description"] = "A reducer."
    m["tags"] = ["gears"]
    wm.write_metadata(str(tmp_path), m)
    data = json.loads((tmp_path / "workspace.json").read_text(encoding="utf-8"))
    assert data["schema"] == 1
    assert data["name"] == "Gearbox"
    assert wm.load_metadata(str(tmp_path))["tags"] == ["gears"]


def test_normalize_tags_lowercases_trims_dedupes_and_caps():
    extra = [f"t{i}" for i in range(20)]
    out = wm.normalize_tags(["  Gears ", "gears", "ENCLOSURE", "", "x" * 40] + extra)
    assert out[0] == "gears"
    assert "enclosure" in out
    assert "" not in out
    assert all(len(t) <= 24 for t in out)
    assert len(out) <= 12


def test_normalize_description_trims_and_caps():
    assert wm.normalize_description("  hi  ") == "hi"
    assert len(wm.normalize_description("x" * 500)) == 280


def test_proactive_patch_skips_user_owned_fields():
    cur = wm.defaults()
    cur["description"] = "mine"
    cur["descriptionSource"] = "user"
    out = wm.apply_patch(cur, {"description": "sol text"}, force=False)
    assert out["description"] == "mine"


def test_force_patch_overrides_user_field_and_reclaims_source():
    cur = wm.defaults()
    cur["description"] = "mine"
    cur["descriptionSource"] = "user"
    out = wm.apply_patch(cur, {"description": "sol text"}, force=True)
    assert out["description"] == "sol text"
    assert out["descriptionSource"] == "sol"


def test_proactive_patch_writes_empty_or_sol_owned_fields():
    cur = wm.defaults()
    out = wm.apply_patch(cur, {"description": "first", "tags": ["a"]}, force=False)
    assert out["description"] == "first"
    assert out["tags"] == ["a"]
    assert out["tagsSource"] == "sol"


def test_user_patch_marks_source_user():
    cur = wm.defaults()
    out = wm.apply_user_patch(cur, {"description": "typed", "tags": ["b"]})
    assert out["descriptionSource"] == "user"
    assert out["tagsSource"] == "user"


def test_proposed_name_dropped_when_equal_to_name():
    cur = wm.defaults()
    cur["name"] = "Gearbox"
    out = wm.apply_patch(cur, {"proposedName": " gearbox "}, force=False)
    assert out["proposedName"] is None


def test_proposed_name_dropped_when_equal_to_dismissed():
    cur = wm.defaults()
    cur["proposedNameDismissed"] = "Cycloidal Drive"
    out = wm.apply_patch(cur, {"proposedName": "cycloidal drive"}, force=False)
    assert out["proposedName"] is None


def test_proposed_name_accepted_when_distinct():
    cur = wm.defaults()
    cur["name"] = "Gearbox"
    out = wm.apply_patch(cur, {"proposedName": "Cycloidal Drive"}, force=False)
    assert out["proposedName"] == "Cycloidal Drive"


def test_set_name_clears_proposal_and_rejects_empty():
    cur = wm.defaults()
    cur["proposedName"] = "Cycloidal Drive"
    out = wm.set_name(cur, "Cycloidal Drive")
    assert out["name"] == "Cycloidal Drive"
    assert out["proposedName"] is None
    try:
        wm.set_name(cur, "   ")
        raise AssertionError("empty name should raise")
    except ValueError:
        pass


def test_dismiss_moves_proposal_to_dismissed():
    cur = wm.defaults()
    cur["proposedName"] = "Cycloidal Drive"
    out = wm.dismiss_proposed_name(cur)
    assert out["proposedName"] is None
    assert out["proposedNameDismissed"] == "Cycloidal Drive"


# --- Session integration tests ---


def _sess(tmp_path):
    model_path = tmp_path / "model.py"
    model_path.write_text("from solidifai import *\n", encoding="utf-8")
    return Session(str(tmp_path / "artifacts"), model_path=str(model_path))


def test_session_get_returns_metadata(tmp_path):
    s = _sess(tmp_path)
    res = s.get_workspace_meta()
    assert res["ok"] is True
    assert res["metadata"]["tags"] == []


def test_session_set_meta_proactive_persists(tmp_path):
    s = _sess(tmp_path)
    res = s.set_workspace_meta({"description": "d", "tags": ["a", "a", "B"]})
    assert res["ok"] is True
    assert res["metadata"]["description"] == "d"
    assert res["metadata"]["tags"] == ["a", "b"]
    assert wm.load_metadata(str(tmp_path))["description"] == "d"


def test_session_set_meta_respects_user_provenance(tmp_path):
    s = _sess(tmp_path)
    s.set_workspace_meta({"description": "typed"}, user=True)
    res = s.set_workspace_meta({"description": "sol"}, force=False)
    assert res["metadata"]["description"] == "typed"


def test_session_set_name_clears_proposal(tmp_path):
    s = _sess(tmp_path)
    s.set_workspace_meta({"proposedName": "Cycloidal Drive"})
    res = s.set_workspace_name("Cycloidal Drive")
    assert res["ok"] is True
    assert res["name"] == "Cycloidal Drive"
    assert wm.load_metadata(str(tmp_path))["proposedName"] is None


def test_session_dismiss_records_dismissed(tmp_path):
    s = _sess(tmp_path)
    s.set_workspace_meta({"proposedName": "Cycloidal Drive"})
    res = s.dismiss_proposed_name()
    assert res["ok"] is True
    assert wm.load_metadata(str(tmp_path))["proposedNameDismissed"] == "Cycloidal Drive"


def test_handlers_registered():
    for name in (
        "get_workspace_meta",
        "set_workspace_meta",
        "set_workspace_name",
        "dismiss_proposed_name",
    ):
        assert name in _HANDLERS
