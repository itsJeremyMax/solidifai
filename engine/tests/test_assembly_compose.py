from build123d import Box, Location

from solidifai import ShownObject
from solidifai_engine.assembly import compose


def test_place_translates_and_repaths():
    obj = ShownObject(name="Base", shape=Box(2, 2, 2), color=None, material=None)
    placed = compose.place([obj], at=Location((10, 0, 0)), path_prefix="enclosure")
    assert placed[0].name == "enclosure/Base"
    # the box centroid moved by the frame
    assert placed[0].shape.bounding_box().center().X == 10.0


def test_place_at_origin_keeps_geometry():
    obj = ShownObject(name="Lid", shape=Box(2, 2, 2), color=None, material=None)
    placed = compose.place([obj], at=Location(), path_prefix="")
    assert placed[0].name == "Lid"
    assert placed[0].shape.bounding_box().center().X == 0.0


def test_place_preserves_material_and_color():
    obj = ShownObject(name="P", shape=Box(1, 1, 1), color=(0.1, 0.2, 0.3), material="abs")
    placed = compose.place([obj], at=Location((1, 0, 0)), path_prefix="a")
    assert placed[0].material == "abs"
    assert placed[0].color == (0.1, 0.2, 0.3)


def test_place_composes_with_existing_placement():
    # An object already positioned at z=6 (as if placed inside a sub-assembly).
    # Placing it in a parent at x=10 must COMPOSE (-> (10,0,6)), not REPLACE
    # (which would wipe the z=6 and give (10,0,0)). Regression guard for nesting.
    inner = ShownObject(
        name="Knuckle",
        shape=Box(2, 2, 2).located(Location((0, 0, 6))),
        color=None,
        material=None,
    )
    placed = compose.place([inner], at=Location((10, 0, 0)), path_prefix="hinge")
    c = placed[0].shape.bounding_box().center()
    assert (round(c.X, 3), round(c.Y, 3), round(c.Z, 3)) == (10.0, 0.0, 6.0)
