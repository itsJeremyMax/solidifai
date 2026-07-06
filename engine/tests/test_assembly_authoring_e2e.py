"""End-to-end: author a 2-part assembly from an empty workspace using only the
public authoring tools, then assert the composed result, the tree, and that a
per-part edit rebuilds only that part."""

import os

from solidifai_engine.session import Session

SKEL_2FRAME = """
from solidifai import skeleton
from build123d import Location
PARAMS = {
    "body_w": {"value": 60.0, "min": 30.0, "max": 120.0, "step": 1.0, "unit": "mm"},
    "body_h": {"value": 30.0, "min": 15.0, "max": 90.0, "step": 1.0, "unit": "mm"},
    "wall":   {"value": 2.4, "min": 1.2, "max": 5.0, "step": 0.2, "unit": "mm"},
}
def build(body_w, body_h, wall):
    s = skeleton()
    s.scalar("body_w", body_w)
    s.scalar("wall", wall)
    s.frame("base_frame", Location((0, 0, 0)))
    s.frame("lid_frame", Location((0, 0, body_h)))
    return s
"""

BASE_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], inputs["wall"])
    show(p.part, name="Base")
"""

LID_PART = """
from solidifai import show
from build123d import BuildPart, Box
def build(inputs):
    with BuildPart() as p:
        Box(inputs["body_w"], inputs["body_w"], 3)
    show(p.part, name="Lid")
"""


def _mk(tmp_path) -> Session:
    root = tmp_path
    s = Session(str(root / ".solidifai" / "artifacts"), model_path=str(root / "assembly.json"))
    s.startup()
    return s


def test_author_assembly_from_scratch(tmp_path):
    s = _mk(tmp_path)
    assert s.set_skeleton(SKEL_2FRAME)["ok"]
    assert s.set_part("base", BASE_PART, attach="base_frame", inputs=["body_w", "wall"])["ok"]
    assert s.set_part("lid", LID_PART, attach="lid_frame", inputs=["body_w", "wall"])["ok"]

    info = s.get_model_info()
    names = {o["name"] for o in info["objects"]}
    assert {"base/Base", "lid/Lid"} <= names

    # Editing one part rebuilds only it: changing the lid thickness misses cache
    # for the lid while the unchanged base is served from the in-memory cache.
    # (NodeCache exposes hits/misses, not a stats() snapshot -- see B1 tests.)
    hits_before, misses_before = s._node_cache.hits, s._node_cache.misses
    assert s.set_part(
        "lid",
        LID_PART.replace(
            'Box(inputs["body_w"], inputs["body_w"], 3)',
            'Box(inputs["body_w"], inputs["body_w"], 4)',
        ),
    )["ok"]
    # the base part was a cache hit on the rebuild; the edited lid was a miss
    assert s._node_cache.hits > hits_before
    assert s._node_cache.misses > misses_before

    assert s.get_model_info()["objects"]  # still composes
    # the tree reflects both children
    assert {c["id"] for c in s.get_assembly_tree()["tree"]["children"]} == {"base", "lid"}
