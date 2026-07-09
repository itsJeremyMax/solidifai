import json

from solidifai_engine import render
from solidifai_engine.assembly import graph
from solidifai_engine.assembly.compose import path_ids


def _enclosure(tmp_path):
    (tmp_path / "parts").mkdir()
    (tmp_path / "skeleton.py").write_text(
        """
from solidifai import skeleton
from build123d import Location
PARAMS = {"body_w": {"value": 40.0, "min": 10, "max": 80, "step": 1, "unit": "mm"},
          "wall": {"value": 2.0, "min": 1, "max": 5, "step": 0.5, "unit": "mm"}}
def build(body_w, wall):
    s = skeleton(); s.scalar("body_w", body_w); s.scalar("wall", wall)
    s.frame("base_frame", Location((0,0,0))); s.frame("lid_frame", Location((0,0,20)))
    return s
""",
        encoding="utf-8",
    )
    for pid, nm in (("base", "Base"), ("lid", "Lid")):
        (tmp_path / "parts" / f"{pid}.py").write_text(
            f'''
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="{nm}")
''',
            encoding="utf-8",
        )
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "base",
                        "kind": "part",
                        "source": "parts/base.py",
                        "attach": "base_frame",
                        "inputs": ["body_w", "wall"],
                    },
                    {
                        "id": "lid",
                        "kind": "part",
                        "source": "parts/lid.py",
                        "attach": "lid_frame",
                        "inputs": ["body_w", "wall"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_render_composed_assembly_writes_artifacts(tmp_path):
    _enclosure(tmp_path)
    artifacts = tmp_path / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    render.render_to(str(artifacts), 1, objects=objs, node_ids=path_ids(objs))
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    ids = sorted(o["id"] for o in model["objects"])
    assert ids == ["base/base", "lid/lid"]
    assert (artifacts / "model.glb").exists()
    # A single-placement assembly carries NO occurrence identity fields.
    assert all("occurrenceOf" not in o for o in model["objects"])
    assert all("occurrenceIndex" not in o for o in model["objects"])


def _occurrence_assembly(tmp_path, occurrences):
    """One instanced part `blk` under a skeleton with two frames."""
    (tmp_path / "parts").mkdir()
    (tmp_path / "skeleton.py").write_text(
        """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("a", Location((0, 0, 0)))
    s.frame("b", Location((40, 0, 0)))
    return s
""",
        encoding="utf-8",
    )
    (tmp_path / "parts" / "blk.py").write_text(
        """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(10, 10, 10)
    show(p.part, name="Blk")
""",
        encoding="utf-8",
    )
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "blk",
                        "kind": "part",
                        "source": "parts/blk.py",
                        "attach": "a",
                        "inputs": [],
                        "occurrences": occurrences,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_render_occurrence_bodies_carry_exact_identity(tmp_path):
    _occurrence_assembly(
        tmp_path,
        [{"frame": "a", "mirror": None}, {"frame": "b", "mirror": "yz"}],
    )
    artifacts = tmp_path / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    render.render_to(str(artifacts), 1, objects=objs, node_ids=path_ids(objs))
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    by_id = {o["id"]: o for o in model["objects"]}
    assert set(by_id) == {"blk/blk", "blk_2/blk"}
    # The first placement is the primary: no occurrence fields.
    assert "occurrenceOf" not in by_id["blk/blk"]
    # The second placement points at the primary's exact id + its placement index.
    assert by_id["blk_2/blk"]["occurrenceOf"] == "blk/blk"
    assert by_id["blk_2/blk"]["occurrenceIndex"] == 2


def test_render_subassembly_occurrence_internals_carry_identity(tmp_path):
    """An instanced SUB-assembly emits each placement's internals under a distinct
    path; every non-primary internal names its primary-path counterpart."""
    (tmp_path / "rig").mkdir()
    (tmp_path / "rig" / "parts").mkdir()
    (tmp_path / "rig" / "skeleton.py").write_text(
        """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("o", Location((0, 0, 0)))
    return s
""",
        encoding="utf-8",
    )
    (tmp_path / "rig" / "parts" / "blk.py").write_text(
        """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(10, 10, 10)
    show(p.part, name="Blk")
""",
        encoding="utf-8",
    )
    (tmp_path / "rig" / "assembly.json").write_text(
        json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "blk",
                        "kind": "part",
                        "source": "parts/blk.py",
                        "attach": "o",
                        "inputs": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "skeleton.py").write_text(
        """
from solidifai import skeleton
from build123d import Location
def build():
    s = skeleton()
    s.frame("a", Location((0, 0, 0)))
    s.frame("b", Location((60, 0, 0)))
    return s
""",
        encoding="utf-8",
    )
    (tmp_path / "assembly.json").write_text(
        json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "rig",
                        "kind": "assembly",
                        "source": "rig/",
                        "attach": "a",
                        "inputs": [],
                        "occurrences": [
                            {"frame": "a", "mirror": None},
                            {"frame": "b", "mirror": None},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    artifacts = tmp_path / ".solidifai" / "artifacts"
    artifacts.mkdir(parents=True)
    objs = graph.build_node(str(tmp_path), params={}, parent=None)
    render.render_to(str(artifacts), 1, objects=objs, node_ids=path_ids(objs))
    model = json.loads((artifacts / "model.json").read_text(encoding="utf-8"))
    by_id = {o["id"]: o for o in model["objects"]}
    assert set(by_id) == {"rig/blk/blk", "rig_2/blk/blk"}
    assert "occurrenceOf" not in by_id["rig/blk/blk"]
    # The occurrence marker is on the sub-assembly prefix; the internal body names
    # its primary-path counterpart exactly (not a slug guess).
    assert by_id["rig_2/blk/blk"]["occurrenceOf"] == "rig/blk/blk"
    assert by_id["rig_2/blk/blk"]["occurrenceIndex"] == 2
