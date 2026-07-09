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


def test_multi_solid_single_object_round_trips_with_attribution(tmp_path):
    # One show() of a 2-solid compound must round-trip as ONE object carrying BOTH
    # solids -- not split into two objects zipped against one metadata entry.
    from build123d import Compound, Location

    b1 = Box(2, 2, 2)
    b2 = Box(4, 4, 4).moved(Location((10, 0, 0)))
    twin = Compound(children=[b1, b2])
    objs = [ShownObject(name="Twin", shape=twin, color=None, material="pla")]
    v0 = sum(s.volume for s in twin.solids())
    serialize.dump_result(str(tmp_path), "k", objs)
    back = serialize.load_result(str(tmp_path), "k")
    assert back is not None and len(back) == 1  # ONE object, not two
    assert back[0].name == "Twin"
    assert len(back[0].shape.solids()) == 2  # both solids kept together
    assert abs(sum(s.volume for s in back[0].shape.solids()) - v0) < 1e-6


def test_multi_solid_then_solid_object_attributed_by_count(tmp_path):
    # A 2-solid object followed by a 1-solid object: split by recorded per-object
    # counts, not naive 1:1, so each object gets exactly its own solids.
    from build123d import Compound, Location

    twin = Compound(children=[Box(2, 2, 2), Box(2, 2, 2).moved(Location((8, 0, 0)))])
    single = Box(6, 6, 6)
    objs = [
        ShownObject(name="Twin", shape=twin, color=None, material="pla"),
        ShownObject(name="Solo", shape=single, color=None, material="steel"),
    ]
    serialize.dump_result(str(tmp_path), "k", objs)
    back = serialize.load_result(str(tmp_path), "k")
    assert [o.name for o in back] == ["Twin", "Solo"]
    assert len(back[0].shape.solids()) == 2 and len(back[1].shape.solids()) == 1
    assert back[1].material == "steel"  # metadata attributed to the right object


def test_non_solid_object_marks_entry_non_cacheable(tmp_path):
    # The audited scenario: a 2-solid object + a non-solid reference face. The face
    # cannot round-trip through solids(), so the WHOLE entry is marked non-cacheable
    # and load is a clean miss -- never a silent misattribution / dropped face.
    from build123d import Compound, Location, Rectangle

    twin = Compound(children=[Box(2, 2, 2), Box(2, 2, 2).moved(Location((8, 0, 0)))])
    objs = [
        ShownObject(name="Twin", shape=twin, color=None, material="pla"),
        ShownObject(name="Ref", shape=Rectangle(5, 5), color=None, material=None, role="reference"),
    ]
    serialize.dump_result(str(tmp_path), "k", objs)
    assert serialize.load_result(str(tmp_path), "k") is None  # cleanly skipped
    # a non-cacheable entry writes no brep, so DiskCache.peek reports it absent
    from solidifai_engine.assembly.diskcache import DiskCache

    dc = DiskCache(str(tmp_path.parent))
    dc.dir = str(tmp_path)  # point at the dir dump_result wrote into
    assert dc.peek("k") is False


def test_corrupt_brep_is_safe_miss(tmp_path):
    objs = [ShownObject(name="P", shape=Box(2, 2, 2), color=None, material="pla")]
    serialize.dump_result(str(tmp_path), "k", objs)
    # truncate the brep to simulate a torn/corrupt write
    (tmp_path / "k.brep").write_text("not a real brep", encoding="utf-8")
    assert serialize.load_result(str(tmp_path), "k") is None  # safe miss, no raise
