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
