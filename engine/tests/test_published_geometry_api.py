import pytest
from build123d import Box, Rectangle

from solidifai import skeleton


def test_profile_stores_and_returns():
    s = skeleton()
    seat = Rectangle(40, 30)
    out = s.profile("seat", seat)
    assert out is seat  # returns the shape, like scalar()/frame()
    assert s.shapes == {"seat": seat}


def test_shape_accepts_a_solid():
    s = skeleton()
    boss = Box(5, 5, 5)
    s.shape("boss", boss)
    assert s.shapes["boss"] is boss


def test_profile_rejects_a_solid():
    s = skeleton()
    with pytest.raises(ValueError, match="profile"):
        s.profile("bad", Box(5, 5, 5))


def test_resolve_shapes_picks_declared_only():
    s = skeleton()
    seat = Rectangle(10, 10)
    s.profile("seat", seat)
    s.shape("boss", Box(1, 1, 1))
    assert s.resolve_shapes(["seat"]) == {"seat": seat}


def test_resolve_shapes_unknown_name_raises():
    s = skeleton()
    s.profile("seat", Rectangle(10, 10))
    with pytest.raises(KeyError, match="nope"):
        s.resolve_shapes(["nope"])


import json

from solidifai_engine.assembly import manifest as manifest_mod


def _manifest_json(tmp_path, children):
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": children,
            }
        ),
        encoding="utf-8",
    )


def test_manifest_loads_shape_inputs(tmp_path):
    _manifest_json(
        tmp_path,
        [
            {
                "id": "lid",
                "kind": "part",
                "source": "parts/lid.py",
                "attach": "lid_frame",
                "inputs": ["fit"],
                "shape_inputs": ["seat"],
            },
        ],
    )
    man = manifest_mod.load_manifest(str(tmp_path))
    assert man.children[0].shape_inputs == ["seat"]


def test_manifest_v1_defaults_empty_shape_inputs(tmp_path):
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "a",
                        "kind": "part",
                        "source": "parts/a.py",
                        "attach": None,
                        "inputs": ["w"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    man = manifest_mod.load_manifest(str(tmp_path))
    assert man.children[0].shape_inputs == []  # backward compatible


def test_manifest_roundtrip_emits_shape_inputs_only_when_present(tmp_path):
    man = manifest_mod.Manifest(
        skeleton="skeleton.py",
        children=[
            manifest_mod.ChildEntry(
                id="lid",
                kind="part",
                source="parts/lid.py",
                attach="lid_frame",
                inputs=["fit"],
                shape_inputs=["seat"],
            ),
            manifest_mod.ChildEntry(
                id="plain", kind="part", source="parts/plain.py", attach=None, inputs=["w"]
            ),
        ],
    )
    manifest_mod.write_manifest(str(tmp_path), man)
    raw = json.loads((tmp_path / "assembly.json").read_text(encoding="utf-8"))
    assert raw["version"] == 2
    assert raw["children"][0]["shape_inputs"] == ["seat"]
    assert "shape_inputs" not in raw["children"][1]  # omitted when empty (clean diffs)


def test_profile_rejects_non_shape():
    s = skeleton()
    with pytest.raises(TypeError, match="profile"):
        s.profile("x", None)
    with pytest.raises(TypeError, match="profile"):
        s.profile("x", 5)


def test_shape_rejects_non_shape():
    s = skeleton()
    with pytest.raises(TypeError, match="shape"):
        s.shape("x", None)
