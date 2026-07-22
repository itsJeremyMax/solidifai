import json
import math
import os

import pytest

from solidifai_engine.session import Session

GOOD_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

with BuildPart() as p:
    Box(20, 20, 20)

show(p.part, name="C")
"""

STACKED_PART_SCRIPT = """
from build123d import Align, Box, Pos
from solidifai import show

base = Box(40, 40, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
lid = Pos(0, 0, 10) * Box(40, 40, 4, align=(Align.CENTER, Align.CENTER, Align.MIN))
show(base, name="Base")
show(lid, name="Lid")
"""

# Two parts sharing the assembly center (a centered pin in a centered block).
# exploded() returns such concentric parts UNCHANGED, so this is the case that
# would corrupt self._model if the explode capture ever reparented a shared
# original into a Compound. Regression guard for that bug.
CONCENTRIC_PART_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

with BuildPart() as a:
    Box(20, 20, 20)
with BuildPart() as b:
    Box(10, 10, 10)
show(a.part, name="Block")
show(b.part, name="Pin")
"""


def _offscreen_or_skip():
    """Skip when offscreen GL can't initialize (headless CI), like test_views."""
    try:
        import vtkmodules.all as vtk

        win = vtk.vtkRenderWindow()
        win.SetOffScreenRendering(1)
        win.AddRenderer(vtk.vtkRenderer())
        win.SetSize(64, 64)
        win.Render()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"offscreen GL unavailable: {exc}")


BAD_SCRIPT = """
from build123d import Box
from solidifai import show

show(Box(10, 10, 10), name="X")
raise RuntimeError("boom")
"""


def test_good_script_renders_and_bumps_build(tmp_path):
    sess = Session(str(tmp_path))
    res = sess.execute_script(GOOD_SCRIPT)

    assert res["ok"] is True
    assert res["buildId"] == 1
    assert sess.build_id == 1
    assert sess.last_ok is True
    assert sess.code == GOOD_SCRIPT

    glb = tmp_path / "model.glb"
    model = tmp_path / "model.json"
    assert glb.exists()
    assert model.exists()
    data = json.loads(model.read_text())
    assert data["buildId"] == 1
    assert data["objects"][0]["name"] == "C"


def test_bad_script_does_not_bump_or_overwrite(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(GOOD_SCRIPT)

    glb = tmp_path / "model.glb"
    model = tmp_path / "model.json"
    good_glb = glb.read_bytes()
    good_json = model.read_text()

    res = sess.execute_script(BAD_SCRIPT)
    assert res["ok"] is False
    assert "error" in res
    assert "traceback" in res
    assert "boom" in res["traceback"]

    # build id unchanged, last good artifacts intact
    assert sess.build_id == 1
    assert sess.last_ok is False
    assert glb.read_bytes() == good_glb
    assert model.read_text() == good_json

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_run_file(tmp_path):
    script = tmp_path / "part.py"
    script.write_text(GOOD_SCRIPT)
    out = tmp_path / "artifacts"
    out.mkdir()
    sess = Session(str(out))
    res = sess.run_file(str(script))
    assert res["ok"] is True
    assert (out / "model.glb").exists()


def test_execute_script_persists_code_to_model_path(tmp_path):
    model_path = tmp_path / "model.py"
    artifacts = tmp_path / "artifacts"
    sess = Session(str(artifacts), model_path=str(model_path))

    res = sess.execute_script(GOOD_SCRIPT)
    assert res["ok"] is True
    # successful execute_script writes the code to the durable model file
    assert model_path.read_text() == GOOD_SCRIPT


def test_failing_script_does_not_overwrite_model_path(tmp_path):
    model_path = tmp_path / "model.py"
    artifacts = tmp_path / "artifacts"
    sess = Session(str(artifacts), model_path=str(model_path))

    sess.execute_script(GOOD_SCRIPT)
    good_on_disk = model_path.read_text()
    assert good_on_disk == GOOD_SCRIPT

    res = sess.execute_script(BAD_SCRIPT)
    assert res["ok"] is False
    # the durable model file is unchanged after a failed build
    assert model_path.read_text() == good_on_disk


def test_no_model_path_writes_no_file(tmp_path):
    # Sessions without a model_path must behave exactly as before (no writes).
    artifacts = tmp_path / "artifacts"
    sess = Session(str(artifacts))
    res = sess.execute_script(GOOD_SCRIPT)
    assert res["ok"] is True
    # nothing written outside the artifacts dir; no model.py appears
    assert not (tmp_path / "model.py").exists()
    assert sess.model_path is None


def test_reopen_reproduces_model_from_persisted_file(tmp_path):
    model_path = tmp_path / "model.py"
    artifacts1 = tmp_path / "artifacts1"
    artifacts2 = tmp_path / "artifacts2"

    sess1 = Session(str(artifacts1), model_path=str(model_path))
    assert sess1.execute_script(GOOD_SCRIPT)["ok"] is True
    bbox1 = json.loads((artifacts1 / "model.json").read_text())["bbox"]["size"]

    sess2 = Session(str(artifacts2), model_path=str(model_path))
    res = sess2.run_file(str(model_path))
    assert res["ok"] is True
    bbox2 = json.loads((artifacts2 / "model.json").read_text())["bbox"]["size"]

    assert bbox2 == bbox1


FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

with BuildPart() as p:
    Box(40, 40, 12)
    with feature("center_hole", driven_by="bore"):
        with Locations((0, 0)):
            Hole(radius=6)

show(p.part, name="Plate")
"""


def test_features_snapshotted_on_success(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(FEATURE_SCRIPT)["ok"] is True
    assert [f.name for f in sess._features] == ["center_hole"]
    assert sess._features[0].driven_by == ["bore"]


def test_features_snapshot_survives_failed_rebuild(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)
    # A failing rebuild must not wipe the last-good feature snapshot.
    assert sess.execute_script(BAD_SCRIPT)["ok"] is False
    assert [f.name for f in sess._features] == ["center_hole"]


def test_untagged_build_has_empty_features(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(GOOD_SCRIPT)["ok"] is True  # no feature() calls
    assert sess._features == []


PARAM_FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

PARAMS = {"bore": {"value": 6.0, "min": 2.0, "max": 18.0, "step": 1.0, "unit": "mm"}}

def build(bore):
    with BuildPart() as p:
        Box(40, 40, 12)
        with feature("center_hole", driven_by="bore"):
            with Locations((0, 0)):
                Hole(radius=bore / 2)
    show(p.part, name="Plate")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


MIXED_PARAM_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "size": {
        "value": 20.0,
        "min": 5.0,
        "max": 100.0,
        "step": 1.0,
        "unit": "mm",
        "desc": "Edge length",
    },
    "enabled": {"type": "boolean", "value": True, "desc": "Show the full body"},
    "mode": {
        "type": "enum",
        "value": "draft",
        "choices": ["draft", "final"],
        "desc": "Output mode",
    },
}

def build(size, enabled, mode):
    width = size if enabled else size / 2
    height = size if mode == "final" else size / 4
    with BuildPart() as p:
        Box(width, size, height)
    show(p.part, name="Mixed")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


LEGACY_NUMERIC_TYPE_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "hole_dia": {
        "type": "diameter",
        "value": 10,
        "min": 1,
        "max": 20,
        "step": 1,
        "unit": "mm",
        "desc": "Hole diameter",
    }
}

def build(hole_dia):
    with BuildPart() as p:
        Box(hole_dia, 20, 20)
    show(p.part, name="Legacy")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


BAD_ENUM_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "mode": {
        "type": "enum",
        "value": "draft",
        "choices": ["draft", 1],
        "desc": "Broken output mode",
    }
}

def build(mode):
    with BuildPart() as p:
        Box(10, 10, 10)
    show(p.part, name="Broken")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


UNKNOWN_TYPE_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

PARAMS = {
    "enabled": {"type": "bool", "value": True, "desc": "Broken enabled type"}
}

def build(enabled):
    with BuildPart() as p:
        Box(10, 10, 10)
    show(p.part, name="Broken")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


def test_features_refreshed_after_set_params(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(PARAM_FEATURE_SCRIPT)["ok"] is True
    assert [f.name for f in sess._features] == ["center_hole"]
    assert sess.set_params({"bore": 8})["ok"] is True
    # the snapshot is refreshed by the set_params rebuild, not stale
    assert [f.name for f in sess._features] == ["center_hole"]
    assert sess._features[0].driven_by == ["bore"]


def test_get_params_and_model_json_include_boolean_and_enum_params(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(MIXED_PARAM_SCRIPT)["ok"] is True

    params = sess.get_params()
    assert params["schema"] == {
        "size": {
            "value": 20.0,
            "min": 5.0,
            "max": 100.0,
            "step": 1.0,
            "unit": "mm",
            "desc": "Edge length",
        },
        "enabled": {"type": "boolean", "value": True, "desc": "Show the full body"},
        "mode": {
            "type": "enum",
            "value": "draft",
            "choices": ["draft", "final"],
            "desc": "Output mode",
        },
    }
    assert params["values"] == {"size": 20.0, "enabled": True, "mode": "draft"}

    model = json.loads((tmp_path / "model.json").read_text())
    assert model["params"] == params


def test_set_params_validates_boolean_and_enum_values(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(MIXED_PARAM_SCRIPT)["ok"] is True

    bad_bool = sess.set_params({"enabled": "yes"})
    assert bad_bool["ok"] is False
    assert "must be a boolean" in bad_bool["error"]

    bad_enum = sess.set_params({"mode": "turbo"})
    assert bad_enum["ok"] is False
    assert "must be one of" in bad_enum["error"]

    bad_unknown = sess.set_params({"missing": True})
    assert bad_unknown["ok"] is False
    assert "unknown parameter" in bad_unknown["error"]

    good = sess.set_params({"enabled": False, "mode": "final"})
    assert good["ok"] is True
    assert sess.get_params()["values"]["enabled"] is False
    assert sess.get_params()["values"]["mode"] == "final"


def test_execute_script_rejects_malformed_enum_choices(tmp_path):
    sess = Session(str(tmp_path))

    res = sess.execute_script(BAD_ENUM_SCRIPT)

    assert res["ok"] is False
    assert "choices" in res["error"]


def test_execute_script_rejects_explicit_unknown_param_type(tmp_path):
    sess = Session(str(tmp_path))

    res = sess.execute_script(UNKNOWN_TYPE_SCRIPT)

    assert res["ok"] is False
    assert "unknown type" in res["error"]


def test_execute_script_accepts_legacy_numeric_param_with_arbitrary_type_metadata(tmp_path):
    sess = Session(str(tmp_path))

    res = sess.execute_script(LEGACY_NUMERIC_TYPE_SCRIPT)

    assert res["ok"] is True
    assert sess.get_params() == {
        "schema": {
            "hole_dia": {
                "value": 10.0,
                "min": 1.0,
                "max": 20.0,
                "step": 1.0,
                "unit": "mm",
                "desc": "Hole diameter",
            }
        },
        "values": {"hole_dia": 10.0},
    }


def test_execute_script_accepts_legacy_numeric_param_with_reserved_type_metadata(tmp_path):
    sess = Session(str(tmp_path))

    res = sess.execute_script(LEGACY_NUMERIC_TYPE_SCRIPT.replace('"diameter"', '"boolean"'))

    assert res["ok"] is True
    assert sess.get_params()["values"] == {"hole_dia": 10.0}


def test_inspect_features_returns_inventory(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)
    feats = sess.inspect_features()["features"]
    assert len(feats) == 1
    f = feats[0]
    assert f["name"] == "center_hole"
    assert f["kind"] is None
    assert f["driven_by"] == ["bore"]
    assert f["source"]["line"] == sess._features[0].source_line
    assert f["center"] is not None and len(f["center"]) == 3
    assert f["bbox"] is not None and len(f["bbox"]) == 3
    assert f["metrics"]["faces"] >= 1


def test_inspect_features_empty_when_untagged(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(GOOD_SCRIPT)
    assert sess.inspect_features() == {"features": []}


def test_inspect_features_includes_geometry(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)  # box + center_hole feature
    f = sess.inspect_features()["features"][0]
    assert f["name"] == "center_hole"
    assert f["center"] is not None and len(f["center"]) == 3
    assert f["bbox"] is not None and len(f["bbox"]) == 3
    assert f["metrics"]["faces"] >= 1


def test_capture_views_unknown_highlight_errors(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)
    out = sess.capture_views(["iso"], highlight=["nope"])
    assert out["ok"] is False
    assert "nope" in out["error"]
    assert "center_hole" in out["error"]  # offers the valid feature names


def _bbox_tuple(bb):
    return (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)


def test_capture_views_explode_does_not_mutate_model(tmp_path):
    # explode is a render-time spread for fit review; it must NEVER change the
    # persisted/exported model. Whether the GL render succeeds (local) or returns
    # an error envelope (headless), the model stays exactly as built.
    sess = Session(str(tmp_path))
    sess.execute_script(STACKED_PART_SCRIPT)
    before = _bbox_tuple(sess._model.bounding_box())

    out = sess.capture_views(["iso"], explode=80)

    assert "ok" in out  # accepted the kwarg (didn't TypeError)
    assert len(sess._objects) == 2  # still two distinct parts
    assert _bbox_tuple(sess._model.bounding_box()) == before


def test_capture_views_explode_preserves_concentric_model(tmp_path):
    # Concentric parts are the case exploded() returns unchanged; an explode
    # capture must still leave self._model intact (the reparenting regression).
    sess = Session(str(tmp_path))
    sess.execute_script(CONCENTRIC_PART_SCRIPT)
    before = _bbox_tuple(sess._model.bounding_box())

    sess.capture_views(["iso"], explode=80)

    assert _bbox_tuple(sess._model.bounding_box()) == before
    assert len(sess._objects) == 2


def test_capture_views_explode_renders_when_gl_available(tmp_path):
    _offscreen_or_skip()
    sess = Session(str(tmp_path))
    sess.execute_script(STACKED_PART_SCRIPT)
    out = sess.capture_views(["iso"], explode=80)
    assert out["ok"] is True
    view = out["views"][0]
    assert view["path"] and os.path.isfile(view["path"])


def test_feature_at_hits_and_misses(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)  # box + center_hole feature
    rec = sess._features[0]
    # Pick a point genuinely ON the feature surface (a real tessellated vertex),
    # NOT the bbox center (a hole's center sits in empty space, far from the wall).
    from solidifai_engine import features as fg

    verts, _ = fg.tessellate(rec.faces, tol=0.5)
    on_surface = list(verts[0])
    hit = sess.feature_at(on_surface)
    assert hit["match"] is not None
    assert hit["match"]["name"] == "center_hole"
    miss = sess.feature_at([1000.0, 1000.0, 1000.0])
    assert miss["match"] is None


DUP_FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

PARAMS = {
    "a": {"value": 5.0, "min": 2.0, "max": 9.0, "step": 1.0, "unit": "mm"},
    "b": {"value": 5.0, "min": 2.0, "max": 9.0, "step": 1.0, "unit": "mm"},
}

def build(a, b):
    with BuildPart() as p:
        Box(60, 30, 10)
        with feature("port", driven_by="a"), Locations((-15, 0)):
            Hole(radius=a / 2)
        with feature("port", driven_by="b"), Locations((15, 0)):
            Hole(radius=b / 2)
    show(p.part, name="Plate")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


def test_duplicate_feature_names_are_disambiguated(tmp_path):
    # Finding 3: two feature("port") blocks must each be addressable, not collapse.
    sess = Session(str(tmp_path))
    assert sess.execute_script(DUP_FEATURE_SCRIPT)["ok"] is True
    names = [f["name"] for f in sess.inspect_features()["features"]]
    assert names == ["port", "port_2"]


def test_set_feature_targets_disambiguated_duplicate(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(DUP_FEATURE_SCRIPT)
    res = sess.set_feature("port_2", {"b": 8})
    assert res["ok"] is True
    assert sess.get_params()["values"]["b"] == 8
    # the raw (now-ambiguous) reference to a missing name lists the disambiguated ones
    bad = sess.set_feature("port_9", {"a": 8})
    assert bad["ok"] is False and "port_2" in bad["error"]


def test_feature_at_resolves_second_duplicate(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(DUP_FEATURE_SCRIPT)
    hit = sess.feature_at([15.0, 0.0, 0.0], tolerance_mm=5.0)  # second port at x=+15
    assert hit["match"] is not None and hit["match"]["name"] == "port_2"


TYPO_DRIVEN_BY_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

PARAMS = {"bore": {"value": 6.0, "min": 2.0, "max": 18.0, "step": 1.0, "unit": "mm"}}

def build(bore):
    with BuildPart() as p:
        Box(40, 40, 12)
        with feature("center_hole", driven_by="boer"):  # typo: real param is "bore"
            with Locations((0, 0)):
                Hole(radius=bore / 2)
    show(p.part, name="Plate")

build(**{k: v["value"] for k, v in PARAMS.items()})
"""


def test_inspect_features_flags_unknown_driven_by(tmp_path):
    # Finding 5: a driven_by that names no real param is surfaced as a warning.
    sess = Session(str(tmp_path))
    assert sess.execute_script(TYPO_DRIVEN_BY_SCRIPT)["ok"] is True
    f = sess.inspect_features()["features"][0]
    assert f["driven_by"] == ["boer"]
    assert f.get("warning") and "boer" in f["warning"]


def test_set_feature_rejects_unknown_driven_by(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(TYPO_DRIVEN_BY_SCRIPT)
    res = sess.set_feature("center_hole", {"boer": 8})
    assert res["ok"] is False
    assert "boer" in res["error"] and "bore" in res["error"]


def test_feature_at_success_envelope_has_ok_true(tmp_path):
    # Finding 6: the success payload carries ok: true (additive; the existing
    # "match" key stays), matching the bad-input branch that returns ok: false.
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)
    res = sess.feature_at([1000.0, 1000.0, 1000.0])
    assert res["ok"] is True
    assert res["match"] is None
    bad = sess.feature_at([1, 2])
    assert bad["ok"] is False


FILLET_FEATURE_SCRIPT = """
from build123d import BuildPart, Box, fillet, Axis
from solidifai import show, feature

with BuildPart() as p:
    Box(200, 200, 100)
    top = p.edges().filter_by(Axis.X).group_by(Axis.Z)[-1].sort_by(Axis.Y)[-1]
    with feature("lip", kind="fillet"):
        fillet(top, radius=3)

show(p.part, name="Block")
"""


def test_feature_at_finds_filleted_edge(tmp_path):
    # Finding 4: a 3mm-filleted edge declared as a feature is resolvable by a
    # click on the rounded surface (adaptive tolerance on a large model).
    import math

    sess = Session(str(tmp_path))
    assert sess.execute_script(FILLET_FEATURE_SCRIPT)["ok"] is True
    assert [f.name for f in sess._features] == ["lip"]
    # a point dead-on the quarter-round surface (top edge at y=100, z=50)
    py = 100 - 3 + 3 * math.cos(math.radians(45))
    pz = 50 - 3 + 3 * math.sin(math.radians(45))
    hit = sess.feature_at([0.0, py, pz])
    assert hit["match"] is not None and hit["match"]["name"] == "lip"


def test_feature_at_tolerance_mm_override(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(FEATURE_SCRIPT)
    # The bore center sits in empty space ~6mm (radius) from the nearest wall: a
    # generous explicit tolerance resolves it, a tight one does not.
    center = [0.0, 0.0, 0.0]
    assert sess.feature_at(center, tolerance_mm=8.0)["match"] is not None
    assert sess.feature_at(center, tolerance_mm=2.0)["match"] is None


LITERAL_FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show, feature

with BuildPart() as p:
    Box(40, 40, 12)
    with feature("plain_hole"):
        with Locations((0, 0)):
            Hole(radius=6)

show(p.part, name="Plate")
"""


def test_set_feature_drives_param_and_rebuilds(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(PARAM_FEATURE_SCRIPT)["ok"] is True
    b0 = sess.build_id
    res = sess.set_feature("center_hole", {"bore": 16})
    assert res["ok"] is True
    assert sess.build_id == b0 + 1
    assert sess.get_params()["values"]["bore"] == 16


def test_set_feature_unknown_name_errors(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(PARAM_FEATURE_SCRIPT)
    res = sess.set_feature("nope", {"bore": 16})
    assert res["ok"] is False
    assert "nope" in res["error"]
    assert "center_hole" in res["error"]


def test_set_feature_wrong_param_errors(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(PARAM_FEATURE_SCRIPT)
    res = sess.set_feature("center_hole", {"length": 99})
    assert res["ok"] is False
    assert "length" in res["error"]
    assert "bore" in res["error"]


def test_set_feature_non_parametric_errors(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(LITERAL_FEATURE_SCRIPT)
    res = sess.set_feature("plain_hole", {"radius": 4})
    assert res["ok"] is False
    assert "plain_hole" in res["error"]
    assert "source" in res["error"].lower() or "execute_script" in res["error"].lower()


def test_set_feature_empty_values_errors(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(PARAM_FEATURE_SCRIPT)
    res = sess.set_feature("center_hole", {})
    assert res["ok"] is False


HOLE_NO_FEATURE_SCRIPT = """
from build123d import BuildPart, Box, Locations, Hole
from solidifai import show

with BuildPart() as p:
    Box(40, 40, 20)
    with Locations((0, 0)):
        Hole(radius=5)

show(p.part, name="Plate")
"""


def test_untagged_model_gets_inferred_features(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(HOLE_NO_FEATURE_SCRIPT)["ok"] is True
    feats = sess.inspect_features()["features"]
    assert feats, "expected inferred features for an untagged hole model"
    assert all(f["inferred"] is True for f in feats)
    assert all(f["confidence"] is not None for f in feats)


def test_declared_features_win_over_inference(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(FEATURE_SCRIPT)["ok"] is True
    feats = sess.inspect_features()["features"]
    assert [f["name"] for f in feats] == ["center_hole"]
    assert all(f["inferred"] is False for f in feats)


def test_plain_box_has_no_inferred_features(tmp_path):
    sess = Session(str(tmp_path))
    assert sess.execute_script(GOOD_SCRIPT)["ok"] is True
    assert sess.inspect_features()["features"] == []


def test_set_feature_refuses_inferred(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(HOLE_NO_FEATURE_SCRIPT)
    name = sess.inspect_features()["features"][0]["name"]
    res = sess.set_feature(name, {"radius": 4})
    assert res["ok"] is False
    assert "inferred" in res["error"].lower()


TWO_PART_SCRIPT = """
from build123d import BuildPart, Box
from solidifai import show

with BuildPart() as a:
    Box(20, 20, 20)
with BuildPart() as b:
    Box(10, 10, 10)

show(a.part, name="Bracket", material="pla")
show(b.part, name="Pin", material="pla")
"""


def _two_part_session(tmp_path):
    """Build a Session over a real workspace (model.py written under root) with a
    two-part registry, then run startup so overrides load + persist. Part ids are
    the slugified show() names: 'bracket' and 'pin'."""
    root = tmp_path / "workspace"
    root.mkdir()
    model_path = root / "model.py"
    model_path.write_text(TWO_PART_SCRIPT)
    artifacts = root / ".solidifai" / "artifacts"
    sess = Session(str(artifacts), model_path=str(model_path))
    sess.startup()
    return sess, str(root)


def _model_by_id(sess):
    model = sess.get_model_info()
    return {o["id"]: o for o in model["objects"]}


def test_set_part_material_overrides_and_persists(tmp_path):
    from solidifai_engine import part_materials

    sess, root = _two_part_session(tmp_path)
    out = sess.set_part_material("bracket", "aluminum")
    assert out["ok"] is True

    by_id = _model_by_id(sess)
    assert by_id["bracket"]["appearance"]["material"] == "aluminum"
    assert by_id["pin"]["appearance"]["material"] == "pla"  # untouched

    assert part_materials.load_overrides(root) == {"bracket": "aluminum"}


def test_set_part_material_rejects_unknown_part(tmp_path):
    sess, _ = _two_part_session(tmp_path)
    out = sess.set_part_material("ghost", "aluminum")
    assert out["ok"] is False
    assert "unknown part" in out["error"]


def test_set_part_material_rejects_unknown_material(tmp_path):
    sess, _ = _two_part_session(tmp_path)
    out = sess.set_part_material("bracket", "unobtainium")
    assert out["ok"] is False
    assert "unobtainium" in out["error"]


def test_set_part_material_none_clears(tmp_path):
    from solidifai_engine import part_materials

    sess, root = _two_part_session(tmp_path)
    assert sess.set_part_material("bracket", "aluminum")["ok"] is True
    assert part_materials.load_overrides(root) == {"bracket": "aluminum"}

    out = sess.set_part_material("bracket", None)
    assert out["ok"] is True
    assert part_materials.load_overrides(root) == {}
    by_id = _model_by_id(sess)
    assert by_id["bracket"]["appearance"]["material"] == "pla"  # back to model default


def test_overrides_loaded_on_startup_apply_to_first_build(tmp_path):
    from solidifai_engine import part_materials

    root = tmp_path / "workspace"
    root.mkdir()
    (root / "model.py").write_text(TWO_PART_SCRIPT)
    # Pre-seed an override before the workspace is ever opened.
    part_materials.write_overrides(str(root), {"bracket": "aluminum"})

    sess = Session(str(tmp_path / "artifacts"), model_path=str(root / "model.py"))
    sess.startup()

    by_id = _model_by_id(sess)
    assert by_id["bracket"]["appearance"]["material"] == "aluminum"
    assert by_id["pin"]["appearance"]["material"] == "pla"


# --- validation: measure / stress_check / tolerance_stack --------------------

TWO_BOX_SCRIPT = """
from build123d import Box, Pos
from solidifai import show

show(Box(10, 10, 10), name="A")
show(Pos(20, 0, 0) * Box(10, 10, 10), name="B")
"""


def test_measure_reports_total_and_parts(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(TWO_BOX_SCRIPT)
    rep = sess.measure()
    assert rep["ok"] is True
    assert len(rep["parts"]) == 2
    assert rep["summary"]["parts"] == 2
    total = sum(p["mass"] for p in rep["parts"])
    assert math.isclose(rep["total"]["mass"], total, rel_tol=1e-6)
    # CoM of two equal boxes at x=0 and x=20 sits at x=10.
    assert math.isclose(rep["total"]["centerOfMass"][0], 10.0, abs_tol=1e-3)


def test_measure_no_model_errors(tmp_path):
    assert Session(str(tmp_path)).measure()["ok"] is False


def test_stress_check_envelope(tmp_path):
    sess = Session(str(tmp_path))
    sess.execute_script(GOOD_SCRIPT)  # a plain 20mm box
    rep = sess.stress_check()
    assert rep["ok"] is True
    assert rep["summary"]["parts"] == 1
    assert rep["parts"][0]["hotspots"] == []  # a clean box has no sharp corners


def test_tolerance_stack_via_session(tmp_path):
    rep = Session(str(tmp_path)).tolerance_stack(
        [
            {"label": "hole", "nominal": 10.0, "fit": "H7", "direction": 1},
            {"label": "shaft", "nominal": 10.0, "fit": "g6", "direction": -1},
        ]
    )
    assert rep["ok"] is True
    assert rep["fit"]["type"] == "clearance"


# --- requirements (goal-driven verification) ---------------------------------


def test_requirements_met_and_unmet(tmp_path):
    s = Session(str(tmp_path))
    s.execute_script(TWO_BOX_SCRIPT)  # combined bbox ~30 x 10 x 10, mass ~2.5 g
    s.set_requirements(
        [
            {"id": "m", "type": "max_mass", "target": 1000, "enabled": True},
            {"id": "z", "type": "max_size", "target": [5, 5, 5], "enabled": True},
        ]
    )
    rep = s.check_requirements()
    assert rep["ok"] is True
    assert rep["summary"]["total"] == 2
    by = {r["id"]: r for r in rep["requirements"]}
    assert by["m"]["pass"] is True
    assert by["z"]["pass"] is False
    assert rep["summary"]["allMet"] is False


def test_requirements_invalid_type_dropped(tmp_path):
    s = Session(str(tmp_path))
    res = s.set_requirements([{"id": "x", "type": "bogus", "target": 1}])
    assert res["count"] == 0


def test_requirements_persist_across_reopen(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(GOOD_SCRIPT)
    s = Session(str(tmp_path / "art"), model_path=str(root / "model.py"))
    s.startup()
    s.set_requirements([{"id": "w", "type": "watertight", "target": None, "enabled": True}])
    s2 = Session(str(tmp_path / "art2"), model_path=str(root / "model.py"))
    s2.startup()
    rep = s2.check_requirements()
    assert len(rep["requirements"]) == 1
    # after migration, watertight is stored/returned as a predicate
    assert rep["requirements"][0]["quantity"] == "watertight"


def test_requirements_no_model_pass_null(tmp_path):
    s = Session(str(tmp_path))
    s.set_requirements([{"id": "m", "type": "max_mass", "target": 1, "enabled": True}])
    assert s.check_requirements()["requirements"][0]["pass"] is None


# --- Task 4: predicate eval + regression deltas + new ctx --------------------

TWO_BOX_SCRIPT_FOR_REQS = """
from build123d import Box, Pos
from solidifai import show

show(Box(10, 10, 10), name="A")
show(Pos(20, 0, 0) * Box(10, 10, 10), name="B")
"""

THIN_WALL_SCRIPT = """
from build123d import Box
from solidifai import show

# 0.5mm thin wall -- below the 0.8mm FDM minimum
show(Box(20, 20, 0.5), name="Plate", material="pla")
"""


def test_check_requirements_predicate_form_and_delta(tmp_path):
    """Predicate requirements are evaluated and each result carries a delta key."""
    s = Session(str(tmp_path))
    s.execute_script(TWO_BOX_SCRIPT_FOR_REQS)
    s.set_requirements([{"id": "m", "quantity": "mass", "op": "<=", "bound": 1e9, "enabled": True}])
    rep = s.check_requirements()
    assert rep["ok"] is True
    r = rep["requirements"][0]
    assert r["pass"] is True
    assert "delta" in r
    assert "regressed" in rep["summary"]
    assert "fixed" in rep["summary"]


def test_set_requirements_accepts_predicate_form(tmp_path):
    """set_requirements accepts new predicate-form entries."""
    s = Session(str(tmp_path))
    res = s.set_requirements(
        [
            {"id": "a", "quantity": "mass", "op": "<=", "bound": 100, "enabled": True},
            {"id": "b", "kind": "assert", "expr": "mass < 500", "label": "light", "enabled": True},
        ]
    )
    assert res["ok"] is True
    assert res["count"] == 2


def test_set_requirements_migrates_legacy_and_drops_malformed(tmp_path):
    """Legacy types are migrated to predicates; bogus entries are dropped."""
    s = Session(str(tmp_path))
    res = s.set_requirements(
        [
            {"id": "x", "type": "max_mass", "target": 50, "enabled": True},
            {"id": "y", "type": "bogus", "target": 1},
            {"id": "z", "kind": "assert", "expr": "mass < 500", "label": "ok"},
        ]
    )
    assert res["count"] == 2
    # stored form is predicate / assert -- not legacy
    assert s._requirements[0]["quantity"] == "mass"
    assert s._requirements[1]["kind"] == "assert"


def test_check_requirements_second_run_computes_delta(tmp_path):
    """Second run shows 'unchanged' delta when result stays the same."""
    s = Session(str(tmp_path))
    s.execute_script(TWO_BOX_SCRIPT_FOR_REQS)
    s.set_requirements([{"id": "m", "quantity": "mass", "op": "<=", "bound": 1e9, "enabled": True}])
    s.check_requirements()  # first run -- seeds state
    rep = s.check_requirements()  # second run
    assert rep["requirements"][0]["delta"] == "unchanged"


def test_check_requirements_min_wall_ctx_populated(tmp_path):
    """min_wall ctx is populated (and check runs) when min_wall requirement exists."""
    s = Session(str(tmp_path))
    s.execute_script(THIN_WALL_SCRIPT)
    s.set_requirements(
        [{"id": "w", "quantity": "min_wall", "op": ">=", "bound": 1.0, "enabled": True}]
    )
    rep = s.check_requirements()
    assert rep["ok"] is True
    r = rep["requirements"][0]
    # thin wall (0.5mm) should fail a >= 1.0 bound
    assert r["pass"] is False
    assert r["measured"] is not None and r["measured"] > 0


def test_check_requirements_startup_migrates_legacy(tmp_path):
    """Legacy requirements.json loaded at startup is migrated to predicate form."""
    import json

    root = tmp_path / "ws"
    root.mkdir()
    (root / "model.py").write_text(GOOD_SCRIPT)
    # write a legacy requirements.json directly
    legacy = {
        "schema": 1,
        "requirements": [{"id": "l", "type": "max_mass", "target": 50, "enabled": True}],
    }
    (root / "requirements.json").write_text(json.dumps(legacy))
    s = Session(str(tmp_path / "art"), model_path=str(root / "model.py"))
    s.startup()
    # after startup, the in-memory requirements should be in predicate form
    assert s._requirements[0]["quantity"] == "mass"
    assert s._requirements[0]["op"] == "<="


def test_analyze_import_reports_features(tmp_path):
    s = Session(str(tmp_path))
    s.execute_script(
        "from build123d import BuildPart, Box, Hole, Locations\n"
        "from solidifai import show\n"
        "with BuildPart() as p:\n"
        "    Box(40, 40, 6)\n"
        "    with Locations((-12, 0), (12, 0)):\n"
        "        Hole(radius=2)\n"
        "show(p.part, name='Plate')\n"
    )
    rep = s.analyze_import()
    assert rep["ok"] is True
    assert rep["name"] == "Plate"
    assert rep["bbox"]["size"][0] == 40.0
    assert len([f for f in rep["features"] if f["kind"] in ("hole", "boss", "cylindrical")]) == 2


def test_analyze_import_no_model_errors(tmp_path):
    assert Session(str(tmp_path)).analyze_import()["ok"] is False


def test_render_after_set_params_reuses_pipeline(tmp_path):
    s = Session(str(tmp_path))
    assert s.execute_script(
        "from build123d import Box\n"
        "from solidifai import show\n"
        "PARAMS = {'w': {'min': 5, 'max': 40, 'default': 20}}\n"
        "def build(w):\n"
        "    show(Box(w, w, w), name='b')\n"
        "build(20)\n"
    )["ok"]
    b0 = s.build_id
    assert s.set_params({"w": 30})["ok"]
    assert s.build_id == b0 + 1
    assert s.render()["ok"]
    assert s.build_id == b0 + 2  # render bumps exactly one build via the shared pipeline


def test_render_does_not_commit_or_apply_references(tmp_path, monkeypatch):
    # A pure re-render must not re-apply reference fixtures nor auto-commit;
    # both are build-time side effects that only execute_script/set_params
    # should trigger. Regression guard for the A3 _run_build unification bug.
    sess = Session(str(tmp_path))
    assert sess.execute_script(GOOD_SCRIPT)["ok"] is True

    counts = {"apply_references": 0, "after_build": 0}

    def bump(key):
        counts[key] += 1

    monkeypatch.setattr(sess, "_apply_references", lambda: bump("apply_references"))
    monkeypatch.setattr(sess, "_after_build", lambda **kwargs: bump("after_build"))

    res = sess.render()

    assert res["ok"] is True
    assert counts["apply_references"] == 0
    assert counts["after_build"] == 0


def test_execute_script_publishes_before_compatibility_source_mirror(tmp_path, monkeypatch):
    from solidifai_engine import paths

    root = tmp_path / "workspace"
    root.mkdir()
    model_path = root / "model.py"
    artifacts = root / ".solidifai" / "artifacts"
    sess = Session(str(artifacts), model_path=str(model_path))

    original_copy = paths._copy_atomic

    def fail_source_mirror(source, destination):
        if destination == str(model_path):
            raise OSError("mirror unavailable")
        original_copy(source, destination)

    monkeypatch.setattr(paths, "_copy_atomic", fail_source_mirror)

    res = sess.execute_script(GOOD_SCRIPT)

    assert res["ok"] is True
    assert sess.build_id == 1
    assert paths.read_current_publication(str(artifacts)) is not None
