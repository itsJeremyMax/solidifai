from solidifai_engine.session import Session


def _collect(node):
    issues = []
    Session._collect_interface_issues(node, prefix="", issues=issues)
    return issues


def test_missing_shape_input_is_flagged():
    node = {
        "skeleton": {"frames": ["lid_frame"], "scalars": ["fit"], "shapes": ["seat"]},
        "children": [
            {
                "id": "lid",
                "kind": "part",
                "attach": "lid_frame",
                "inputs": ["fit"],
                "shape_inputs": ["ghost"],
            },
        ],
    }
    issues = _collect(node)
    assert any(i["issue"] == "missing_shape_input" and i["name"] == "ghost" for i in issues)


def test_valid_shape_wiring_has_no_issue():
    node = {
        "skeleton": {"frames": ["lid_frame"], "scalars": ["fit"], "shapes": ["seat"]},
        "children": [
            {
                "id": "lid",
                "kind": "part",
                "attach": "lid_frame",
                "inputs": ["fit"],
                "shape_inputs": ["seat"],
            },
        ],
    }
    assert _collect(node) == []


def test_scalar_shape_name_collision_is_flagged():
    node = {
        "skeleton": {"frames": [], "scalars": ["seat"], "shapes": ["seat"]},
        "children": [
            {
                "id": "lid",
                "kind": "part",
                "attach": None,
                "inputs": ["seat"],
                "shape_inputs": ["seat"],
            },
        ],
    }
    issues = _collect(node)
    assert any(i["issue"] == "input_name_collision" and i["name"] == "seat" for i in issues)


import json


def _seed_assembly(tmp_path):
    (tmp_path / "skeleton.py").write_text(
        "from solidifai import skeleton\n"
        "from build123d import Rectangle, Location\n"
        "PARAMS = {'w': {'value': 40.0, 'min': 10, 'max': 80, 'step': 1, 'unit': 'mm'}}\n"
        "def build(w):\n"
        "    s = skeleton()\n"
        "    s.profile('seat', Rectangle(w, w))\n"
        "    s.frame('o', Location((0, 0, 0)))\n"
        "    return s\n",
        encoding="utf-8",
    )
    (tmp_path / "assembly.json").write_text(
        json.dumps({"version": 2, "skeleton": "skeleton.py", "children": []}), encoding="utf-8"
    )


def test_set_part_persists_shape_inputs(tmp_path):
    _seed_assembly(tmp_path)
    artifacts = tmp_path / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    sess = Session(str(artifacts), model_path=str(tmp_path / "assembly.json"))
    sess.startup()

    code = (
        "from solidifai import show\n"
        "from build123d import BuildPart, BuildSketch, add, extrude\n"
        "def build(inputs):\n"
        "    with BuildPart() as p:\n"
        "        with BuildSketch():\n"
        "            add(inputs['seat'])\n"
        "        extrude(amount=3)\n"
        "    show(p.part, name='Base')\n"
    )
    res = sess.set_part("base", code, attach="o", inputs=[], shape_inputs=["seat"])
    assert res.get("ok"), res
    from solidifai_engine.assembly import manifest as manifest_mod

    man = manifest_mod.load_manifest(str(tmp_path))
    base = manifest_mod.child_by_id(man, "base")
    assert base.shape_inputs == ["seat"]

    res2 = sess.set_part("base", code)  # source-only edit, wiring omitted
    assert res2.get("ok"), res2
    man2 = manifest_mod.load_manifest(str(tmp_path))
    assert manifest_mod.child_by_id(man2, "base").shape_inputs == ["seat"]  # preserved


def test_shape_input_on_subassembly_is_flagged():
    node = {
        "skeleton": {"frames": [], "scalars": [], "shapes": ["seat"]},
        "children": [
            {
                "id": "sub",
                "kind": "assembly",
                "attach": None,
                "inputs": [],
                "shape_inputs": ["seat"],
            },
        ],
    }
    issues = []
    Session._collect_interface_issues(node, prefix="", issues=issues)
    assert any(i["issue"] == "shape_input_on_subassembly" and i["name"] == "seat" for i in issues)
