from build123d import Box, BuildPart, Hole

from solidifai import ShownObject, build_scope, show
from solidifai_engine.assembly import serialize


def _part_objects():
    with build_scope() as scope:
        with BuildPart() as p:
            Box(20, 20, 5)
            Hole(radius=2.5)
        show(p.part, name="Plate", material="aluminum", color=(0.2, 0.3, 0.4))
        return list(scope.objects)


def test_round_trip_preserves_geometry_and_metadata(tmp_path):
    objs = _part_objects()
    v0 = objs[0].shape.volume
    serialize.dump_result(str(tmp_path), "abc", objs)
    back = serialize.load_result(str(tmp_path), "abc")
    assert back is not None and len(back) == 1
    assert back[0].name == "Plate"
    assert back[0].material == "aluminum"
    assert tuple(round(c, 4) for c in back[0].color) == (0.2, 0.3, 0.4)
    assert abs(back[0].shape.volume - v0) < 1e-6  # BREP is exact


def test_load_missing_returns_none(tmp_path):
    assert serialize.load_result(str(tmp_path), "nope") is None


def test_multi_shape_part_round_trips_in_order(tmp_path):
    with build_scope() as scope:
        show(Box(2, 2, 2), name="A", material="pla")
        show(Box(4, 4, 4), name="B", material="steel")
        objs = list(scope.objects)
    serialize.dump_result(str(tmp_path), "k", objs)
    back = serialize.load_result(str(tmp_path), "k")
    assert [o.name for o in back] == ["A", "B"]
    assert back[0].shape.volume < back[1].shape.volume  # order preserved


def test_corrupt_brep_is_safe_miss(tmp_path):
    objs = [ShownObject(name="P", shape=Box(2, 2, 2), color=None, material="pla")]
    serialize.dump_result(str(tmp_path), "k", objs)
    # truncate the brep to simulate a torn/corrupt write
    (tmp_path / "k.brep").write_text("not a real brep", encoding="utf-8")
    assert serialize.load_result(str(tmp_path), "k") is None  # safe miss, no raise
