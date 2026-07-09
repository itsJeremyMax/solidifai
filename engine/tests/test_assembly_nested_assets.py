"""A part inside a nested sub-assembly must resolve import_cad() relative paths
against the TRUE workspace root, exactly like a root-level part -- not against its
own node dir. Regression for the asymmetric set_workspace_root in runner.run_part.
"""

import json

from build123d import Box, export_brep

from solidifai_engine.assembly import graph

ROOT_SKEL = """
from solidifai import skeleton
from build123d import Location
PARAMS = {}
def build():
    s = skeleton(); s.frame("f", Location((0, 0, 0))); return s
"""

SUB_SKEL = """
from solidifai import skeleton
from build123d import Location
def build(parent=None):
    s = skeleton(); s.frame("g", Location((0, 0, 0))); return s
"""

# The part references an asset by a path relative to the WORKSPACE ROOT.
PIN = """
from solidifai import show, import_cad
def build(inputs):
    show(import_cad("assets/fixture.brep"), name="Pin")
"""


def _nested_ws(root):
    (root / "assets").mkdir(parents=True)
    export_brep(Box(10, 10, 10), str(root / "assets" / "fixture.brep"))
    (root / "skeleton.py").write_text(ROOT_SKEL, encoding="utf-8")
    (root / "assembly.json").write_text(
        json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": [{"id": "hinge", "kind": "assembly", "source": "hinge", "attach": "f"}],
            }
        ),
        encoding="utf-8",
    )
    hinge = root / "hinge"
    (hinge / "parts").mkdir(parents=True)
    (hinge / "skeleton.py").write_text(SUB_SKEL, encoding="utf-8")
    (hinge / "parts" / "pin.py").write_text(PIN, encoding="utf-8")
    (hinge / "assembly.json").write_text(
        json.dumps(
            {
                "version": 2,
                "skeleton": "skeleton.py",
                "children": [
                    {
                        "id": "pin",
                        "kind": "part",
                        "source": "parts/pin.py",
                        "attach": "g",
                        "inputs": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_nested_part_resolves_asset_against_workspace_root(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    _nested_ws(root)
    # Before the fix this raised FileNotFoundError (looked in hinge/assets/).
    objs = graph.build_node(str(root), params={}, parent=None)
    assert len(objs) == 1
    assert objs[0].name == "hinge/pin/Pin"
    assert abs(objs[0].shape.volume - 1000.0) < 1.0  # the 10mm cube asset loaded
